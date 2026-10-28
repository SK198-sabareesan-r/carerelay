"""Outbound channel builders + senders for AWS CDS.

Covers:
- WhatsApp interactive messages to the PATIENT (document request, list
  picker for "which procedure", status updates) via
  socialmessaging.send_whatsapp_message. The `message` field is a WhatsApp
  Message object (Meta Cloud API shape) serialized to bytes.
- RCS action card to the DOCTOR/CLINIC with Approve / Request-More-Info
  buttons, via pinpoint-sms-voice-v2.send_text_message (falls back to SMS).
- WhatsApp media fetch (insurance card photo, symptom voice note) into S3.
"""
import json
import re
from typing import List, Dict, Any, Optional

from . import aws_clients, config
from .logging_utils import get_logger, log_event

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# WhatsApp message builders (patient-facing)
# --------------------------------------------------------------------------- #
def _to_e164(number: str) -> str:
    """Inbound WhatsApp events carry the sender's number as bare digits
    (e.g. "919500799295" - no "+"), but Meta's Cloud API requires E.164
    format ("+919500799295") for the `to` field on outbound sends.
    Idempotent - already-prefixed numbers pass through unchanged."""
    number = number.strip()
    return number if number.startswith("+") else f"+{number}"


def build_whatsapp_text(to: str, body: str) -> Dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": _to_e164(to),
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }


def build_whatsapp_buttons(
    to: str, body: str, buttons: List[Dict[str, str]], header: Optional[str] = None
) -> Dict[str, Any]:
    """Interactive reply-button card (max 3 buttons)."""
    action_buttons = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]
    msg: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": _to_e164(to),
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body[:1024]},
            "action": {"buttons": action_buttons},
        },
    }
    if header:
        msg["interactive"]["header"] = {"type": "text", "text": header[:60]}
    return msg


def build_whatsapp_list_picker(
    to: str,
    body: str,
    button_label: str,
    sections: List[Dict[str, Any]],
    header: Optional[str] = None,
) -> Dict[str, Any]:
    """Interactive List Message (Meta Cloud API "list" type) - used for the
    pharmacy pickup picker and prior-auth consent choice. `sections` is a
    list of {"title": str, "rows": [{"id": str, "title": str, "description": str}]}
    - Meta caps this at 10 sections and 10 rows total across all sections,
    row title <= 24 chars, row description <= 72 chars (truncated below
    rather than rejected outright, so a long pharmacy name doesn't break
    the whole send)."""
    clipped_sections = []
    for section in sections[:10]:
        rows = [
            {
                "id": r["id"],
                "title": r["title"][:24],
                **({"description": r["description"][:72]} if r.get("description") else {}),
            }
            for r in section.get("rows", [])[:10]
        ]
        clipped_sections.append({"title": section["title"][:24], "rows": rows})

    msg: Dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": _to_e164(to),
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body[:1024]},
            "action": {"button": button_label[:20], "sections": clipped_sections},
        },
    }
    if header:
        msg["interactive"]["header"] = {"type": "text", "text": header[:60]}
    return msg


def build_whatsapp_appointment_confirmation(
    to: str, appointment_datetime_display: str, procedure_name: str, clinic_name: str, cleared_note: str
) -> Dict[str, Any]:
    """The FINAL message that releases the appointment date/time to the
    patient - sent only after insurance clearance (insured) or doctor
    approval (self-pay). Before this point the patient was never told the
    slot (see dashboard_api._handle_start_followup: appointment_datetime is
    stored withheld). `cleared_note` states why they're now confirmed
    (e.g. 'Your insurance has been verified' or 'Your visit has been
    approved by the doctor')."""
    body = (
        f"{cleared_note} You're all set for your {procedure_name} at {clinic_name}.\n\n"
        f"Please come in on: {appointment_datetime_display}\n\n"
        "Arrive 15 minutes early. Reply here if you need to reschedule."
    )
    return build_whatsapp_buttons(
        to=to,
        body=body,
        buttons=[{"id": "appt_ack", "title": "See you then"}, {"id": "appt_reschedule", "title": "Reschedule"}],
        header="Appointment Confirmed",
    )


