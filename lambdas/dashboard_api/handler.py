"""dashboard_api Lambda - API backing the CareRelay frontend application
(frontend/).

Routes (API Gateway proxy):
    GET   /cases                   -> list of cases, newest first
                                       optional ?from=YYYY-MM-DD&to=YYYY-MM-DD
                                       filters by created_at date (inclusive)
    GET   /cases/{id}              -> single case detail, incl. agent_trace
                                       and the full timestamped activity_log
    POST  /followups               -> staff starts the follow-up flow after an
                                       in-person consult (patient phone, procedure,
                                       intended appointment datetime, has_insurance).
                                       Creates the case pending + sends the first
                                       WhatsApp request (card+voice if insured,
                                       voice-only if self-pay). The appointment
                                       datetime is withheld from the patient until
                                       clearance/approval.
    POST  /cases                   -> manually log a new intake (staff-entered,
                                       e.g. a phone/walk-in case with no WhatsApp
                                       message behind it)
    PATCH /cases/{id}/status       -> update a case's status, appends an
                                       activity_log entry
    POST  /cases/{id}/message      -> staff sends a free-text WhatsApp message
                                       to the case's patient directly (outside
                                       the agent-drafted flow), appends an
                                       activity_log entry
    GET   /payer-rules             -> the deterministic PayerRulesTable contents
    POST  /payer-rules             -> add a new payer/CPT coverage rule
    GET   /stats                   -> aggregate counters for the analytics view
    POST  /auth/signup             -> create a clinic staff account
    POST  /auth/login              -> verify credentials, return the staff profile

StaffUsersTable item shape (written/read by the /auth/* routes only).
Composite key (hospital_id, username) - multiple hospitals can each register
their own staff without username collisions:
    {
      "hospital_id": "sunrisegeneralhospital",   # alphanumeric ID derived from hospital_name
      "hospital_name": "Sunrise General Hospital",
      "hospital_address": "221B Baker Street, Mumbai",
      "hospital_email": "contact@sunrise.example.com",
      "hospital_phone": "+919876543210",
      "username": "pnair",
      "display_name": "Dr. Priya Nair",
      "role": "Clinic Staff",
      "password_hash": "<hex>",          # PBKDF2-HMAC-SHA256, never plaintext
      "password_salt": "<hex>",
      "created_at": "2026-...Z",
    }

Signup collects the hospital's address/email/phone once per registration
(stored on every staff row for that hospital_id - no separate HospitalsTable,
same scope-reduction tradeoff as deriving hospital_id as a slug rather than
a generated ID). Login only requires hospital_id + username + password -
the frontend shows hospital_id as the "Hospital ID" field returned at signup
time, since asking a returning user to retype their exact hospital display
name (capitalization/punctuation-sensitive before slugging) is fragile UX.

This is a basic staff-portal credential store sized for a clinic command
console demo - not a hospital-grade identity system (no NPI/license
verification, no MFA, no session tokens/JWT). See docs/DASHBOARD.md for the
production-auth note (Cognito/SSO recommended for any real deployment).

MULTI-TENANCY SCOPE: signup/login ARE hospital-scoped (a username only needs
to be unique within its own hospital). Case data (PriorAuthTable) is NOT YET
filtered by hospital - channel_dispatcher does not currently tag cases with
a hospital_id, so /cases, /stats, and /payer-rules return the same global
data to every signed-in hospital. See docs/DASHBOARD.md "Multi-tenancy
status" for what a full per-hospital data boundary would require.

PriorAuthTable item shape (written by channel_dispatcher, read here):
    {
      "case_id": "...",
      "created_at": "2026-...Z",
      "status": "OPEN" | "APPROVED" | "DENIED" | "AWAITING_DOCUMENTS",
      "patient_name": "...",            # display name only, never raw PHI id
      "patient_phone_masked": "***1234",
      "patient_phone": "+1555...",      # raw number, WRITE-ONLY from this API's
                                         # perspective - used internally by
                                         # _handle_send_message to reply over
                                         # WhatsApp, never included in _present()
      "phone_number_id": "...",         # WhatsApp origination phone-number-id to reply from
      "channel": "whatsapp",
      "cpt_code": "29881",
      "procedure_name": "...",
      "payer_id": "PAYER-ACME",
      "extracted_card": {...},          # schemas.ExtractedCard
      "verification": {...},            # schemas.VerificationResult
      "messages": {...},                # schemas.DraftedMessages
      "perceived_facts": [...],         # symptom_summary + any notes
      "photo_key": "intake/.../card.jpg" (optional, S3 key),
      "audio_key": "intake/.../voice.ogg" (optional, S3 key),
      "narration": "...",               # raw agent narration, debug only
    }

Every case carries an `activity_log` - a list of timestamped entries
appended on creation and on every status change:
    {
      "timestamp": "2026-...Z",
      "event": "CREATED" | "STATUS_CHANGED" | ...,
      "actor": "staff:pnair" | "system" | "agent",
      "detail": "free-text description of what happened",
    }
This is the per-case audit trail the console timeline renders - every
change traces back to a logged, timestamped entry rather than being
inferred from the current state alone.

This Lambda also accepts a small set of staff-initiated writes (manual case
logging, status updates, payer-rule authoring) in addition to the
auth/read routes - it is intentionally NOT purely read-only, unlike an
earlier revision of this docstring.

SECURITY NOTE: unauthenticated by default so the demo/dashboard works with
zero setup. patient_phone_masked is pre-masked at write time by
channel_dispatcher; this API never returns the raw phone number. Add an
authorizer (Cognito/Lambda/API key) before any real deployment - see
docs/DASHBOARD.md. Because writes are unauthenticated, `actor` on
staff-initiated activity_log entries is self-reported by the client
(whatever `actor` the request body sends) - do not treat it as a verified
identity until an authorizer is added.
"""
import hashlib
import hmac
import json
import os
import re
import time
from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional

