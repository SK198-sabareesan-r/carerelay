"""channel_dispatcher Lambda.

Triggered by the IntakeEventsTable DynamoDB Stream with a batching window
(configured in cdk/stacks/compute_stack.py). Groups a patient's rapid
message burst (insurance card photo, voice note, free text) by sender,
invokes the CareRelay Strands agent on Amazon Bedrock AgentCore Runtime
ONCE per case, persists the resulting case to PriorAuthTable in the exact
shape lambdas/dashboard_api/handler.py expects, and dispatches the drafted
messages over AWS CDS:

    - WhatsApp (patient)  - AWS End User Messaging Social
    - RCS (doctor/clinic) - AWS End User Messaging (falls back to SMS)
    - SES (audit report)  - KMS-signed executive summary email

This Lambda NEVER makes a coverage/eligibility decision itself - it only
reads the structured `case_result` the agent returned (which itself only
narrates what the deterministic rules_engine / simulated payer tool
produced) and routes it to the right channels. See
agent_app/__init__.py for the full "code decides, AI talks" rationale.
"""
import json
import re
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from common import aws_clients, config, channels
from common.logging_utils import get_logger, log_event
from common.models import KIND_IMAGE, KIND_AUDIO, KIND_TEXT, CHANNEL_WHATSAPP

logger = get_logger("channel_dispatcher")

# Matches a 5-digit CPT code or an ADA dental code like D2740 in free text.
_CPT_PATTERN = re.compile(r"\b(D\d{4}|\d{5})\b")

# Fallback used when the patient's message batch doesn't name a procedure.
# A real deployment would look this up from an appointment/EHR system -
# out of scope here, so we default to a representative procedure rather
# than silently skipping the case.
_DEFAULT_CPT_CODE = "29881"
_DEFAULT_PROCEDURE_NAME = "Knee arthroscopy, meniscectomy"
_DEFAULT_PAYER_ID = "PAYER-ACME"

_AGENT_SESSION_PREFIX = "carerelay-case-"  # runtimeSessionId must be 33+ chars


def handler(event, context):
    records = event.get("Records", [])
    decoded = _decode_records(records)
    log_event(logger, "info", "batch.received", records=len(records), decoded=len(decoded))

    groups: Dict[str, List[tuple]] = defaultdict(list)
    for event_id, msg in decoded:
        groups[msg.get("sender", "unknown")].append((event_id, msg))

    failures: List[Dict[str, str]] = []
    for sender, items in groups.items():
        msgs = [m for _, m in items]
        try:
            _process_patient_batch(sender, msgs)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "error", "group.failed", error=str(exc))
            for event_id, _ in items:
                if event_id:
                    failures.append({"itemIdentifier": event_id})

    return {"batchItemFailures": failures}


def _decode_records(records: List[Dict[str, Any]]):
    out = []
    for rec in records:
        if rec.get("eventName") not in ("INSERT", "MODIFY"):
            continue
        new_image = rec.get("dynamodb", {}).get("NewImage")
        if not new_image:
            continue
        out.append((rec.get("eventID"), _deserialize(new_image)))
    return out


def _deserialize(image: Dict[str, Any]) -> Dict[str, Any]:
    """Minimal DynamoDB Stream image -> plain dict (string/number/bool only)."""
    result = {}
    for key, type_val in image.items():
        if "S" in type_val:
            result[key] = type_val["S"]
        elif "N" in type_val:
            result[key] = type_val["N"]
        elif "BOOL" in type_val:
            result[key] = type_val["BOOL"]
        elif "NULL" in type_val:
            result[key] = None
    return result


