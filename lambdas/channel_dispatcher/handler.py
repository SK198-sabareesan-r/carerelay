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

from common import aws_clients, config, channels, transcript
from common.logging_utils import get_logger, log_event
from common.models import KIND_IMAGE, KIND_AUDIO, KIND_TEXT, KIND_BUTTON, CHANNEL_WHATSAPP

logger = get_logger("channel_dispatcher")

# Matches a 5-digit CPT code or an ADA dental code like D2740 in free text.
_CPT_PATTERN = re.compile(r"\b(D\d{4}|\d{5})\b")

_DEFAULT_PAYER_ID = "PAYER-ACME"

_AGENT_SESSION_PREFIX = "carerelay-case-"  # runtimeSessionId must be 33+ chars
_PENDING_TTL_SECONDS = 3 * 24 * 60 * 60  # 3 days - a patient who never replies to the
                                          # template request shouldn't block that
                                          # sender's intake forever


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

    button_payloads = [m.get("button_payload") for m in msgs if m.get("kind") == KIND_BUTTON and m.get("button_payload")]
    if button_payloads:
        # Button taps (quick-reply or list-picker selection) are handled as
        # their OWN interaction, never mixed into the same batch as a fresh
        # card photo/voice note/text - a button press means the patient is
        # responding to something we already sent, not starting a new
        # intake. See _handle_button_payload for what each known payload
        # does; anything unrecognized is logged and otherwise ignored.
        for payload in button_payloads:
            _handle_button_payload(sender, phone_number_id, channel, payload)
        return

    # STAFF-INITIATED FOLLOW-UP FLOW (the primary CareRelay workflow): if an
    # open follow-up case already exists for this sender (created by staff
    # via dashboard_api POST /followups), this inbound batch is the
    # patient's reply to our card/voice request - route it into that case's
    # flow rather than treating it as a brand-new cold intake.
    followup = _find_open_followup_case(sender)
    if followup:
        _process_followup_reply(sender, phone_number_id, channel, msgs, followup)
        return

    card_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_IMAGE and m.get("s3_media_key")), None)
    voice_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_AUDIO and m.get("s3_media_key")), None)
    voice_mime = next((m.get("media_mime") for m in msgs if m.get("kind") == KIND_AUDIO), None)
    text_parts = [m["text"] for m in msgs if m.get("kind") == KIND_TEXT and m.get("text")]
    combined_text = " ".join(text_parts)
    cpt_code = _extract_cpt_code(combined_text)

    # Merge this batch with any earlier partial intake for the same sender
    # (e.g. they already sent a card photo last time, now they're replying
    # with the procedure description we asked for) - see
    # _load_pending_intake / _save_pending_intake.
    pending = _load_pending_intake(sender)
    if pending:
        card_key = card_key or pending.get("card_key")
        voice_key = voice_key or pending.get("voice_key")
        voice_mime = voice_mime or pending.get("voice_mime")
        if not cpt_code and pending.get("cpt_code"):
            cpt_code = pending["cpt_code"]
        if not combined_text and pending.get("text"):
            combined_text = pending["text"]
        case_id = pending.get("case_id") or f"case-{uuid.uuid4().hex[:8]}"
    else:
        case_id = f"case-{uuid.uuid4().hex[:8]}"

    procedure_name = combined_text.strip()[:120] if combined_text.strip() else None

    # Both a card photo AND a procedure description (parsed from text/voice
    # transcript via cpt_code) are needed before the agent runs - rather
    # than silently defaulting to a placeholder procedure, ask the patient
    # for whichever is missing via a template message, and park this case
    # as pending so the NEXT message from them continues it instead of
    # starting over.
    missing_inputs = []
    if not card_key:
        missing_inputs.append("card_photo")
    if not cpt_code and not voice_key:
        # A voice note might still name the procedure once transcribed by
        # the agent - only ask for a text/voice description if neither a
        # CPT code NOR any voice note is present at all.
        missing_inputs.append("procedure_description")

    if missing_inputs:
        _save_pending_intake(
            sender, case_id=case_id, card_key=card_key, voice_key=voice_key,
            voice_mime=voice_mime, cpt_code=cpt_code, text=combined_text,
        )
        _request_missing_inputs(sender, phone_number_id, channel, missing_inputs)
        log_event(logger, "info", "intake.awaiting_patient_input", case_id=case_id, missing=missing_inputs)
        return

    _clear_pending_intake(sender)
    payload = {
        "case_id": case_id,
        "patient_name": _display_name(sender),
        "cpt_code": cpt_code or "",
        "procedure_name": procedure_name or "",
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
        phone_number_id=phone_number_id,
        patient_name=payload["patient_name"],
        cpt_code=cpt_code,
        procedure_name=procedure_name or "Unspecified procedure",
        payer_id=payload["payer_id"],
        case_result=case_result,
        card_key=card_key,
        voice_key=voice_key,
        narration=agent_response.get("narration"),
    )
    # The agent's case_result carries extracted_card/verification/messages
    # but NOT the cpt_code/procedure_name (those are the dispatcher's own
    # parsed values) - inject them so downstream consumers like the payer
    # prior-auth email have the full picture without a second lookup. Also
    # inject the owning hospital (Option A multi-tenancy) so the payer
    # letter shows the real hospital name, not a hardcoded CLINIC_NAME.
    from common import patient_directory

    _assoc = patient_directory.lookup_patient(sender) or {}
    case_result.setdefault("cpt_code", cpt_code)
    case_result.setdefault("procedure_name", procedure_name or "Unspecified procedure")
    case_result.setdefault("hospital_name", _assoc.get("hospital_name"))

    _record_inbound(case_id, msgs)
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