from common import aws_clients, config
from common.logging_utils import get_logger, log_event

logger = get_logger("dashboard_api")

_MEDIA_URL_TTL = 900  # 15 minutes
_PAGE_LIMIT = 100

# PBKDF2 parameters for staff password hashing. No new dependency (stdlib
# hashlib) - sized for a demo staff portal, not a hardened production KDF.
_PBKDF2_ITERATIONS = 260_000
_USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,32}$")
_HOSPITAL_NAME_MIN_LEN = 3
_HOSPITAL_ADDRESS_MIN_LEN = 5
# Intentionally permissive (format sanity-check, not full RFC 5322/E.164
# validation) - good enough to catch typos without rejecting valid real-world
# addresses/numbers.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_PATTERN = re.compile(r"^\+?[0-9][0-9\s\-()]{6,19}$")


def _hospital_id(hospital_name: str) -> str:
    """Stable alphanumeric-only ID used as the StaffUsersTable partition
    key, e.g. "Sunrise General Hospital" -> "sunrisegeneralhospital" (no
    hyphens/spaces/punctuation - easier to read back and retype from the
    onboarding email than a hyphenated slug). Two different hospitals that
    happen to share a display name will collide on this ID - acceptable for
    a demo-scale credential store; a production system would issue a real
    tenant ID at registration instead of deriving one."""
    alnum = re.sub(r"[^a-z0-9]+", "", hospital_name.strip().lower())
    return alnum or "defaulthospital"

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "content-type",
    "Access-Control-Allow-Methods": "GET,POST,PATCH,OPTIONS",
    "Content-Type": "application/json",
}

_VALID_STATUSES = {
    "OPEN", "APPROVED", "DENIED", "AWAITING_DOCUMENTS",
    # Follow-up flow lifecycle states.
    "AWAITING_INSURANCE_DOCS",   # insured: waiting for card photo + voice note
    "AWAITING_VOICE_NOTE",       # self-pay: waiting for voice note
    "PENDING_DOCTOR_APPROVAL",   # self-pay: voice received, awaiting doctor's tap
    "SCHEDULED",                 # appointment date/time released to the patient
}


def handler(event, context):
    method = (event.get("httpMethod") or "GET").upper()
    if method == "OPTIONS":
        return _respond(200, {"ok": True})

    path = event.get("path") or event.get("resource") or ""
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    case_id = path_params.get("id")

    try:
        if method == "POST" and "/auth/signup" in path:
            return _handle_signup(_parse_body(event))
        if method == "POST" and "/auth/login" in path:
            return _handle_login(_parse_body(event))

        if "/payer-rules" in path:
            if method == "POST":
                return _handle_create_rule(_parse_body(event))
            return _respond(200, {"rules": _list_payer_rules()})

        if "/stats" in path:
            return _respond(200, _compute_stats(query_params))

        if case_id and "/status" in path:
            return _handle_update_status(case_id, _parse_body(event))

        if case_id and method == "POST" and "/message" in path:
            return _handle_send_message(case_id, _parse_body(event))

        if case_id:
            item = _get_case(case_id)
            if not item:
                return _respond(404, {"error": "case not found"})
            return _respond(200, {"case": _present(item, detail=True)})

        if method == "POST" and "/followups" in path:
            return _handle_start_followup(_parse_body(event))

        if method == "POST" and "/cases" in path:
            return _handle_create_case(_parse_body(event))

        items = _list_cases(query_params)
        return _respond(200, {"cases": [_present(i) for i in items], "count": len(items)})
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "error", "dashboard.failed", path=path, error=str(exc))
        return _respond(500, {"error": "internal error"})