def build_whatsapp_appointment_reminder(to: str, appointment_time_display: str) -> Dict[str, Any]:
    """24-hours-prior onboarding reminder with quick-reply buttons
    (Start Verification / Reschedule).

    IMPORTANT: this is a business-INITIATED message (the patient hasn't
    messaged us first / it may be outside the 24h customer service
    window), which per Meta's WhatsApp Business policy MUST be sent as a
    pre-approved WhatsApp Template Message, not a free-form interactive
    message like this one. This builder produces the free-form shape for
    local testing and for replies sent WITHIN an open customer service
    window (e.g. resending the same prompt after the patient has already
    messaged in). For the real unprompted 24h-prior reminder, submit this
    exact body + button set as a Template in the WhatsApp Manager /ÁWS End
    User Messaging Social console, get it approved by Meta, then send it
    via a template-type message referencing the approved template name
    instead of this interactive builder."""
    return build_whatsapp_buttons(
        to=to,
        body=(
            f"Your appointment is scheduled for {appointment_time_display}. "
            "Would you like to complete digital insurance verification now?"
        ),
        buttons=[
            {"id": "start_verification", "title": "Start Verification"},
            {"id": "reschedule", "title": "Reschedule"},
        ],
    )


def build_whatsapp_document_request(to: str, missing_documents: List[str]) -> Dict[str, Any]:
    """Ask the patient to upload the specific documents the rules engine flagged."""
    items = "\n".join(f"- {d}" for d in missing_documents)
    body = (
        "To process your prior authorization we still need:\n"
        f"{items}\n\nPlease reply with a photo or PDF of each document."
    )
    return build_whatsapp_text(to, body)


# --------------------------------------------------------------------------- #
# Senders
# --------------------------------------------------------------------------- #
_AWS_PHONE_NUMBER_ID_PATTERN = re.compile(r"^(phone-number-id-.*|arn:.*:phone-number-id/[0-9a-zA-Z]+)$")


def _resolve_aws_phone_number_id(origination_phone_number_id: str) -> str:
    """send_whatsapp_message's `originationPhoneNumberId` parameter must be
    AWS's OWN phone-number-id (e.g. "phone-number-id-5f633f54...") - NOT
    Meta's numeric phone number ID (e.g. "1434310029761397"), which is what
    inbound events actually carry in metadata.phone_number_id /
    context.MetaPhoneNumberId (see sns_parser.py). If we're handed a
    Meta-format ID (all digits), look up the matching AWS phone-number-id
    from the linked WABA instead of sending it straight through and getting
    a ValidationException.

    Cached per-process since a deployed Lambda only ever talks to one
    linked WABA's phone number for the lifetime of the container."""
    if not origination_phone_number_id:
        return origination_phone_number_id
    if _AWS_PHONE_NUMBER_ID_PATTERN.match(origination_phone_number_id):
        return origination_phone_number_id  # already the correct format

    cache = _resolve_aws_phone_number_id.__dict__.setdefault("_cache", {})
    if origination_phone_number_id in cache:
        return cache[origination_phone_number_id]

    client = aws_clients.social_messaging()
    resolved = origination_phone_number_id
    try:
        wabas = client.list_linked_whatsapp_business_accounts().get("linkedAccounts", [])
        for waba in wabas:
            detail = client.get_linked_whatsapp_business_account(id=waba["id"])
            for phone in detail.get("account", {}).get("phoneNumbers", []):
                if phone.get("metaPhoneNumberId") == origination_phone_number_id:
                    resolved = phone["phoneNumberId"]
                    break
    except Exception as exc:  # noqa: BLE001 - fall back to passing the original through
        log_event(logger, "warning", "phone_number_id.resolve.failed", error=str(exc))

    cache[origination_phone_number_id] = resolved
    return resolved


def send_whatsapp(message_obj: Dict[str, Any], origination_phone_number_id: str) -> Optional[str]:
    """Send a WhatsApp Message object. Returns the Meta message id (or None)."""
    if not origination_phone_number_id:
        log_event(logger, "warning", "whatsapp.send.skipped.no_phone_number_id")
        return None
    resolved_id = _resolve_aws_phone_number_id(origination_phone_number_id)
    client = aws_clients.social_messaging()
    resp = client.send_whatsapp_message(
        originationPhoneNumberId=resolved_id,
        message=json.dumps(message_obj).encode("utf-8"),
        metaApiVersion=config.META_API_VERSION,
    )
    mid = resp.get("messageId")
    log_event(logger, "info", "whatsapp.send.ok", message_id=mid)
    return mid


