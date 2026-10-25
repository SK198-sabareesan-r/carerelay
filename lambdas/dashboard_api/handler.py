"""dashboard_api Lambda - read-only API backing the CareRelay frontend
application (frontend/).

Routes (API Gateway proxy):
    GET  /cases                -> list of cases, newest first
    GET  /cases/{id}           -> single case detail, incl. agent_trace
    GET  /payer-rules          -> the deterministic PayerRulesTable contents
    GET  /stats                -> aggregate counters for the analytics view
    POST /auth/signup          -> create a clinic staff account
    POST /auth/login           -> verify credentials, return the staff profile

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

This Lambda is READ-ONLY and never writes. It is deliberately the only
surface exposed to the browser.

SECURITY NOTE: unauthenticated by default so the demo/dashboard works with
zero setup. patient_phone_masked is pre-masked at write time by
channel_dispatcher; this API never returns the raw phone number. Add an
authorizer (Cognito/Lambda/API key) before any real deployment - see
docs/DASHBOARD.md.
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
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Content-Type": "application/json",
}


def handler(event, context):
    method = (event.get("httpMethod") or "GET").upper()
    if method == "OPTIONS":
        return _respond(200, {"ok": True})

    path = event.get("path") or event.get("resource") or ""
    path_params = event.get("pathParameters") or {}
    case_id = path_params.get("id")

    try:
        if method == "POST" and "/auth/signup" in path:
            return _handle_signup(_parse_body(event))
        if method == "POST" and "/auth/login" in path:
            return _handle_login(_parse_body(event))

        if "/payer-rules" in path:
            return _respond(200, {"rules": _list_payer_rules()})
        if "/stats" in path:
            return _respond(200, _compute_stats())
        if case_id:
            item = _get_case(case_id)
            if not item:
                return _respond(404, {"error": "case not found"})
            return _respond(200, {"case": _present(item, detail=True)})

        items = _list_cases()
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


def _list_cases() -> List[Dict[str, Any]]:
    """Scan + sort newest-first.

    Demo-scale volume (tens to low hundreds of cases), so a bounded scan is
    the simplest correct approach. For production volume, query the
    `by-status` GSI or add a time-bucketed partition key instead.
    """
    resp = _cases_table().scan(Limit=_PAGE_LIMIT)
    items = resp.get("Items", [])
    items.sort(key=lambda i: str(i.get("created_at", "")), reverse=True)
    return items


def _get_case(case_id: str):
    resp = _cases_table().get_item(Key={"case_id": case_id})
    return resp.get("Item")


def _list_payer_rules() -> List[Dict[str, Any]]:
    resp = _rules_table().scan()
    items = resp.get("Items", [])
    items.sort(key=lambda i: (str(i.get("payer_id", "")), str(i.get("cpt_code", ""))))
    return [_num_safe(i) for i in items]


def _compute_stats() -> Dict[str, Any]:
    items = _list_cases()
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

    if verification.get("payer_simulated"):
        trace.append({
            "agent": "Verification",
            "tool": "call_payer_ivr (SIMULATED)",
            "detail": [
                f"eligible = {verification.get('payer_eligible')}",
                f"approval_code = {verification.get('approval_code') or 'n/a'}",
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