# --------------------------------------------------------------------------- #
# Staff-initiated follow-up flow (primary workflow)
# --------------------------------------------------------------------------- #
_FOLLOWUP_OPEN_STATUSES = {"AWAITING_INSURANCE_DOCS", "AWAITING_VOICE_NOTE", "PENDING_DOCTOR_APPROVAL"}


def _find_open_followup_case(sender: str) -> Optional[Dict[str, Any]]:
    """Return the most recent still-open follow-up case for this patient
    phone (created by staff via POST /followups), or None. 'Open' means it's
    still waiting on the patient / doctor - a SCHEDULED or DENIED case is
    done and won't capture new replies."""
    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    resp = table.scan(
        FilterExpression="patient_phone = :p AND attribute_exists(flow)",
        ExpressionAttributeValues={":p": sender},
    )
    candidates = [
        i for i in resp.get("Items", [])
        if str(i.get("flow", "")).startswith("followup")
        and i.get("status") in _FOLLOWUP_OPEN_STATUSES
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return candidates[0]


def _process_followup_reply(
    sender: str, phone_number_id: str, channel: str, msgs: List[Dict[str, Any]], case: Dict[str, Any]
) -> None:
    """Handle a patient's WhatsApp reply to a staff-initiated follow-up.

    Insured path: expects insurance card photo + voice note. Once both are
    in, run the agent (vision + transcription + rules verification), email
    the payer, and - if cleared (APPROVED/NOT_REQUIRED) - release the
    appointment date/time to the patient.

    Self-pay path: expects a voice note. Once in, transcribe it, move the
    case to PENDING_DOCTOR_APPROVAL, and send the doctor the approval card.
    The appointment date/time is released when the doctor taps Approve (see
    _handle_button_payload 'approve_slot')."""
    case_id = case["case_id"]
    has_insurance = bool(case.get("has_insurance"))

    card_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_IMAGE and m.get("s3_media_key")), None)
    voice_key = next((m["s3_media_key"] for m in msgs if m.get("kind") == KIND_AUDIO and m.get("s3_media_key")), None)
    voice_mime = next((m.get("media_mime") for m in msgs if m.get("kind") == KIND_AUDIO), None)
    text_parts = [m["text"] for m in msgs if m.get("kind") == KIND_TEXT and m.get("text")]
    combined_text = " ".join(text_parts)

    _record_inbound(case_id, msgs)

    # Merge with anything already received on earlier turns for this case.
    card_key = card_key or case.get("photo_key")
    voice_key = voice_key or case.get("audio_key")

    if has_insurance:
        missing = []
        if not card_key:
            missing.append("card_photo")
        if not voice_key and not combined_text:
            missing.append("symptom_voice_note")
        if missing:
            _persist_followup_partial(case_id, card_key=card_key, voice_key=voice_key)
            _request_followup_inputs(sender, phone_number_id, channel, missing, case_id=case_id)
            log_event(logger, "info", "followup.awaiting_more", case_id=case_id, missing=missing)
            return
        _run_insured_followup(sender, phone_number_id, channel, case, card_key, voice_key, voice_mime, combined_text)
        return

    # Self-pay: just need a voice note (or text) describing the reason.
    if not voice_key and not combined_text:
        _request_followup_inputs(sender, phone_number_id, channel, ["symptom_voice_note"], case_id=case_id)
        log_event(logger, "info", "followup.awaiting_more", case_id=case_id, missing=["symptom_voice_note"])
        return
    _run_selfpay_followup(sender, phone_number_id, channel, case, voice_key, voice_mime, combined_text)


def _record_inbound(case_id: str, msgs: List[Dict[str, Any]]) -> None:
    """Add a transcript bubble for each inbound patient message in this
    batch (text/voice/image), so the console WhatsApp thread shows exactly
    what the patient sent, in order."""
    bubbles = []
    for m in msgs:
        kind = m.get("kind")
        if kind == KIND_TEXT and m.get("text"):
            bubbles.append(transcript.make_bubble(
                transcript.DIRECTION_INBOUND, m["text"], kind="text", actor="patient"))
        elif kind == KIND_AUDIO:
            bubbles.append(transcript.make_bubble(
                transcript.DIRECTION_INBOUND, "Voice note", kind="audio", actor="patient"))
        elif kind == KIND_IMAGE:
            bubbles.append(transcript.make_bubble(
                transcript.DIRECTION_INBOUND, "Insurance card photo", kind="image", actor="patient"))
    if bubbles:
        transcript.append_bubbles(case_id, bubbles)


def _persist_followup_partial(case_id: str, *, card_key, voice_key) -> None:
    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    updates, vals = [], {}
    if card_key:
        updates.append("photo_key = :c")
        vals[":c"] = card_key
    if voice_key:
        updates.append("audio_key = :a")
        vals[":a"] = voice_key
    if updates:
        table.update_item(
            Key={"case_id": case_id},
            UpdateExpression="SET " + ", ".join(updates),
            ExpressionAttributeValues=vals,
        )


def _request_followup_inputs(
    sender: str, phone_number_id: str, channel: str, missing: List[str], case_id: Optional[str] = None
) -> None:
    labels = {
        "card_photo": "- A clear photo of your insurance card (front side)",
        "symptom_voice_note": "- A short voice note describing your symptoms / reason for the visit",
    }
    body = "Thanks! We still need:\n" + "\n".join(labels[m] for m in missing if m in labels)
    _send_text_or_sms(sender, phone_number_id, channel, body, case_id=case_id)


