"""webhook_receiver Lambda.

Entry points:
- SNS: AWS End User Messaging publishes inbound WhatsApp events here
  (insurance card photo, symptom voice note, free text, button taps).
- API Gateway: direct webhook POST (and Meta GET verification challenge),
  used for local testing and alternative integrations.

Responsibilities:
1. Parse the event into normalized `InboundIntakeMessage`s.
2. For media (card photo / voice note), pull the file into S3 via the
   Social Messaging API.
3. Persist each message to the DynamoDB intake-events table (whose Stream
   drives the channel_dispatcher Lambda with a batching window).

Keeping media fetch + raw persistence here (and the AgentCore invocation in
the stream consumer) means a patient's rapid message burst - card photo,
then voice note, then a follow-up text - gets naturally batched before it
ever reaches the agent, protecting cost and giving the agent the complete
picture in one pass.
"""
import hashlib
import hmac
import json
import time

from common import aws_clients, config
from common.logging_utils import get_logger, log_event
from common.sns_parser import parse_sns_record
from common.models import InboundIntakeMessage, KIND_IMAGE, KIND_AUDIO
from common import channels

logger = get_logger("webhook_receiver")

_EVENT_TTL_DAYS = 7


def handler(event, context):
    records = event.get("Records")
    if records and records[0].get("EventSource") == "aws:sns":
        return _handle_sns(records)
    if "httpMethod" in event or "requestContext" in event:
        return _handle_http(event)
    msgs = parse_sns_record(json.dumps(event))
    stored = _store_all(msgs)
    return {"stored": stored}


def _handle_sns(records):
    total = 0
    for rec in records:
        sns_message = rec.get("Sns", {}).get("Message", "")
        msgs = parse_sns_record(sns_message)
        total += _store_all(msgs)
    log_event(logger, "info", "sns.processed", stored=total, records=len(records))
    return {"stored": total}


def _handle_http(event):
    method = event.get("httpMethod", "POST")

    if method == "GET":
        return _handle_verification_challenge(event)

    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")

    if not _verify_meta_signature(event, body):
        log_event(logger, "warning", "webhook.signature.invalid")
        return {"statusCode": 403, "body": json.dumps({"error": "invalid signature"})}

    msgs = parse_sns_record(body)
    stored = _store_all(msgs)
    return {"statusCode": 200, "body": json.dumps({"stored": stored})}


def _handle_verification_challenge(event):
    """Meta's GET handshake when configuring a direct webhook URL.

    Meta sends hub.mode=subscribe, hub.verify_token, hub.challenge. We must
    echo hub.challenge back ONLY if hub.verify_token matches our configured
    META_WEBHOOK_VERIFY_TOKEN. If no verify token is configured, we accept
    any challenge (useful for local testing only - set
    META_WEBHOOK_VERIFY_TOKEN before exposing this endpoint publicly)."""
    params = event.get("queryStringParameters") or {}
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    if challenge is None:
        return {"statusCode": 200, "body": "ok"}

    if config.META_WEBHOOK_VERIFY_TOKEN:
        if verify_token != config.META_WEBHOOK_VERIFY_TOKEN:
            log_event(logger, "warning", "webhook.verify_token.mismatch")
            return {"statusCode": 403, "body": "verification token mismatch"}
    else:
        log_event(logger, "warning", "webhook.verify_token.unset_accepting_any")

    return {"statusCode": 200, "body": challenge}


def _verify_meta_signature(event, body: str) -> bool:
    """Validate Meta's X-Hub-Signature-256 header (HMAC-SHA256 over the raw
    body, keyed with META_APP_SECRET).

    Only applies to the direct API Gateway webhook path - the SNS path is
    already signature-verified by AWS End User Messaging Social before it
    reaches us. If META_APP_SECRET is not configured, verification is
    skipped (accepted) so local testing and SNS-only deployments keep
    working; configure it before exposing this endpoint publicly."""
    if not config.META_APP_SECRET:
        return True

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    signature_header = headers.get("x-hub-signature-256", "")
    if not signature_header.startswith("sha256="):
        return False

    expected = hmac.new(
        config.META_APP_SECRET.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


def _store_all(msgs) -> int:
    count = 0
    for m in msgs:
        try:
            _enrich_and_store(m)
            count += 1
        except Exception as exc:  # noqa: BLE001
            log_event(
                logger, "error", "store.failed", message_id=m.message_id, error=str(exc)
            )
    return count


def _enrich_and_store(m: InboundIntakeMessage) -> None:
    s3_media_key = None
    if m.kind in (KIND_IMAGE, KIND_AUDIO) and m.media_id:
        ext = _ext_for_mime(m.media_mime, m.kind)
        kind_label = "card" if m.kind == KIND_IMAGE else "voice"
        s3_media_key = f"intake/{m.sender}/{m.message_id}-{kind_label}{ext}"
        try:
            channels.fetch_whatsapp_media_to_s3(
                media_id=m.media_id,
                origination_phone_number_id=m.phone_number_id,
                s3_key=s3_media_key,
            )
        except Exception as exc:  # noqa: BLE001 - media fetch best-effort
            log_event(logger, "warning", "media.fetch.failed", error=str(exc))
            s3_media_key = None

    ttl = int(time.time()) + _EVENT_TTL_DAYS * 86400
    item = m.to_item(ttl)
    item["s3_media_key"] = s3_media_key

    table = aws_clients.dynamodb_resource().Table(config.INTAKE_EVENTS_TABLE)
    table.put_item(Item={k: v for k, v in item.items() if v is not None})
    log_event(
        logger,
        "info",
        "event.stored",
        kind=m.kind,
        channel=m.channel,
        has_media=bool(s3_media_key),
    )


def _ext_for_mime(mime, kind) -> str:
    if not mime:
        return ".bin" if kind == KIND_AUDIO else ".jpg"
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/amr": ".amr",
        "audio/wav": ".wav",
    }
    return mapping.get(mime.split(";")[0].strip(), ".bin")