def _parse_body(event) -> Dict[str, Any]:
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return {}


# --------------------------------------------------------------------------- #
# Staff authentication (signup / login)
# --------------------------------------------------------------------------- #
def _staff_table():
    return aws_clients.dynamodb_resource().Table(config.STAFF_USERS_TABLE)


def _hash_password(password: str, salt_hex: Optional[str] = None) -> Dict[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return {"password_hash": digest.hex(), "password_salt": salt.hex()}


def _verify_password(password: str, password_hash: str, password_salt: str) -> bool:
    candidate = _hash_password(password, password_salt)["password_hash"]
    return hmac.compare_digest(candidate, password_hash)


def _profile(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "username": item["username"],
        "display_name": item.get("display_name", item["username"]),
        "role": item.get("role", "Clinic Staff"),
        "hospital_id": item["hospital_id"],
        "hospital_name": item.get("hospital_name", item["hospital_id"]),
        "hospital_address": item.get("hospital_address", ""),
        "hospital_email": item.get("hospital_email", ""),
        "hospital_phone": item.get("hospital_phone", ""),
    }


def _handle_signup(body: Dict[str, Any]):
    hospital_name = str(body.get("hospital_name", "")).strip()
    hospital_address = str(body.get("hospital_address", "")).strip()
    hospital_email = str(body.get("hospital_email", "")).strip().lower()
    hospital_phone = str(body.get("hospital_phone", "")).strip()
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))
    display_name = str(body.get("display_name", "")).strip()
    role = str(body.get("role", "")).strip() or "Clinic Staff"

    if len(hospital_name) < _HOSPITAL_NAME_MIN_LEN:
        return _respond(400, {"error": "Hospital / clinic name is required."})
    if len(hospital_address) < _HOSPITAL_ADDRESS_MIN_LEN:
        return _respond(400, {"error": "Hospital address is required."})
    if not _EMAIL_PATTERN.match(hospital_email):
        return _respond(400, {"error": "A valid hospital email address is required."})
    if not _PHONE_PATTERN.match(hospital_phone):
        return _respond(400, {"error": "A valid hospital phone number is required."})
    if not _USERNAME_PATTERN.match(username):
        return _respond(400, {
            "error": "Username must be 3-32 characters: lowercase letters, numbers, dot, underscore, or hyphen."
        })
    if len(password) < 8:
        return _respond(400, {"error": "Password must be at least 8 characters."})
    if not display_name:
        return _respond(400, {"error": "Display name is required."})

    hospital_id = _hospital_id(hospital_name)
    table = _staff_table()
    existing = table.get_item(Key={"hospital_id": hospital_id, "username": username}).get("Item")
    if existing:
        return _respond(409, {"error": "That username is already registered for this hospital."})

    hashed = _hash_password(password)
    item = {
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "hospital_address": hospital_address,
        "hospital_email": hospital_email,
        "hospital_phone": hospital_phone,
        "username": username,
        "display_name": display_name,
        "role": role,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **hashed,
    }
    table.put_item(Item=item)
    log_event(logger, "info", "auth.signup.ok", hospital_id=hospital_id, username=username)

    # Best-effort onboarding email - signup must succeed even if SES is
    # unreachable/unverified, so failures are logged, never raised.
    try:
        from . import onboarding_email

        onboarding_email.send_onboarding_email(
            to_address=hospital_email,
            display_name=display_name,
            hospital_name=hospital_name,
            hospital_id=hospital_id,
            username=username,
            role=role,
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "auth.signup.onboarding_email_failed", error=str(exc))

    return _respond(201, {"profile": _profile(item)})


def _handle_login(body: Dict[str, Any]):
    hospital_id = str(body.get("hospital_id", "")).strip().lower()
    username = str(body.get("username", "")).strip().lower()
    password = str(body.get("password", ""))

    if not hospital_id or not username or not password:
        return _respond(400, {"error": "Hospital ID, username, and password are required."})

    item = _staff_table().get_item(Key={"hospital_id": hospital_id, "username": username}).get("Item")
    # Compare against a dummy hash even on a missing user, so response
    # timing doesn't reveal whether a username/hospital combination exists.
    dummy = _hash_password("", os.urandom(16).hex())
    stored_hash = item.get("password_hash") if item else dummy["password_hash"]
    stored_salt = item.get("password_salt") if item else dummy["password_salt"]
    ok = _verify_password(password, stored_hash, stored_salt) and item is not None

    if not ok:
        log_event(logger, "warning", "auth.login.failed", hospital_id=hospital_id, username=username)
        return _respond(401, {"error": "Invalid hospital ID, username, or password."})

    log_event(logger, "info", "auth.login.ok", hospital_id=hospital_id, username=username)
    return _respond(200, {"profile": _profile(item)})