def _run_insured_followup(sender, phone_number_id, channel, case, card_key, voice_key, voice_mime, combined_text) -> None:
    """Insured path: run the agent to extract card + transcribe voice +
    verify prior-auth, persist the result onto the existing case, email the
    payer, and release the appointment date/time if cleared."""
    case_id = case["case_id"]
    cpt_code = case.get("cpt_code") or _extract_cpt_code(combined_text) or _DEFAULT_CPT_CODE
    procedure_name = case.get("procedure_name") or (combined_text.strip()[:120] or _DEFAULT_PROCEDURE_NAME)
    payer_id = case.get("payer_id") or _DEFAULT_PAYER_ID

    payload = {
        "case_id": case_id,
        "patient_name": case.get("patient_name") or _display_name(sender),
        "cpt_code": cpt_code,
        "procedure_name": procedure_name,
        "payer_id": payer_id,
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
        log_event(logger, "warning", "followup.agent.no_output", case_id=case_id)
        return

    verification = case_result.get("verification", {})
    outcome = verification.get("outcome", "NO_MATCHING_RULE")
    case_result.setdefault("cpt_code", cpt_code)
    case_result.setdefault("procedure_name", procedure_name)
    case_result.setdefault("hospital_name", case.get("hospital_name"))

    _update_followup_after_agent(case_id, case_result, card_key, voice_key, outcome, has_insurance=True)

    # Doctor card + audit email + payer email (payer only if prior auth required).
    _send_doctor_card(case_result.get("messages", {}))
    _send_audit_email(case_id, case.get("patient_name", ""), case_result)
    if outcome == "PRIOR_AUTH_REQUIRED":
        _send_payer_prior_auth_request(case_id, case.get("patient_name", ""), case_result)

    # Insurance "cleared" = NOT_REQUIRED (no auth needed) or PRIOR_AUTH_REQUIRED
    # with all docs present (the rules engine already confirmed completeness).
    if outcome in ("NOT_REQUIRED", "PRIOR_AUTH_REQUIRED"):
        _release_appointment(case, sender, phone_number_id, cleared_note="Your insurance has been verified.")
    else:
        # INCOMPLETE_INFO / NO_MATCHING_RULE: tell the patient we're still working on it.
        body = ("Thanks - we've received your details and are completing your insurance "
                "verification. We'll confirm your appointment time shortly.")
        _send_text_or_sms(sender, phone_number_id, channel, body, case_id=case_id)


def _run_selfpay_followup(sender, phone_number_id, channel, case, voice_key, voice_mime, combined_text) -> None:
    """Self-pay path: transcribe the voice note (via the agent, which also
    drafts the doctor card), move to PENDING_DOCTOR_APPROVAL, and send the
    doctor the approval card. Appointment released on doctor approval."""
    case_id = case["case_id"]
    procedure_name = case.get("procedure_name") or (combined_text.strip()[:120] or "Follow-up visit")

    # Reuse the agent only to transcribe + draft the doctor card. No payer,
    # no rules verification for self-pay. If AgentCore isn't deployed, we
    # still proceed with a minimal doctor card built from what we have.
    payload = {
        "case_id": case_id,
        "patient_name": case.get("patient_name") or _display_name(sender),
        "cpt_code": case.get("cpt_code") or "",
        "procedure_name": procedure_name,
        "payer_id": "SELF_PAY",
        "documents_on_file": [],
        "self_pay": True,
    }
    if voice_key:
        payload["voice_s3_bucket"] = config.MEDIA_BUCKET
        payload["voice_s3_key"] = voice_key
        payload["voice_media_format"] = _media_format(voice_mime, voice_key)

    agent_response = _invoke_agent(case_id, payload)
    case_result = agent_response.get("case_result") or {}
    symptom_summary = case_result.get("symptom_summary") or (combined_text.strip() or None)

    # Build the doctor card (prefer agent-drafted, else a minimal one).
    messages = case_result.get("messages") or {}
    if not messages.get("doctor_card_body"):
        lines = [f"Patient: {case.get('patient_name') or _display_name(sender)} (SELF-PAY)"]
        if symptom_summary:
            lines.append(f"Reported symptoms: {symptom_summary}")
        lines.append(f"Procedure: {procedure_name}")
        lines.append("No insurance - self-pay visit awaiting your approval.")
        messages = {
            "doctor_card_body": "\n".join(lines),
            "doctor_card_buttons": [
                {"id": "approve_slot", "title": "Approve Visit"},
                {"id": "request_notes", "title": "Request Notes"},
            ],
        }

    _update_followup_after_agent(
        case_id, {"messages": messages, "symptom_summary": symptom_summary, "verification": {}},
        None, voice_key, "SELF_PAY", has_insurance=False, status="PENDING_DOCTOR_APPROVAL",
    )
    _send_doctor_card(messages)

    body = ("Thank you - we've shared your details with the doctor for approval. "
            "We'll confirm your appointment time shortly.")
    _send_text_or_sms(sender, phone_number_id, channel, body, case_id=case_id)
    log_event(logger, "info", "followup.selfpay.pending_doctor", case_id=case_id)


def _update_followup_after_agent(case_id, case_result, card_key, voice_key, outcome, *, has_insurance, status=None) -> None:
    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    if status is None:
        status = _status_for_outcome(outcome)
    expr = {
        ":s": status,
        ":v": case_result.get("verification", {}),
        ":m": case_result.get("messages", {}),
        ":ec": case_result.get("extracted_card", {}),
        ":pf": [case_result["symptom_summary"]] if case_result.get("symptom_summary") else [],
    }
    sets = ["#s = :s", "verification = :v", "messages = :m", "extracted_card = :ec", "perceived_facts = :pf"]
    if card_key:
        sets.append("photo_key = :pk")
        expr[":pk"] = card_key
    if voice_key:
        sets.append("audio_key = :ak")
        expr[":ak"] = voice_key
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    sets.append("activity_log = list_append(if_not_exists(activity_log, :emptylog), :entry)")
    expr[":emptylog"] = []
    expr[":entry"] = [{
        "timestamp": now,
        "event": "AGENT_PROCESSED",
        "actor": "agent",
        "detail": f"Patient reply processed; outcome={outcome}, status={status}.",
    }]
    table.update_item(
        Key={"case_id": case_id},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues=expr,
    )


def _release_appointment(case: Dict[str, Any], sender: str, phone_number_id: str, cleared_note: str) -> None:
    """Send the patient the WITHHELD appointment date/time and mark the
    case SCHEDULED + appointment_released. This is the only place the
    patient ever learns their slot."""
    case_id = case["case_id"]
    appt = case.get("appointment_datetime", "")
    procedure = case.get("procedure_name", "your procedure")
    clinic = case.get("hospital_name") or config._get("CLINIC_NAME", "the clinic")  # noqa: SLF001

    try:
        msg = channels.build_whatsapp_appointment_confirmation(
            to=sender,
            appointment_datetime_display=appt,
            procedure_name=procedure,
            clinic_name=clinic,
            cleared_note=cleared_note,
        )
        channels.send_whatsapp(msg, phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID)
        transcript.append(
            case_id, transcript.DIRECTION_OUTBOUND,
            f"{cleared_note} You're all set for your {procedure} at {clinic}.\n\n"
            f"Please come in on: {appt}\n\nArrive 15 minutes early.",
            kind="text", actor="system",
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "appointment.release.send_failed", case_id=case_id, error=str(exc))

    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    table.update_item(
        Key={"case_id": case_id},
        UpdateExpression="SET #s = :s, appointment_released = :r, activity_log = list_append(if_not_exists(activity_log, :e), :entry)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "SCHEDULED",
            ":r": True,
            ":e": [],
            ":entry": [{
                "timestamp": now,
                "event": "APPOINTMENT_RELEASED",
                "actor": "system",
                "detail": f"Appointment {appt} confirmed to patient ({cleared_note.strip()}).",
            }],
        },
    )
    log_event(logger, "info", "appointment.released", case_id=case_id)


