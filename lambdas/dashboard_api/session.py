"""Signed session tokens for the dashboard API.

Replaces the previous "trust whatever profile the client sends" model. On a
successful login/signup the API issues a compact HMAC-signed token that
encodes the staff identity (hospital_id, username, role) and an expiry. Every
mutating / tenant-scoped route then REQUIRES a valid token and derives the
caller's identity + hospital from it - the client can no longer self-report
who it is or which hospital's data it sees.

Design notes:
- Stdlib only (hmac, hashlib, base64, json, time) - no new dependency, same
  constraint as the PBKDF2 password hashing already in handler.py.
- Token shape:  base64url(payload_json) + "." + base64url(hmac_sha256)
  payload = {"hid": hospital_id, "u": username, "r": role, "exp": epoch}
- The signing secret comes from config.SESSION_SIGNING_SECRET (env
  SESSION_SIGNING_SECRET). If unset, a per-process random secret is used so
  tokens still work within a warm Lambda but are invalidated on cold start -
  acceptable for the demo; a real deployment sets a stable secret (or uses
  Cognito/JWT). This is intentionally a real signature check, not decoration:
  a tampered or unsigned token is rejected.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

_DEFAULT_TTL_SECONDS = 12 * 3600  # 12h session


def _secret() -> bytes:
    secret = os.environ.get("SESSION_SIGNING_SECRET", "")
    if not secret:
        # Stable-within-process fallback so warm invocations validate each
        # other's tokens even without a configured secret.
        cached = getattr(_secret, "_cached", None)
        if cached is None:
            cached = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
            _secret._cached = cached  # type: ignore[attr-defined]
        secret = cached
    return secret.encode("utf-8")


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(
    hospital_id: str, username: str, role: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS
) -> str:
    payload = {
        "hid": hospital_id,
        "u": username,
        "r": role,
        "exp": int(time.time()) + ttl_seconds,
    }
    payload_b = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_secret(), payload_b, hashlib.sha256).digest()
    return f"{_b64u(payload_b)}.{_b64u(sig)}"


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Return the decoded claims if the token is well-formed, correctly
    signed, and unexpired; otherwise None."""
    if not token or "." not in token:
        return None
    try:
        payload_part, sig_part = token.split(".", 1)
        payload_b = _b64u_decode(payload_part)
        expected = hmac.new(_secret(), payload_b, hashlib.sha256).digest()
        got = _b64u_decode(sig_part)
    except Exception:  # noqa: BLE001 - any decode error => invalid token
        return None
    if not hmac.compare_digest(expected, got):
        return None
    try:
        claims = json.loads(payload_b.decode("utf-8"))
    except (ValueError, TypeError):
        return None
    if int(claims.get("exp", 0)) < int(time.time()):
        return None
    return claims


def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """Pull the bearer token from the Authorization header (case-insensitive
    header name, 'Bearer <token>' or raw token)."""
    headers = event.get("headers") or {}
    auth = None
    for k, v in headers.items():
        if k.lower() == "authorization":
            auth = v
            break
    if not auth:
        return None
    auth = auth.strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return auth or None


def claims_from_event(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convenience: extract + verify in one call."""
    token = extract_token(event)
    return verify_token(token) if token else None