# --------------------------------------------------------------------------- #
# Per-patient batch processing
# --------------------------------------------------------------------------- #
def _process_patient_batch(sender: str, msgs: List[Dict[str, Any]]) -> None:
    channel = next((m.get("channel") for m in msgs if m.get("channel")), CHANNEL_WHATSAPP)
    phone_number_id = next((m.get("phone_number_id") for m in msgs if m.get("phone_number_id")), "")

    card_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_IMAGE and m.get("s3_media_key")), None)
    voice_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_AUDIO and m.get("s3_media_key")), None)
    voice_mime = next((m.get("media_mime") for m in msgs if m.get("kind") == KIND_AUDIO), None)
    text_parts = [m["text"] for m in msgs if m.get("kind") == KIND_TEXT and m.get("text")]
    combined_text = " ".join(text_parts)

    cpt_code = _extract_cpt_code(combined_text) or _DEFAULT_CPT_CODE
    procedure_name = combined_text.strip()[:120] or _DEFAULT_PROCEDURE_NAME

    case_id = f"case-{uuid.uuid4().hex[:8]}"
    payload = {
        "case_id": case_id,
        "patient_name": _display_name(sender),
        "cpt_code": cpt_code,
        "procedure_name": procedure_name,
        "payer_id": _DEFAULT_PAYER_ID,
        "documents_on_file": [],
    }
    if card_key:
        payload["card_s3_bucket"] = config.MEDIA_BUCKET
        payload["card_s3_key"] = card_key
    if voice_key:
        payload["voice_s3_bucket"] = config.MEDIA_BUCKET
        payload["voice_s3_key"] = voice_key
        payload["voice_media_format"] = _media_format(voice_mime, voice_key)

    agent_response = _invoke_agent(case_id, payload)
    case_result = agent_response.get("case_result")

    if not case_result:
        log_event(logger, "warning", "agent.no_structured_output", case_id=case_id)
        return

    _persist_case(
        case_id=case_id,
        sender=sender,
        channel=channel,
        patient_name=payload["patient_name"],
        cpt_code=cpt_code,
        procedure_name=procedure_name,
        payer_id=payload["payer_id"],
        case_result=case_result,
        card_key=card_key,
        voice_key=voice_key,
        narration=agent_response.get("narration"),
    )
    _dispatch_outbound(
        sender=sender,
        phone_number_id=phone_number_id,
        channel=channel,
        case_result=case_result,
        case_id=case_id,
        patient_name=payload["patient_name"],
    )
    log_event(logger, "info", "case.handled", case_id=case_id,
              outcome=case_result.get("verification", {}).get("outcome"))


def _extract_cpt_code(text: str) -> Optional[str]:
    match = _CPT_PATTERN.search(text or "")
    return match.group(1) if match else None


def _display_name(sender: str) -> str:
    """Patients are identified by phone number only; we never have a real
    name from the WhatsApp payload unless Meta's `profile.name` is parsed
    (sns_parser.py does not currently carry it through). Show a masked
    label rather than inventing a name."""
    tail = sender[-4:] if len(sender) >= 4 else sender
    return f"Patient ***{tail}"


def _media_format(mime: Optional[str], key: str) -> str:
    k = key.lower()
    if k.endswith(".mp3") or (mime and "mpeg" in mime):
        return "mp3"
    if k.endswith(".m4a") or (mime and "mp4" in mime):
        return "mp4"
    if k.endswith(".wav"):
        return "wav"
    if k.endswith(".amr") or (mime and "amr" in mime):
        return "amr"
    return "ogg"


# --------------------------------------------------------------------------- #
# AgentCore invocation
# --------------------------------------------------------------------------- #
def _invoke_agent(case_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if not config.AGENT_RUNTIME_ARN:
        log_event(logger, "warning", "agent.invoke.skipped.no_runtime_arn")
        return {}

    session_id = (_AGENT_SESSION_PREFIX + case_id + uuid.uuid4().hex)[:48]
    client = aws_clients.agentcore_runtime()
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=config.AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps(payload).encode("utf-8"),
        qualifier="DEFAULT",
    )
    body = resp["response"].read()
    result = json.loads(body)
    log_event(logger, "info", "agent.invoke.done", case_id=case_id, status=resp.get("statusCode"))
    return result


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #
def _persist_case(
    *, case_id, sender, channel, patient_name, cpt_code, procedure_name,
    payer_id, case_result, card_key, voice_key, narration,
) -> None:
    verification = case_result.get("verification", {})
    outcome = verification.get("outcome", "NO_MATCHING_RULE")
    status = _status_for_outcome(outcome)

    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    item = {
        "case_id": case_id,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "patient_name": patient_name,
        "patient_phone_masked": f"***{sender[-4:]}" if len(sender) >= 4 else sender,
        "channel": channel,
        "cpt_code": cpt_code,
        "procedure_name": procedure_name,
        "payer_id": payer_id,
        "extracted_card": case_result.get("extracted_card", {}),
        "verification": verification,
        "messages": case_result.get("messages", {}),
        "perceived_facts": (
            [case_result["symptom_summary"]] if case_result.get("symptom_summary") else []
        ),
        "photo_key": card_key,
        "audio_key": voice_key,
        "narration": narration,
    }
    table.put_item(Item={k: v for k, v in item.items() if v not in (None, "")})


def _status_for_outcome(outcome: str) -> str:
    return {
        "PRIOR_AUTH_REQUIRED": "APPROVED",
        "NOT_REQUIRED": "APPROVED",
        "INCOMPLETE_INFO": "AWAITING_DOCUMENTS",
        "NO_MATCHING_RULE": "OPEN",
    }.get(outcome, "OPEN")


# --------------------------------------------------------------------------- #
# Outbound dispatch
# --------------------------------------------------------------------------- #
def _dispatch_outbound(*, sender, phone_number_id, channel, case_result, case_id, patient_name) -> None:
    messages = case_result.get("messages", {})

    _send_patient_message(sender, phone_number_id, channel, messages)
    _send_doctor_card(messages)
    _send_audit_email(case_id, patient_name, case_result)