def _handle_doctor_decision(approver: str, phone_number_id: str, channel: str, payload: str) -> None:
    """A doctor tapped Approve / Request-Notes on a self-pay follow-up card.
    The tap arrives from the DOCTOR's number, so we find the case by its
    PENDING_DOCTOR_APPROVAL state (oldest first), not by phone match.

    Approve -> release the withheld appointment date/time to the patient.
    Request-Notes -> leave the case pending and ask the patient for more
    detail."""
    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    resp = table.scan(
        FilterExpression="#s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": "PENDING_DOCTOR_APPROVAL"},
    )
    pending = resp.get("Items", [])
    if not pending:
        log_event(logger, "warning", "doctor_decision.no_pending_case", payload=payload)
        return
    pending.sort(key=lambda i: str(i.get("created_at", "")))
    case = pending[0]
    case_id = case["case_id"]
    patient_phone = case.get("patient_phone")

    if payload == "approve_slot":
        if patient_phone:
            _release_appointment(case, patient_phone, config.WHATSAPP_PHONE_NUMBER_ID,
                                 cleared_note="Your visit has been approved by the doctor.")
        _append_case_note(patient_phone or "", "DOCTOR_APPROVED", "doctor",
                          "Doctor approved the self-pay follow-up visit; appointment released.")
        log_event(logger, "info", "doctor_decision.approved", case_id=case_id)
    else:  # request_notes
        if patient_phone:
            body = ("Your doctor would like a bit more detail before confirming. Please reply with "
                    "another short voice note describing your symptoms and how long you've had them.")
            _send_text_or_sms(patient_phone, config.WHATSAPP_PHONE_NUMBER_ID, CHANNEL_WHATSAPP, body)
        _append_case_note(patient_phone or "", "DOCTOR_REQUESTED_NOTES", "doctor",
                          "Doctor requested more detail; patient asked for an additional voice note.")
        log_event(logger, "info", "doctor_decision.requested_notes", case_id=case_id)


