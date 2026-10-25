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
from typing import List, Dict, Any, Optional

from . import aws_clients, config
from .logging_utils import get_logger, log_event

logger = get_logger(__name__)


# --------------------------------------------------------------------------- #
# WhatsApp message builders (patient-facing)
# --------------------------------------------------------------------------- #
def build_whatsapp_text(to: str, body: str) -> Dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": to,
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
        "to": to,
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
def send_whatsapp(message_obj: Dict[str, Any], origination_phone_number_id: str) -> Optional[str]:
    """Send a WhatsApp Message object. Returns the Meta message id (or None)."""
    if not origination_phone_number_id:
        log_event(logger, "warning", "whatsapp.send.skipped.no_phone_number_id")
        return None
    client = aws_clients.social_messaging()
    resp = client.send_whatsapp_message(
        originationPhoneNumberId=origination_phone_number_id,
        message=json.dumps(message_obj).encode("utf-8"),
        metaApiVersion=config.META_API_VERSION,
    )
    mid = resp.get("messageId")
    log_event(logger, "info", "whatsapp.send.ok", message_id=mid)
    return mid


def send_rcs_action_card(to: str, text: str, buttons: List[Dict[str, str]]) -> Optional[str]:
    """Send the doctor/clinic an RCS approval card (degrades to SMS text)."""
    if not config.RCS_PHONE_NUMBER_ID:
        log_event(logger, "warning", "rcs.send.skipped.no_phone_number_id")
        return None
    chips = "  ".join(f"[{b['title']}]" for b in buttons)
    body = f"{text}\n{chips}" if chips else text
    client = aws_clients.sms_voice()
    resp = client.send_text_message(
        DestinationPhoneNumber=to,
        OriginationIdentity=config.RCS_PHONE_NUMBER_ID,
        MessageBody=body[:1600],
        MessageType="TRANSACTIONAL",
    )
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
    """Pull a WhatsApp media file (insurance card photo / voice note) into S3."""
    client = aws_clients.social_messaging()
    client.get_whatsapp_message_media(
        mediaId=media_id,
        originationPhoneNumberId=origination_phone_number_id,
        destinationS3File={"bucketName": config.MEDIA_BUCKET, "key": s3_key},
    )
    log_event(logger, "info", "media.fetch.ok", s3_key=s3_key)
    return s3_key
