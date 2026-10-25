"""Parse AWS End User Messaging inbound events into `InboundIntakeMessage`s.

AWS End User Messaging Social delivers WhatsApp events to an SNS topic. The SNS
`Message` is a JSON string whose `whatsAppWebhookEntry` field is a base64- or
JSON-encoded Meta webhook entry containing `changes[].value.messages[]`.

Reference: "Message and event format in AWS End User Messaging Social"
(whatsAppWebhookEntry / GetWhatsAppMessageMedia).
"""
import base64
import json
from typing import List, Optional

from .models import (
    InboundIntakeMessage,
    CHANNEL_WHATSAPP,
    CHANNEL_RCS,
    CHANNEL_SMS,
    KIND_TEXT,
    KIND_IMAGE,
    KIND_AUDIO,
    KIND_BUTTON,
    KIND_UNKNOWN,
)


def _maybe_json_loads(value):
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        pass
    try:
        decoded = base64.b64decode(value).decode("utf-8")
        return json.loads(decoded)
    except Exception:  # noqa: BLE001 - best effort decode
        return value


def parse_sns_record(sns_message: str) -> List[InboundIntakeMessage]:
    """Parse the `Message` string of one SNS record into normalized messages.

    Returns a (possibly empty) list; delivery receipts / status events
    produce an empty list.
    """
    body = _maybe_json_loads(sns_message)
    if not isinstance(body, dict):
        return []

    if "whatsAppWebhookEntry" in body:
        entry = _maybe_json_loads(body["whatsAppWebhookEntry"])
        ctx = {
            "aws_phone_number_id": body.get("context", {}).get("MetaPhoneNumberId")
            or body.get("originationPhoneNumberId"),
        }
        return _parse_whatsapp_entry(entry, ctx)

    if body.get("messageType") or body.get("originationNumber") or "messageBody" in body:
        msg = _parse_sms_rcs(body)
        return [msg] if msg else []

    return []


def _parse_whatsapp_entry(entry, ctx) -> List[InboundIntakeMessage]:
    if not isinstance(entry, dict):
        return []
    out: List[InboundIntakeMessage] = []
    for change in entry.get("changes", []):
        value = change.get("value", {})
        metadata = value.get("metadata", {})
        phone_number_id = (
            ctx.get("aws_phone_number_id")
            or metadata.get("phone_number_id")
            or ""
        )
        for m in value.get("messages", []):
            parsed = _parse_whatsapp_message(m, phone_number_id)
            if parsed is not None:
                out.append(parsed)
    return out


def _parse_whatsapp_message(m: dict, phone_number_id: str) -> Optional[InboundIntakeMessage]:
    mtype = m.get("type", "")
    base = dict(
        channel=CHANNEL_WHATSAPP,
        sender=m.get("from", ""),
        phone_number_id=phone_number_id,
        message_id=m.get("id", ""),
        timestamp=str(m.get("timestamp", "")),
        raw=m,
    )
    if mtype == "text":
        return InboundIntakeMessage(kind=KIND_TEXT, text=m.get("text", {}).get("body"), **base)
    if mtype == "image":
        img = m.get("image", {})
        return InboundIntakeMessage(
            kind=KIND_IMAGE,
            media_id=img.get("id"),
            media_mime=img.get("mime_type"),
            text=img.get("caption"),
            **base,
        )
    if mtype in ("audio", "voice"):
        aud = m.get("audio", m.get("voice", {}))
        return InboundIntakeMessage(
            kind=KIND_AUDIO,
            media_id=aud.get("id"),
            media_mime=aud.get("mime_type"),
            **base,
        )
    if mtype in ("button", "interactive"):
        payload = _extract_button_payload(m)
        return InboundIntakeMessage(kind=KIND_BUTTON, button_payload=payload, text=payload, **base)
    return InboundIntakeMessage(kind=KIND_UNKNOWN, **base)


def _extract_button_payload(m: dict) -> Optional[str]:
    if "button" in m:
        return m["button"].get("payload") or m["button"].get("text")
    inter = m.get("interactive", {})
    if inter.get("type") == "button_reply":
        return inter.get("button_reply", {}).get("id")
    if inter.get("type") == "list_reply":
        return inter.get("list_reply", {}).get("id")
    return None


def _parse_sms_rcs(body: dict) -> Optional[InboundIntakeMessage]:
    channel = CHANNEL_RCS if str(body.get("messageType", "")).upper().startswith("RCS") else CHANNEL_SMS
    text = body.get("messageBody") or body.get("messageContent")
    return InboundIntakeMessage(
        channel=channel,
        kind=KIND_BUTTON if body.get("buttonPayload") else KIND_TEXT,
        sender=body.get("originationNumber", ""),
        phone_number_id=body.get("destinationNumber", "") or body.get("originationPhoneNumberId", ""),
        message_id=body.get("messageId", body.get("inboundMessageId", "")),
        timestamp=str(body.get("timestamp", "")),
        text=text,
        button_payload=body.get("buttonPayload"),
        raw=body,
    )