# --------------------------------------------------------------------------- #
# Button / list-picker reply handling
# --------------------------------------------------------------------------- #
def _handle_button_payload(sender: str, phone_number_id: str, channel: str, payload: str) -> None:
    # Doctor-facing approval buttons (tapped from the APPROVER's phone, not
    # the patient's) for a self-pay follow-up awaiting doctor sign-off.
    if payload in ("approve_slot", "request_notes"):
        _handle_doctor_decision(sender, phone_number_id, channel, payload)
        return

    if payload == "start_verification":
        _request_missing_inputs(sender, phone_number_id, channel, ["card_photo", "procedure_description"])
        log_event(logger, "info", "button.start_verification", sender=sender)
        return

    if payload == "reschedule":
        _append_case_note(sender, "RESCHEDULE_REQUESTED", "patient",
                           "Patient tapped 'Reschedule' on the appointment reminder.")
        body = "No problem - our front desk will reach out shortly to find a new time for your visit."
        _send_text_or_sms(sender, phone_number_id, channel, body)
        log_event(logger, "info", "button.reschedule", sender=sender)
        return

    if payload == "consent_submit_auth":
        _append_case_note(sender, "CONSENT_GIVEN", "patient",
                           "Patient authorized the clinic to submit the prior-authorization request to their insurer.")
        body = "Thank you - we've recorded your authorization and will submit this to your insurer."
        _send_text_or_sms(sender, phone_number_id, channel, body)
        log_event(logger, "info", "button.consent_submit_auth", sender=sender)
        return

    if payload.startswith("pickup_"):
        pharmacy_id = payload[len("pickup_"):]
        pharmacy = next((p for p in _load_pharmacies() if p["pharmacy_id"] == pharmacy_id), None)
        pharmacy_name = pharmacy["name"] if pharmacy else pharmacy_id
        _append_case_note(sender, "PHARMACY_SELECTED", "patient",
                           f"Patient selected pharmacy pickup: {pharmacy_name}.")
        body = f"Got it - we've noted {pharmacy_name} for your medication pickup."
        _send_text_or_sms(sender, phone_number_id, channel, body)
        log_event(logger, "info", "button.pharmacy_selected", sender=sender, pharmacy_id=pharmacy_id)
        return

    log_event(logger, "warning", "button.unrecognized_payload", sender=sender, payload=payload)


def _send_text_or_sms(sender: str, phone_number_id: str, channel: str, body: str,
                      case_id: Optional[str] = None) -> None:
    sent = False
    if channel == CHANNEL_WHATSAPP:
        msg = channels.build_whatsapp_text(to=sender, body=body)
        try:
            channels.send_whatsapp(msg, phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID)
            sent = True
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "whatsapp.send.failed", error=str(exc))
    if not sent:
        try:
            channels.send_sms(sender, body)
            sent = True
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "sms.send.failed", error=str(exc))
    if sent and case_id:
        transcript.append(case_id, transcript.DIRECTION_OUTBOUND, body, kind="text", actor="system")


def _append_case_note(sender: str, event: str, actor: str, detail: str) -> None:
    """Appends an activity_log entry to the sender's MOST RECENT case
    (newest created_at) - a button tap is always a reply to something
    already sent about a specific case, so this is a best-effort match by
    recency rather than a stored session id. If no case exists yet for
    this sender (e.g. they tapped a stale button), this is a no-op."""
    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    resp = table.scan(FilterExpression="patient_phone = :p", ExpressionAttributeValues={":p": sender})
    items = resp.get("Items", [])
    if not items:
        return
    items.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    case_id = items[0]["case_id"]
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "actor": actor,
        "detail": detail,
    }
    table.update_item(
        Key={"case_id": case_id},
        UpdateExpression="SET activity_log = list_append(if_not_exists(activity_log, :empty), :entry)",
        ExpressionAttributeValues={":empty": [], ":entry": [entry]},
    )


# --------------------------------------------------------------------------- #
# Pending intake tracking (multi-turn: card photo + procedure description
# can arrive in separate messages, possibly minutes/hours apart)
# --------------------------------------------------------------------------- #
def _pending_key(sender: str) -> Dict[str, str]:
    return {"pk": f"PATIENT#{sender}", "sk": "PENDING#intake"}


def _load_pending_intake(sender: str) -> Optional[Dict[str, Any]]:
    table = aws_clients.dynamodb_resource().Table(config.INTAKE_EVENTS_TABLE)
    resp = table.get_item(Key=_pending_key(sender))
    return resp.get("Item")


def _save_pending_intake(
    sender: str, *, case_id: str, card_key: Optional[str], voice_key: Optional[str],
    voice_mime: Optional[str], cpt_code: Optional[str], text: str,
) -> None:
    table = aws_clients.dynamodb_resource().Table(config.INTAKE_EVENTS_TABLE)
    item = {
        **_pending_key(sender),
        "case_id": case_id,
        "card_key": card_key,
        "voice_key": voice_key,
        "voice_mime": voice_mime,
        "cpt_code": cpt_code,
        "text": text,
        "ttl": int(time.time()) + _PENDING_TTL_SECONDS,
    }
    table.put_item(Item={k: v for k, v in item.items() if v not in (None, "")})


def _clear_pending_intake(sender: str) -> None:
    table = aws_clients.dynamodb_resource().Table(config.INTAKE_EVENTS_TABLE)
    table.delete_item(Key=_pending_key(sender))