def _send_patient_message(sender, phone_number_id, channel, messages: Dict[str, Any]) -> None:
    body = messages.get("patient_message_body", "")
    buttons = messages.get("patient_message_buttons", []) or [{"id": "ack", "title": "Acknowledged"}]
    if not body:
        return

    if channel == CHANNEL_WHATSAPP:
        msg = channels.build_whatsapp_buttons(to=sender, body=body, buttons=buttons)
        try:
            channels.send_whatsapp(msg, phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID)
            return
        except Exception as exc:  # noqa: BLE001 - fall through to SMS
            log_event(logger, "warning", "whatsapp.send.failed", error=str(exc))

    try:
        channels.send_sms(sender, body)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "sms.send.failed", error=str(exc))


def _send_doctor_card(messages: Dict[str, Any]) -> None:
    body = messages.get("doctor_card_body", "")
    buttons = messages.get("doctor_card_buttons", []) or [{"id": "approve_slot", "title": "Approve"}]
    if not body:
        return
    for approver in config.clinic_approver_numbers():
        try:
            channels.send_rcs_action_card(approver, body, buttons)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "rcs.send.failed", error=str(exc))


def _send_audit_email(case_id: str, patient_name: str, case_result: Dict[str, Any]) -> None:
    messages = case_result.get("messages", {})
    headline = messages.get("audit_headline") or f"Prior-auth update for {patient_name}"
    detail_lines = messages.get("audit_detail_lines", [])
    recipients = config.ses_command_recipients()
    if not recipients or not config.SES_SENDER:
        log_event(logger, "info", "ses.skipped.unconfigured")
        return

    html_body = _render_audit_html(case_id, headline, detail_lines)
    text_body = f"{headline}\n\n" + "\n".join(detail_lines)
    signature = _sign_report(text_body)

    try:
        aws_clients.ses().send_email(
            FromEmailAddress=config.SES_SENDER,
            Destination={"ToAddresses": recipients},
            Content={
                "Simple": {
                    "Subject": {"Data": f"[CareRelay] {headline}"[:200], "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": html_body, "Charset": "UTF-8"},
                        "Text": {"Data": text_body + (f"\n\nKMS signature: {signature}" if signature else ""), "Charset": "UTF-8"},
                    },
                }
            },
        )
        log_event(logger, "info", "ses.sent", case_id=case_id)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "ses.send.failed", error=str(exc))


def _sign_report(text_body: str) -> Optional[str]:
    """KMS-sign the audit report text so auditors can verify it was
    generated by this pipeline and has not been altered. Uses the
    asymmetric RSA_2048 SIGN_VERIFY key created in storage_stack.py."""
    if not config.KMS_SIGNING_KEY_ID:
        return None
    try:
        import hashlib

        digest = hashlib.sha256(text_body.encode("utf-8")).digest()
        resp = aws_clients.kms().sign(
            KeyId=config.KMS_SIGNING_KEY_ID,
            Message=digest,
            MessageType="DIGEST",
            SigningAlgorithm="RSASSA_PKCS1_V1_5_SHA_256",
        )
        import base64

        return base64.b64encode(resp["Signature"]).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "kms.sign.failed", error=str(exc))
        return None


def _render_audit_html(case_id: str, headline: str, detail_lines: List[str]) -> str:
    import html as html_mod

    items = "".join(f"<li style='margin:4px 0;'>{html_mod.escape(str(d))}</li>" for d in detail_lines)
    return f"""<!DOCTYPE html>
<html><body style="font-family:Segoe UI,Arial,sans-serif;background:#f4f5f7;margin:0;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;border:1px solid #e3e6ea;">
    <div style="background:#0f1b2d;color:#fff;padding:16px 20px;">
      <div style="font-size:12px;letter-spacing:1.5px;opacity:.7;">CARERELAY &middot; AUDIT REPORT (KMS-SIGNED)</div>
      <div style="font-size:18px;font-weight:700;margin-top:4px;">{html_mod.escape(headline)}</div>
    </div>
    <div style="padding:18px 20px;">
      <div style="font-size:12px;color:#777;margin-bottom:10px;">Case ID: {html_mod.escape(case_id)}</div>
      <ul style="margin:0;padding-left:18px;color:#333;font-size:13px;line-height:1.6;">{items}</ul>
      <p style="margin-top:18px;font-size:11px;color:#999;">
        This report was signed with an asymmetric AWS KMS key (RSASSA_PKCS1_V1_5_SHA_256) for audit
        verification. This is an automated prior-authorization summary; verify before acting on it.
      </p>
    </div>
  </div>
</body></html>"""
