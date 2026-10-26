"""Per-case WhatsApp conversation transcript.

CareRelay's console shows a live, chat-style view of the real WhatsApp
conversation with each patient. That view is backed by a `transcript` list
stored on the PriorAuthTable case item - a chronological list of message
bubbles appended every time a message flows in either direction:

    - INBOUND  : something the patient sent us (text, a voice note, an
                 insurance card photo, or a button/list tap).
    - OUTBOUND : something we sent the patient (the document request, a
                 status update, the final appointment confirmation, or a
                 free-text staff reply).

Each bubble:
    {
      "direction": "inbound" | "outbound",
      "kind": "text" | "image" | "audio" | "button" | "interactive",
      "body": "human-readable text to render in the bubble",
      "actor": "patient" | "system" | "agent" | "staff:<username>",
      "timestamp": "2026-...Z",
    }

This is deliberately separate from `activity_log` (the audit trail of
case-state events like STATUS_CHANGED / APPOINTMENT_RELEASED). The
transcript is what a human conversation looks like; the activity_log is
what the system did. The console renders the transcript as the WhatsApp
thread and the activity_log as the case timeline.

append() is best-effort and never raises - a transcript write failing must
never break the actual message send or case processing.
"""
import time
from typing import Any, Dict, List, Optional

from . import aws_clients, config
from .logging_utils import get_logger, log_event

logger = get_logger("transcript")

DIRECTION_INBOUND = "inbound"
DIRECTION_OUTBOUND = "outbound"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def make_bubble(
    direction: str,
    body: str,
    *,
    kind: str = "text",
    actor: str = "system",
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single transcript bubble dict (no DynamoDB write)."""
    return {
        "direction": direction,
        "kind": kind,
        "body": (body or "")[:2000],
        "actor": actor,
        "timestamp": timestamp or _now(),
    }


def append_bubbles(case_id: str, bubbles: List[Dict[str, Any]]) -> None:
    """Append one or more bubbles to a case's transcript. Best-effort."""
    if not case_id or not bubbles:
        return
    try:
        table = aws_clients.dynamodb_resource().Table(config.PRIOR_AUTH_TABLE)
        table.update_item(
            Key={"case_id": case_id},
            UpdateExpression=(
                "SET transcript = list_append(if_not_exists(transcript, :empty), :b)"
            ),
            ExpressionAttributeValues={":empty": [], ":b": bubbles},
        )
    except Exception as exc:  # noqa: BLE001 - never break the real send over a transcript write
        log_event(logger, "warning", "transcript.append.failed", case_id=case_id, error=str(exc))


def append(
    case_id: str,
    direction: str,
    body: str,
    *,
    kind: str = "text",
    actor: str = "system",
) -> None:
    """Convenience: append a single bubble."""
    append_bubbles(case_id, [make_bubble(direction, body, kind=kind, actor=actor)])