def _request_missing_inputs(sender: str, phone_number_id: str, channel: str, missing: List[str]) -> None:
    """Sends ONE combined template message (not one per missing item) asking
    the patient for whatever we still need, mirroring the real messages a
    front-desk would send: "please send a photo of your insurance card"
    and/or "please tell us (text or voice note) what procedure this is
    for". Uses channels.build_whatsapp_text - no model involved in
    deciding what to ask for, only in how the final verification result
    gets phrased later."""
    lines = []
    if "card_photo" in missing:
        lines.append("- A clear photo of your insurance card (front side)")
    if "procedure_description" in missing:
        lines.append("- What procedure or visit this is for (a short text message or voice note is fine)")

    body = (
        "Thanks for reaching out. To continue processing your prior authorization, "
        "please send us:\n" + "\n".join(lines)
    )

    if channel == CHANNEL_WHATSAPP:
        msg = channels.build_whatsapp_text(to=sender, body=body)
        try:
            channels.send_whatsapp(msg, phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID)
            return
        except Exception as exc:  # noqa: BLE001 - fall through to SMS
            log_event(logger, "warning", "whatsapp.send.failed", error=str(exc))

    try:
        channels.send_sms(sender, body)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "sms.send.failed", error=str(exc))


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
    *, case_id, sender, channel, phone_number_id, patient_name, cpt_code, procedure_name,
    payer_id, case_result, card_key, voice_key, narration,
) -> None:
    verification = case_result.get("verification", {})
    outcome = verification.get("outcome", "NO_MATCHING_RULE")
    status = _status_for_outcome(outcome)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Multi-tenancy (Option A): tag the case with the hospital this patient
    # belongs to, looked up from PatientsTable (populated when the hospital's
    # staff first created an appointment / sent a reminder - see
    # common/patient_directory.py). Falls back to None if the patient was
    # never associated (cold inbound), which downstream consumers handle.
    from common import patient_directory

    association = patient_directory.lookup_patient(sender) or {}
    hospital_id = association.get("hospital_id")
    hospital_name = association.get("hospital_name")

    table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
    item = {
        "case_id": case_id,
        "created_at": now,
        "status": status,
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "patient_name": patient_name,
        "patient_phone_masked": f"***{sender[-4:]}" if len(sender) >= 4 else sender,
        # Raw sender number, stored ONLY so dashboard_api's
        # POST /cases/{id}/message route can let staff reply over WhatsApp.
        # Never returned by dashboard_api._present() - patient_phone_masked
        # is the only phone field the frontend ever sees.
        "patient_phone": sender if channel == CHANNEL_WHATSAPP else None,
        "phone_number_id": phone_number_id if channel == CHANNEL_WHATSAPP else None,
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
        "activity_log": [{
            "timestamp": now,
            "event": "CREATED",
            "actor": "system",
            "detail": f"Case created from {channel} intake and verified by the agent pipeline.",
        }],
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
    verification = case_result.get("verification", {})

    _send_patient_message(sender, phone_number_id, channel, messages)
    if messages.get("patient_message_body"):
        transcript.append(case_id, transcript.DIRECTION_OUTBOUND,
                          messages["patient_message_body"], kind="text", actor="agent")
    _send_doctor_card(messages)
    _send_audit_email(case_id, patient_name, case_result)

    # When the rules engine says prior auth IS required, send the formal
    # written prior-authorization request to the payer's intake inbox
    # (distinct from the internal audit email above). This is the "email
    # the insurance payer" leg of the flow.
    if verification.get("outcome") == "PRIOR_AUTH_REQUIRED":
        _send_payer_prior_auth_request(case_id, patient_name, case_result)

    # Deterministic, NOT model-drafted: offer the prior-auth consent /
    # pharmacy list picker only when prior authorization is actually
    # required. Fires as a SEPARATE follow-up message after the status
    # update, mirroring how a front-desk would first tell you the result,
    # then ask what you want to do about it.
    if verification.get("outcome") == "PRIOR_AUTH_REQUIRED" and channel == CHANNEL_WHATSAPP:
        _send_prior_auth_consent_picker(sender, phone_number_id, case_id)


def _send_payer_prior_auth_request(case_id: str, patient_name: str, case_result: Dict[str, Any]) -> None:
    from . import payer_email

    card = case_result.get("extracted_card", {}) or {}
    verification = case_result.get("verification", {}) or {}
    clinic_name = case_result.get("hospital_name") or config._get("CLINIC_NAME", "CareRelay Clinic")  # noqa: SLF001
    payer_label = card.get("payer_name") or case_result.get("payer_id") or "the payer"
    ctx = {
        "case_id": case_id,
        "patient_name": patient_name,
        "payer_name": card.get("payer_name"),
        "payer_id": card.get("payer_id"),
        "member_id": card.get("member_id"),
        "group_number": card.get("group_number"),
        "cpt_code": case_result.get("cpt_code"),
        "procedure_name": case_result.get("procedure_name"),
        "matched_rule_id": verification.get("matched_rule_id"),
        "rationale": verification.get("rationale"),
        "clinical_summary": case_result.get("symptom_summary"),
        "missing_documents": verification.get("missing_documents", []),
        # Dynamic per Option A: the owning hospital tagged on the case.
        # Falls back to CLINIC_NAME only if this patient was never
        # associated with a hospital (cold inbound).
        "clinic_name": clinic_name,
    }
    subject = (
        f"Prior Authorization Request - {case_result.get('procedure_name') or 'procedure'} "
        f"(CPT {case_result.get('cpt_code') or 'n/a'})"
    )
    message_id = payer_email.send_payer_prior_auth_request(ctx)

    # Record the outbound request on the case so the console can show the
    # full hospital <-> payer email correspondence with timestamps.
    sender = config.SES_SENDER or "clinic@carerelay"
    recipient = config._get("PAYER_PRIOR_AUTH_INBOX", "priorauth@payer.example.com")  # noqa: SLF001
    _record_payer_email(
        case_id,
        direction="outbound",
        subject=subject,
        from_addr=sender,
        to_addr=recipient,
        from_label=clinic_name,
        to_label=payer_label,
        body=(
            f"Formal prior-authorization request sent to {payer_label} for "
            f"{case_result.get('procedure_name') or 'the procedure'} "
            f"(CPT {case_result.get('cpt_code') or 'n/a'}, member "
            f"{card.get('member_id') or 'n/a'}). Clinical justification and the matched coverage "
            f"rule ({verification.get('matched_rule_id') or 'n/a'}) were included."
        ),
        message_id=message_id,
    )

    # Record the payer's determination as the inbound reply, using the
    # deterministic verification result (eligible / approval code).
    eligible = verification.get("payer_eligible")
    approval = verification.get("approval_code")
    if eligible is False:
        reply_body = (
            "Prior authorization could not be confirmed at this time. Additional clinical "
            "documentation may be required before a determination is issued."
        )
    else:
        reply_body = (
            "Prior authorization APPROVED for the requested procedure."
            + (f" Authorization reference: {approval}." if approval else "")
            + " Please proceed and retain this reference for claims submission."
        )
    _record_payer_email(
        case_id,
        direction="inbound",
        subject=f"RE: {subject}",
        from_addr=recipient,
        to_addr=sender,
        from_label=payer_label,
        to_label=clinic_name,
        body=reply_body,
        message_id=None,
    )


def _record_payer_email(
    case_id: str, *, direction: str, subject: str, from_addr: str, to_addr: str,
    from_label: str, to_label: str, body: str, message_id: Optional[str],
) -> None:
    """Append one email to the case's payer_emails correspondence log. Each
    entry carries from/to, a subject, a body summary, a timestamp, and the
    direction (outbound = clinic->payer, inbound = payer->clinic). Best
    effort - never breaks case handling."""
    entry = {
        "direction": direction,
        "subject": subject[:200],
        "from_addr": from_addr,
        "to_addr": to_addr,
        "from_label": from_label,
        "to_label": to_label,
        "body": body[:2000],
        "message_id": message_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
        table.update_item(
            Key={"case_id": case_id},
            UpdateExpression="SET payer_emails = list_append(if_not_exists(payer_emails, :e), :entry)",
            ExpressionAttributeValues={":e": [], ":entry": [entry]},
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "payer_email.record.failed", case_id=case_id, error=str(exc))


def _send_prior_auth_consent_picker(sender: str, phone_number_id: str, case_id: str) -> None:
    """WhatsApp List Message offering: authorize the clinic to submit the
    Prior-Auth request to the insurer, or pick a pharmacy for medication
    pickup. See channels.build_whatsapp_list_picker and seed/pharmacies.json
    (loaded once per container, not re-read from disk on the hot path -
    this is demo-scale static data, not something that changes per
    request)."""
    pharmacies = _load_pharmacies()
    rows = [
        {"id": f"pickup_{p['pharmacy_id']}", "title": p["name"], "description": p.get("address", "")}
        for p in pharmacies
    ]
    sections = [
        {
            "title": "Prior authorization",
            "rows": [{
                "id": "consent_submit_auth",
                "title": "Authorize submission",
                "description": "Let the clinic submit this to your insurer",
            }],
        },
        {"title": "Pharmacy pickup", "rows": rows},
    ]
    msg = channels.build_whatsapp_list_picker(
        to=sender,
        body="Would you like to authorize the clinic to submit this prior-authorization request, "
             "or choose a pharmacy for medication pickup?",
        button_label="Choose an option",
        sections=sections,
        header="Next steps",
    )
    try:
        channels.send_whatsapp(msg, phone_number_id or config.WHATSAPP_PHONE_NUMBER_ID)
        log_event(logger, "info", "consent_picker.sent", case_id=case_id)
    except Exception as exc:  # noqa: BLE001 - this is a convenience follow-up, never fail the case over it
        log_event(logger, "warning", "consent_picker.send.failed", error=str(exc))


def _load_pharmacies() -> List[Dict[str, str]]:
    """Reads seed/pharmacies.json, bundled into the deployment zip
    alongside this handler at channel_dispatcher/seed_pharmacies.json by
    scripts/deploy_channel_dispatcher.py (the zip's filesystem layout is
    flat, not a copy of the repo tree, so this reads relative to this
    file's own directory - not via a repo-root-relative path)."""
    if not hasattr(_load_pharmacies, "_cache"):
        import os

        seed_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_pharmacies.json")
        try:
            with open(seed_path, "r", encoding="utf-8") as fh:
                _load_pharmacies._cache = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "pharmacies.load.failed", error=str(exc))
            _load_pharmacies._cache = []
    return _load_pharmacies._cache


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
        _send_doctor_card_to(approver, body, buttons)


# E.164 country-code prefixes where AWS End User Messaging supports RCS
# (per https://docs.aws.amazon.com/sms-voice/latest/userguide/rcs-supported-countries.html).
# Longest-prefix match. A doctor number NOT matching any of these (e.g. an
# Indian +91 number) can't receive RCS through AWS, so the card is routed
# over WhatsApp instead - which does reach those countries.
_RCS_SUPPORTED_PREFIXES = (
    "+1",    # US / Canada
    "+44",   # UK
    "+43", "+420", "+45", "+33", "+49", "+39", "+31", "+47", "+48", "+421", "+34", "+46",  # EU
    "+55",   # Brazil
    "+52",   # Mexico
    "+57",   # Colombia
    "+1809", "+1829", "+1849",  # Dominican Republic
    "+502",  # Guatemala
    "+51",   # Peru
    "+65",   # Singapore
)


def _rcs_supported(number: str) -> bool:
    n = number.strip()
    return any(n.startswith(p) for p in sorted(_RCS_SUPPORTED_PREFIXES, key=len, reverse=True))


def _send_doctor_card_to(approver: str, body: str, buttons: List[Dict[str, str]]) -> None:
    """Deliver the doctor approval card over the best channel that actually
    reaches `approver`:
      - RCS (real tappable rich card) if the number is in an AWS-RCS-supported
        country.
      - WhatsApp interactive buttons otherwise (e.g. India +91, where AWS
        doesn't offer RCS) - the same Approve / Request-Notes buttons, just
        delivered on a channel that works there.
    Honest by construction: we never pretend to send RCS where it can't land."""
    if _rcs_supported(approver):
        try:
            channels.send_rcs_action_card(approver, body, buttons)
            log_event(logger, "info", "doctor_card.sent", channel="rcs", to_masked=f"***{approver[-4:]}")
            return
        except Exception as exc:  # noqa: BLE001 - fall through to WhatsApp
            log_event(logger, "warning", "doctor_card.rcs.failed", error=str(exc))

    # WhatsApp interactive-button fallback (RCS-unsupported country, or RCS send failed).
    try:
        msg = channels.build_whatsapp_buttons(
            to=approver,
            body=body,
            buttons=buttons,
            header="Clinical Approval",
        )
        channels.send_whatsapp(msg, config.WHATSAPP_PHONE_NUMBER_ID)
        log_event(logger, "info", "doctor_card.sent", channel="whatsapp", to_masked=f"***{approver[-4:]}")
        return
    except Exception as exc:  # noqa: BLE001 - last resort SMS
        log_event(logger, "warning", "doctor_card.whatsapp.failed", error=str(exc))

    try:
        chips = "  ".join(f"[{b['title']}]" for b in buttons)
        channels.send_sms(approver, f"{body}\n{chips}" if chips else body)
        log_event(logger, "info", "doctor_card.sent", channel="sms", to_masked=f"***{approver[-4:]}")
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "doctor_card.sms.failed", error=str(exc))