# --------------------------------------------------------------------------- #
# Data access
# --------------------------------------------------------------------------- #
def _cases_table():
    return aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)


def _rules_table():
    return aws_clients.dynamodb_resource().Table(config.PAYER_RULES_TABLE)


def _list_cases(query_params: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Scan + sort newest-first, optionally filtered to a created_at date
    range via ?from=YYYY-MM-DD&to=YYYY-MM-DD (both inclusive, UTC calendar
    days). No `from`/`to` -> no filtering (full page).

    Demo-scale volume (tens to low hundreds of cases), so a bounded scan is
    the simplest correct approach. For production volume, query the
    `by-status` GSI or add a time-bucketed partition key instead.
    """
    resp = _cases_table().scan(Limit=_PAGE_LIMIT)
    items = resp.get("Items", [])
    items.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)

    query_params = query_params or {}
    date_from = (query_params.get("from") or "").strip()
    date_to = (query_params.get("to") or "").strip()
    if date_from or date_to:
        lo = date_from or "0000-00-00"
        hi = (date_to or "9999-99-99") + "T23:59:59.999999Z"
        items = [i for i in items if lo <= str(i.get("created_at", "")) <= hi]
    return items


def _get_case(case_id: str):
    resp = _cases_table().get_item(Key={"case_id": case_id})
    return resp.get("Item")


def _append_activity(case_id: str, event: str, actor: str, detail: str) -> None:
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "actor": actor,
        "detail": detail,
    }
    _cases_table().update_item(
        Key={"case_id": case_id},
        UpdateExpression="SET activity_log = list_append(if_not_exists(activity_log, :empty), :entry)",
        ExpressionAttributeValues={":empty": [], ":entry": [entry]},
    )


def _handle_start_followup(body: Dict[str, Any]):
    """Staff-initiated follow-up flow (the primary CareRelay workflow).

    After an in-person consult, a doctor/staff member decides the patient
    needs a future scheduled procedure/diagnosis. They start the follow-up
    here with the patient's phone, the procedure, the intended appointment
    date/time, and whether the patient HAS INSURANCE. This:

      1. Creates the case in the correct pending state and stores the
         intended appointment_datetime WITHHELD (appointment_released=False) -
         the patient is NOT told the date/time yet.
      2. Associates the patient with the staff member's hospital
         (patient_directory) so a later WhatsApp reply is tagged correctly.
      3. Sends the FIRST WhatsApp request to the patient:
         - insured  -> ask for insurance card photo + a voice note (symptoms)
         - self-pay -> ask for a voice note only (symptoms/reason)

    The appointment date/time is released to the patient only later: once
    insurance clearance completes (insured path) or the doctor approves
    (self-pay path). That release happens in channel_dispatcher, not here.
    """
    import uuid

    patient_name = str(body.get("patient_name", "")).strip()
    patient_phone = str(body.get("patient_phone", "")).strip()
    cpt_code = str(body.get("cpt_code", "")).strip()
    procedure_name = str(body.get("procedure_name", "")).strip()
    payer_id = str(body.get("payer_id", "")).strip()
    has_insurance = bool(body.get("has_insurance", False))
    appointment_datetime = str(body.get("appointment_datetime", "")).strip()
    actor = str(body.get("actor", "")).strip() or "staff"
    hospital_id = str(body.get("hospital_id", "")).strip()
    hospital_name = str(body.get("hospital_name", "")).strip()

    if not patient_name or not patient_phone or not procedure_name:
        return _respond(400, {"error": "patient_name, patient_phone, and procedure_name are required."})
    if not appointment_datetime:
        return _respond(400, {"error": "appointment_datetime (intended slot) is required."})
    if has_insurance and (not cpt_code or not payer_id):
        return _respond(400, {"error": "cpt_code and payer_id are required for an insured follow-up."})

    phone_digits = re.sub(r"[^0-9]", "", patient_phone)
    flow = "followup_insured" if has_insurance else "followup_selfpay"
    status = "AWAITING_INSURANCE_DOCS" if has_insurance else "AWAITING_VOICE_NOTE"
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    item = {
        "case_id": case_id,
        "created_at": now,
        "status": status,
        "flow": flow,
        "channel": "whatsapp",
        "has_insurance": has_insurance,
        "appointment_datetime": appointment_datetime,
        "appointment_released": False,
        "hospital_id": hospital_id or None,
        "hospital_name": hospital_name or None,
        "patient_name": patient_name,
        "patient_phone_masked": f"***{phone_digits[-4:]}" if len(phone_digits) >= 4 else phone_digits,
        "patient_phone": phone_digits,
        "phone_number_id": config.WHATSAPP_PHONE_NUMBER_ID,
        "cpt_code": cpt_code or None,
        "procedure_name": procedure_name,
        "payer_id": payer_id or None,
        "extracted_card": {},
        "verification": {},
        "messages": {},
        "perceived_facts": [],
        "activity_log": [{
            "timestamp": now,
            "event": "FOLLOWUP_INITIATED",
            "actor": f"staff:{actor}",
            "detail": (
                f"Follow-up started for a {'insured' if has_insurance else 'self-pay'} patient. "
                f"Intended appointment {appointment_datetime} (withheld until "
                f"{'insurance clearance' if has_insurance else 'doctor approval'})."
            ),
        }],
    }
    _cases_table().put_item(Item={k: v for k, v in item.items() if v not in (None, "")})

    # Associate patient -> hospital so a later WhatsApp reply inherits it.
    if hospital_id:
        try:
            from common import patient_directory

            patient_directory.associate_patient(
                patient_phone=phone_digits, hospital_id=hospital_id,
                hospital_name=hospital_name, patient_name=patient_name,
            )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "followup.associate.failed", error=str(exc))

    # Send the first WhatsApp request to the patient.
    first_message_sent = False
    if has_insurance:
        body_text = (
            f"Hello {patient_name.split(' ')[0]}, this is {hospital_name or 'your clinic'}. "
            "Your doctor has recommended a follow-up procedure. To process your insurance "
            "coverage, please reply with:\n"
            "- A clear photo of your insurance card (front side)\n"
            "- A short voice note describing your symptoms / reason for the visit"
        )
    else:
        body_text = (
            f"Hello {patient_name.split(' ')[0]}, this is {hospital_name or 'your clinic'}. "
            "Your doctor has recommended a follow-up visit. To confirm, please reply with a "
            "short voice note describing your symptoms / reason for the visit."
        )
    try:
        from common import channels

        msg = channels.build_whatsapp_text(to=phone_digits, body=body_text)
        channels.send_whatsapp(msg, config.WHATSAPP_PHONE_NUMBER_ID)
        first_message_sent = True
        log_event(logger, "info", "followup.request_sent", case_id=case_id, flow=flow)
    except Exception as exc:  # noqa: BLE001 - case still created even if the first message fails
        log_event(logger, "warning", "followup.request_send_failed", case_id=case_id, error=str(exc))

    # Seed the conversation transcript with this first outbound request so
    # the console WhatsApp thread shows it immediately.
    if first_message_sent:
        try:
            from common import transcript

            transcript.append(case_id, transcript.DIRECTION_OUTBOUND, body_text,
                              kind="text", actor=f"staff:{actor}")
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "warning", "followup.transcript_failed", case_id=case_id, error=str(exc))

    return _respond(201, {"case": _present(_get_case(case_id) or item, detail=True)})


def _handle_create_case(body: Dict[str, Any]):
    """Manually log a staff-entered intake (e.g. a phone/walk-in case with
    no WhatsApp message behind it). Runs the SAME deterministic rules_engine
    logic the agent pipeline uses, so a manually-logged case gets a real
    verification outcome rather than a placeholder."""
    import uuid

    patient_name = str(body.get("patient_name", "")).strip()
    cpt_code = str(body.get("cpt_code", "")).strip()
    procedure_name = str(body.get("procedure_name", "")).strip()
    payer_id = str(body.get("payer_id", "")).strip()
    channel = str(body.get("channel", "whatsapp")).strip().lower()
    patient_phone_masked = str(body.get("patient_phone_masked", "")).strip() or "***0000"
    patient_phone = str(body.get("patient_phone", "")).strip()  # optional: enables POST /cases/{id}/message later
    actor = str(body.get("actor", "")).strip() or "staff"
    # Multi-tenancy (Option A): a console-logged case is tagged with the
    # authenticated staff member's own hospital, sent by the frontend from
    # the signed-in session.
    hospital_id = str(body.get("hospital_id", "")).strip()
    hospital_name = str(body.get("hospital_name", "")).strip()

    if not patient_name or not cpt_code or not procedure_name or not payer_id:
        return _respond(400, {
            "error": "patient_name, cpt_code, procedure_name, and payer_id are required."
        })
    if channel not in {"whatsapp", "rcs", "sms"}:
        return _respond(400, {"error": "channel must be one of: whatsapp, rcs, sms."})

    verification = _evaluate_rules(payer_id, cpt_code)
    status = "AWAITING_DOCUMENTS" if verification["missing_documents"] else (
        "APPROVED" if not verification["requires_prior_auth"] else "OPEN"
    )

    case_id = f"case-{uuid.uuid4().hex[:8]}"
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    item = {
        "case_id": case_id,
        "created_at": now,
        "status": status,
        "channel": channel,
        "hospital_id": hospital_id or None,
        "hospital_name": hospital_name or None,
        "patient_name": patient_name,
        "patient_phone_masked": patient_phone_masked,
        "patient_phone": patient_phone or None,
        "phone_number_id": config.WHATSAPP_PHONE_NUMBER_ID if patient_phone and channel == "whatsapp" else None,
        "cpt_code": cpt_code,
        "procedure_name": procedure_name,
        "payer_id": payer_id,
        "extracted_card": {},
        "verification": verification,
        "messages": {},
        "perceived_facts": [],
        "activity_log": [{
            "timestamp": now,
            "event": "CREATED",
            "actor": f"staff:{actor}",
            "detail": f"Case manually logged via console ({channel}).",
        }],
    }
    _cases_table().put_item(Item=item)
    log_event(logger, "info", "case.created", case_id=case_id, actor=actor)
    return _respond(201, {"case": _present(item, detail=True)})


def _handle_update_status(case_id: str, body: Dict[str, Any]):
    new_status = str(body.get("status", "")).strip().upper()
    actor = str(body.get("actor", "")).strip() or "staff"
    note = str(body.get("note", "")).strip()

    if new_status not in _VALID_STATUSES:
        return _respond(400, {"error": f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}."})

    item = _get_case(case_id)
    if not item:
        return _respond(404, {"error": "case not found"})

    old_status = item.get("status", "OPEN")
    _cases_table().update_item(
        Key={"case_id": case_id},
        UpdateExpression="SET #s = :new_status",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":new_status": new_status},
    )
    detail = f"Status changed {old_status} -> {new_status}" + (f" ({note})" if note else "")
    _append_activity(case_id, "STATUS_CHANGED", f"staff:{actor}", detail)
    log_event(logger, "info", "case.status_changed", case_id=case_id, old=old_status, new=new_status)

    updated = _get_case(case_id)
    return _respond(200, {"case": _present(updated, detail=True)})


def _handle_send_message(case_id: str, body: Dict[str, Any]):
    """Lets staff send a free-text WhatsApp message directly to the
    patient tied to a case - e.g. answering a question the automated flow
    didn't anticipate, or following up manually. This bypasses the agent
    entirely (no drafting, no rules_engine involvement) - the message body
    is exactly what the staff member typed, sent verbatim.

    Requires patient_phone + phone_number_id to have been stored on the
    case (written by channel_dispatcher when it creates the case from a
    real WhatsApp intake - see channel_dispatcher.handler._persist_case).
    A manually-logged case created via POST /cases has no WhatsApp thread
    behind it, so this will 400 for those unless a phone number was
    provided at creation time."""
    text = str(body.get("text", "")).strip()
    actor = str(body.get("actor", "")).strip() or "staff"

    if not text:
        return _respond(400, {"error": "text is required."})
    if len(text) > 4096:
        return _respond(400, {"error": "text must be 4096 characters or fewer."})

    item = _get_case(case_id)
    if not item:
        return _respond(404, {"error": "case not found"})

    patient_phone = item.get("patient_phone")
    if not patient_phone:
        return _respond(400, {
            "error": "This case has no WhatsApp thread to reply to (no patient phone number on file)."
        })

    from common import channels

    phone_number_id = item.get("phone_number_id") or config.WHATSAPP_PHONE_NUMBER_ID
    message_id = None
    try:
        msg = channels.build_whatsapp_text(to=patient_phone, body=text)
        message_id = channels.send_whatsapp(msg, phone_number_id)
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "staff_message.send.failed", case_id=case_id, error=str(exc))
        return _respond(502, {"error": "Could not send the WhatsApp message. Please try again."})

    _append_activity(
        case_id, "STAFF_MESSAGE_SENT", f"staff:{actor}",
        f"Sent a WhatsApp message to the patient: \"{text[:200]}\"",
    )
    try:
        from common import transcript

        transcript.append(case_id, transcript.DIRECTION_OUTBOUND, text,
                          kind="text", actor=f"staff:{actor}")
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "staff_message.transcript_failed", case_id=case_id, error=str(exc))
    log_event(logger, "info", "staff_message.sent", case_id=case_id, actor=actor, message_id=message_id)

    updated = _get_case(case_id)
    return _respond(200, {"case": _present(updated, detail=True)})


def _evaluate_rules(payer_id: str, cpt_code: str) -> Dict[str, Any]:
    """Thin wrapper around agent_app.rules_engine.evaluate() so manually
    logged cases get the SAME deterministic outcome the agent pipeline
    would produce - never a hand-rolled placeholder decision. No documents
    are on file yet for a freshly-logged case, so missing_documents will
    equal the rule's full required_documents list until updated."""
    import sys

    _lambdas_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _repo_root = os.path.dirname(_lambdas_dir)
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from agent_app import rules_engine

    rules = _list_payer_rules()
    decision = rules_engine.evaluate(payer_id, cpt_code, documents_on_file=[], rules=rules)
    result = decision.to_dict()
    return {
        "outcome": result.get("outcome"),
        "requires_prior_auth": result.get("requires_prior_auth", False),
        "missing_documents": result.get("missing_documents", []),
        "matched_rule_id": result.get("matched_rule_id"),
        "rationale": result.get("rationale", ""),
        "payer_simulated": False,
        "payer_eligible": None,
        "approval_code": None,
    }


def _list_payer_rules() -> List[Dict[str, Any]]:
    resp = _rules_table().scan()
    items = resp.get("Items", [])
    items.sort(key=lambda i: (str(i.get("payer_id", "")), str(i.get("cpt_code", ""))))
    return [_num_safe(i) for i in items]


def _handle_create_rule(body: Dict[str, Any]):
    payer_id = str(body.get("payer_id", "")).strip()
    cpt_code = str(body.get("cpt_code", "")).strip()
    procedure_name = str(body.get("procedure_name", "")).strip()
    requires_prior_auth = bool(body.get("requires_prior_auth", False))
    required_documents = body.get("required_documents") or []
    rule_id = str(body.get("rule_id", "")).strip()
    notes = str(body.get("notes", "")).strip()

    if not payer_id or not cpt_code or not procedure_name or not rule_id:
        return _respond(400, {
            "error": "payer_id, cpt_code, procedure_name, and rule_id are required."
        })
    if not isinstance(required_documents, list) or not all(isinstance(d, str) for d in required_documents):
        return _respond(400, {"error": "required_documents must be a list of strings."})

    item = {
        "payer_id": payer_id,
        "cpt_code": cpt_code,
        "procedure_name": procedure_name,
        "requires_prior_auth": requires_prior_auth,
        "required_documents": required_documents,
        "rule_id": rule_id,
        "notes": notes,
    }
    _rules_table().put_item(Item=item)
    log_event(logger, "info", "payer_rule.created", rule_id=rule_id, payer_id=payer_id, cpt_code=cpt_code)
    return _respond(201, {"rule": item})


def _compute_stats(query_params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    items = _list_cases(query_params)
    outcomes = Counter(i.get("verification", {}).get("outcome", "UNKNOWN") for i in items)
    statuses = Counter(i.get("status", "UNKNOWN") for i in items)
    channels = Counter(i.get("channel", "unknown") for i in items)

    missing_doc_counts = Counter()
    for i in items:
        for doc in i.get("verification", {}).get("missing_documents", []) or []:
            missing_doc_counts[doc] += 1

    simulated_calls = sum(1 for i in items if i.get("verification", {}).get("payer_simulated"))
    eligible_calls = sum(
        1 for i in items
        if i.get("verification", {}).get("payer_simulated")
        and i.get("verification", {}).get("payer_eligible")
    )

    confidences = [
        _num(i.get("extracted_card", {}).get("confidence"))
        for i in items
        if i.get("extracted_card", {}).get("confidence") is not None
    ]
    avg_confidence = round(sum(confidences) / len(confidences), 1) if confidences else None

    return {
        "total_cases": len(items),
        "by_outcome": dict(outcomes),
        "by_status": dict(statuses),
        "by_channel": dict(channels),
        "missing_documents": dict(missing_doc_counts.most_common(10)),
        "payer_simulated_calls": simulated_calls,
        "payer_eligible_calls": eligible_calls,
        "avg_card_extraction_confidence": avg_confidence,
    }


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #
def _present(item: Dict[str, Any], detail: bool = False) -> Dict[str, Any]:
    verification = _num_safe(item.get("verification", {}))
    extracted_card = _num_safe(item.get("extracted_card", {}))

    out = {
        "case_id": item.get("case_id"),
        "created_at": item.get("created_at"),
        "status": item.get("status", "OPEN"),
        "channel": item.get("channel"),
        "flow": item.get("flow"),
        "has_insurance": item.get("has_insurance"),
        "appointment_datetime": item.get("appointment_datetime"),
        "appointment_released": item.get("appointment_released", False),
        "hospital_id": item.get("hospital_id"),
        "hospital_name": item.get("hospital_name"),
        "patient_name": item.get("patient_name"),
        "patient_phone_masked": item.get("patient_phone_masked"),
        "cpt_code": item.get("cpt_code"),
        "procedure_name": item.get("procedure_name"),
        "payer_id": item.get("payer_id"),
        "verification": verification,
        "extracted_card": extracted_card,
    }

    if detail:
        out.update({
            "messages": item.get("messages", {}),
            "perceived_facts": item.get("perceived_facts", []),
            "narration": item.get("narration"),
            "photo_url": _presign(item.get("photo_key")),
            "audio_url": _presign(item.get("audio_key")),
            "agent_trace": _agent_trace(item),
            "activity_log": _num_safe(item.get("activity_log", [])),
            "transcript": _num_safe(item.get("transcript", [])),
            "payer_emails": _num_safe(item.get("payer_emails", [])),
            # Tells the frontend whether POST /cases/{id}/message is usable
            # for this case, WITHOUT ever exposing the raw patient_phone.
            "can_message_patient": bool(item.get("patient_phone")),
        })
    return out


def _agent_trace(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Reconstruct the Strands multi-agent pipeline as display steps.

    Mirrors the real execution order enforced in
    agent_app/agents/supervisor.py (Intake -> Verification -> Notification),
    so the frontend can render it as a visual trace instead of raw logs.
    """
    extracted_card = item.get("extracted_card", {}) or {}
    verification = item.get("verification", {}) or {}
    messages = item.get("messages", {}) or {}
    facts = item.get("perceived_facts", []) or []

    card_lines = [
        f"{k.replace('_', ' ')}: {v}"
        for k, v in extracted_card.items()
        if k != "confidence" and v
    ]
    if extracted_card.get("confidence") is not None:
        card_lines.append(f"extraction confidence: {_num(extracted_card.get('confidence'))}")

    trace = [
        {
            "agent": "Intake",
            "tool": "extract_insurance_card + transcribe_voice_note",
            "detail": card_lines + list(facts),
        },
        {
            "agent": "Verification",
            "tool": "check_prior_auth",
            "detail": [
                f"outcome = {verification.get('outcome')}",
                f"matched_rule_id = {verification.get('matched_rule_id')}",
                f"rationale: {verification.get('rationale')}",
            ] + (
                [f"missing_documents: {', '.join(verification.get('missing_documents', []))}"]
                if verification.get("missing_documents") else []
            ),
        },
    ]

    # Legacy seeded cases may carry payer_simulated/IVR fields from an
    # earlier revision; render them if present so their traces stay
    # complete. New cases contact the payer by email only (below).
    if verification.get("payer_simulated"):
        trace.append({
            "agent": "Verification",
            "tool": "call_payer_ivr (SIMULATED, legacy)",
            "detail": [
                f"eligible = {verification.get('payer_eligible')}",
                f"approval_code = {verification.get('approval_code') or 'n/a'}",
            ],
        })

    if verification.get("outcome") == "PRIOR_AUTH_REQUIRED":
        trace.append({
            "agent": "Notification",
            "tool": "send_payer_prior_auth_request (Amazon SES)",
            "detail": [
                "Formal written prior-authorization request emailed to the payer's intake inbox.",
                "CareRelay contacts the payer by email only - no IVR/phone call.",
            ],
        })

    trace.append({
        "agent": "Notification",
        "tool": "draft_patient_message + draft_doctor_approval_card + draft_audit_summary",
        "detail": [
            f"patient message: {messages.get('patient_message_body', '')}",
            f"doctor card: {messages.get('doctor_card_body', '')}",
        ],
    })
    return trace


def _presign(key):
    if not key:
        return None
    try:
        return aws_clients.s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": config.MEDIA_BUCKET, "Key": key},
            ExpiresIn=_MEDIA_URL_TTL,
        )
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "presign.failed", error=str(exc))
        return None


def _num(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


def _num_safe(obj):
    """Recursively convert Decimal -> float/int for JSON serialization."""
    if isinstance(obj, Decimal):
        return float(obj) if obj % 1 else int(obj)
    if isinstance(obj, dict):
        return {k: _num_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_num_safe(v) for v in obj]
    return obj


def _respond(status: int, body: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": _CORS,
        "body": json.dumps(body, default=str),
    }