def send_rcs_action_card(
    to: str, text: str, buttons: List[Dict[str, str]], title: str = "CareRelay Clinical Approval"
) -> Optional[str]:
    """Send the doctor/clinic a REAL RCS rich card with tappable reply chips
    (the Approve / Request-Notes buttons), via AWS End User Messaging's
    send_rcs_message. OriginationIdentity is the RCS agent ID
    (config.RCS_AGENT_ID, e.g. "rcs-..."), NOT a phone number - RCS is
    agent-based. If the recipient's device/carrier can't do RCS, AWS
    automatically delivers the SMS FallbackConfiguration instead (chips
    flattened to text), so the doctor always gets *something*.

    Reply-chip titles are capped at 25 chars by Meta's RCS; PostbackData is
    the button id, echoed back to us when the doctor taps it (so inbound
    handling can tell Approve from Request-Notes)."""
    if not config.RCS_AGENT_ID:
        log_event(logger, "warning", "rcs.send.skipped.no_agent_id")
        return None

    suggestions = [
        {"Reply": {"Text": b["title"][:25], "PostbackData": b.get("id", b["title"])[:2048]}}
        for b in buttons[:11]  # RCS allows up to 11 suggestions per card
    ]
    card_content: Dict[str, Any] = {
        "Title": title[:200],
        "Description": text[:2000],
    }
    if suggestions:
        card_content["Suggestions"] = suggestions

    chips_text = "  ".join(f"[{b['title']}]" for b in buttons)
    fallback_body = (f"{title}\n\n{text}\n{chips_text}" if chips_text else f"{title}\n\n{text}")[:1600]

    kwargs: Dict[str, Any] = {
        "DestinationPhoneNumber": _to_e164(to),
        "OriginationIdentity": config.RCS_AGENT_ID,
        "RcsMessageContent": {
            "Content": {
                "RichCard": {
                    "CardOrientation": "VERTICAL",
                    "CardContent": card_content,
                }
            }
        },
        "MessageTrafficType": "TRANSACTIONAL",
    }
    # SMS fallback only wires up if a real origination number is configured.
    if config.SMS_ORIGINATION_NUMBER:
        kwargs["FallbackConfiguration"] = {
            "Channel": "SMS",
            "MessageBody": fallback_body,
            "OriginationIdentity": config.SMS_ORIGINATION_NUMBER,
        }

    client = aws_clients.sms_voice()
    resp = client.send_rcs_message(**kwargs)
    mid = resp.get("MessageId")
    log_event(logger, "info", "rcs.send.ok", message_id=mid)
    return mid


def send_sms(to: str, text: str) -> Optional[str]:
    if not config.SMS_ORIGINATION_NUMBER:
        log_event(logger, "warning", "sms.send.skipped.no_origination")
        return None
    client = aws_clients.sms_voice()
    resp = client.send_text_message(
        DestinationPhoneNumber=to,
        OriginationIdentity=config.SMS_ORIGINATION_NUMBER,
        MessageBody=text[:1600],
        MessageType="TRANSACTIONAL",
    )
    return resp.get("MessageId")


# --------------------------------------------------------------------------- #
# WhatsApp media -> S3
# --------------------------------------------------------------------------- #
def fetch_whatsapp_media_to_s3(media_id: str, origination_phone_number_id: str, s3_key: str) -> str:
    """Pull a WhatsApp media file (insurance card photo / voice note) into S3.

    get_whatsapp_message_media's originationPhoneNumberId has the SAME
    requirement as send: it must be AWS's own phone-number-id, not Meta's
    numeric ID that inbound events carry. Without this translation the call
    fails with a ValidationException and the media never lands in S3 - which
    makes the dispatcher think the card/voice never arrived and re-request
    it forever."""
    resolved_id = _resolve_aws_phone_number_id(origination_phone_number_id)
    client = aws_clients.social_messaging()
    client.get_whatsapp_message_media(
        mediaId=media_id,
        originationPhoneNumberId=resolved_id,
        destinationS3File={"bucketName": config.MEDIA_BUCKET, "key": s3_key},
    )
    log_event(logger, "info", "media.fetch.ok", s3_key=s3_key)
    return s3_key