def _send_audit_email(case_id: str, patient_name: str, case_result: Dict[str, Any]) -> None:
    messages = case_result.get("messages", {})
    headline = messages.get("audit_headline") or f"Prior-auth update for {patient_name}"
    detail_lines = messages.get("audit_detail_lines", [])
    recipients = config.resolve_ses_recipients(config.ses_command_recipients())
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

    year = time.strftime("%Y")
    signed = bool(config.KMS_SIGNING_KEY_ID)
    items = "".join(
        f"<tr><td style='padding:7px 0;border-bottom:1px solid #f1f5f4;"
        f"font-size:13px;line-height:1.6;color:#334155;'>{html_mod.escape(str(d))}</td></tr>"
        for d in detail_lines
    )
    # Only claim KMS signing when a signing key is actually configured -
    # the text body appends the real signature in the same condition.
    sign_badge = (
        "<span style='display:inline-block;background:#ccfbf1;color:#0f766e;font-size:10px;"
        "font-weight:700;letter-spacing:0.5px;text-transform:uppercase;padding:3px 8px;"
        "border-radius:999px;'>KMS-signed</span>"
        if signed else ""
    )
    sign_note = (
        "<p style='margin:16px 0 0;font-size:11px;line-height:1.5;color:#94a3b8;'>"
        "Signed with an asymmetric AWS KMS key (RSASSA_PKCS1_V1_5_SHA_256) for audit verification. "
        "This is an automated prior-authorization summary; verify before acting on it.</p>"
        if signed else
        "<p style='margin:16px 0 0;font-size:11px;line-height:1.5;color:#94a3b8;'>"
        "This is an automated prior-authorization summary; verify before acting on it.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><body style="margin:0;padding:0;background:#eef2f1;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f1;padding:0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;">

        <tr>
          <td style="background-color:#0f766e;background:linear-gradient(135deg,#0f766e 0%,#14b8a6 100%);padding:24px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>
              <td width="30" height="30" bgcolor="#ffffff" style="width:30px;height:30px;border-radius:7px;text-align:center;vertical-align:middle;font-size:16px;font-weight:700;color:#0f766e;">+</td>
              <td style="padding-left:10px;" valign="middle">
                <span style="color:#ffffff;font-size:18px;font-weight:700;">CareRelay</span>
              </td>
              <td align="right" valign="middle">{sign_badge}</td>
            </tr></table>
            <div style="color:#d7f3ee;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;margin-top:16px;">Case audit report</div>
            <h1 style="margin:4px 0 0;color:#ffffff;font-size:19px;line-height:1.3;font-weight:700;">{html_mod.escape(headline)}</h1>
          </td>
        </tr>

        <tr>
          <td style="padding:24px 32px 8px;">
            <div style="display:inline-block;background:#f0fdfa;border:1px solid #ccfbf1;border-radius:8px;padding:6px 12px;font-size:12px;color:#0f766e;font-weight:700;font-family:Consolas,Menlo,monospace;">
              Case {html_mod.escape(case_id)}
            </div>
            <table width="100%" cellpadding="0" cellspacing="0" style="margin-top:14px;">{items}</table>
            {sign_note}
          </td>
        </tr>

        <tr>
          <td style="background-color:#0b2b27;padding:16px 32px;text-align:center;">
            <span style="color:#ffffff;font-size:12px;font-weight:700;">CareRelay</span>
            <p style="margin:5px 0 0;color:#8fb0ac;font-size:10px;">Automated case audit report &copy; {year} CareRelay.</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body></html>"""
