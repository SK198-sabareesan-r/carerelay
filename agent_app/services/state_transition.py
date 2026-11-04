"""Deterministic case-state transition validation.

A single authority for which case-status transitions are legal, and a gate
that blocks progression toward approval/scheduling while a readiness report
has unresolved critical discrepancies. This is the "deterministic safety and
state engine" from the plan: even if an agent (or a mis-click) requests an
illegal or unsafe transition, this module rejects it.

The status vocabulary is aligned with the existing dashboard
(lambdas/dashboard_api/handler.py _VALID_STATUSES) plus the Sentinel review
states, so the upgrade layers on top of the existing case lifecycle rather
than replacing it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Set

from ..models import ReadinessReport

# Legal transitions. Keys are the "from" status; values are allowed "to".
# Sentinel adds UNDER_REVIEW (evidence pipeline running) and
# READY_FOR_REVIEW (pipeline cleared; a human may now act).
_ALLOWED: Dict[str, Set[str]] = {
    # Follow-up flow entry states (set by POST /followups). Staff may move a
    # follow-up forward once documents arrive, or close it out.
    "AWAITING_INSURANCE_DOCS": {"AWAITING_PAYER", "AWAITING_DOCUMENTS", "UNDER_REVIEW", "DENIED"},
    "AWAITING_VOICE_NOTE": {"PENDING_DOCTOR_APPROVAL", "AWAITING_DOCUMENTS", "UNDER_REVIEW", "DENIED"},
    "OPEN": {"AWAITING_DOCUMENTS", "UNDER_REVIEW", "DENIED"},
    "AWAITING_DOCUMENTS": {"UNDER_REVIEW", "AWAITING_DOCUMENTS", "DENIED"},
    "UNDER_REVIEW": {"READY_FOR_REVIEW", "AWAITING_DOCUMENTS", "AWAITING_PAYER", "DENIED"},
    "READY_FOR_REVIEW": {"AWAITING_PAYER", "PENDING_DOCTOR_APPROVAL", "AWAITING_DOCUMENTS", "DENIED"},
    "AWAITING_PAYER": {"PENDING_DOCTOR_APPROVAL", "READY_FOR_REVIEW", "DENIED"},
    "PENDING_DOCTOR_APPROVAL": {"APPROVED", "READY_FOR_REVIEW", "DENIED"},
    "APPROVED": {"SCHEDULED", "DENIED"},
    "SCHEDULED": {"DENIED"},
    "DENIED": set(),
}

# Transitions that mean "this case is moving toward authorization / the
# patient being committed". These are gated by the readiness report: they are
# refused while any critical discrepancy is unresolved.
_PROGRESSION_TARGETS = {"AWAITING_PAYER", "PENDING_DOCTOR_APPROVAL", "APPROVED", "SCHEDULED"}


@dataclass
class TransitionResult:
    allowed: bool
    reason: str


def validate_transition(
    from_status: str,
    to_status: str,
    readiness: Optional[ReadinessReport] = None,
) -> TransitionResult:
    """Return whether a status transition is permitted.

    Two gates, both deterministic:
      1. The transition must be in the allowed adjacency map.
      2. If it is a progression toward authorization, the readiness report
         (when supplied) must permit progression (no blocking discrepancies).
    """
    from_status = (from_status or "").upper()
    to_status = (to_status or "").upper()

    if from_status == to_status:
        return TransitionResult(True, "No-op transition (same status).")

    allowed_targets = _ALLOWED.get(from_status)
    if allowed_targets is None:
        return TransitionResult(False, f"Unknown source status '{from_status}'.")
    if to_status not in allowed_targets:
        return TransitionResult(
            False, f"Illegal transition {from_status} -> {to_status}."
        )

    if to_status in _PROGRESSION_TARGETS and readiness is not None:
        if not readiness.can_progress():
            blocking = readiness.blocking_discrepancies()
            detail = "; ".join(d.summary for d in blocking) or f"status={readiness.status.value}"
            return TransitionResult(
                False,
                f"Blocked: case is not cleared for progression ({detail}).",
            )

    return TransitionResult(True, f"Transition {from_status} -> {to_status} permitted.")
