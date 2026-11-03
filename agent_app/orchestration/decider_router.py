"""Decider 2B: bounded next-action router.

Given a compact, structured case state, the Decider selects exactly ONE next
processing action from a closed set (DeciderAction). It never approves a
procedure or authorizes a claim - it only chooses what the pipeline does next.

Two implementations, with rules FIRST (per the plan: benchmark the Decider
against simple rules; if rules achieve the same routing quality at lower
cost/latency, use rules):

  decide_by_rules(...)  - deterministic routing from the readiness report.
  decide(...)           - entry point: uses rules by default; a model-based
                          decider can be plugged in later for genuinely
                          ambiguous states, but the deterministic safety/state
                          engine still has the final say downstream.

The output is an AgentDecision carrying the action, a concrete reason, a
confidence, and `rule_based` so a benchmark harness can compare rule routing
vs model routing.
"""
from __future__ import annotations

from typing import Optional

from ..models import (
    AgentDecision,
    DeciderAction,
    ReadinessReport,
    ReadinessStatus,
)

# The full, closed action space presented to the router for every decision.
_ALLOWED_ACTIONS = [
    DeciderAction.CONTINUE_VERIFICATION,
    DeciderAction.REQUEST_MISSING_EVIDENCE,
    DeciderAction.INVESTIGATE_CONFLICT,
    DeciderAction.HUMAN_REVIEW_REQUIRED,
]


def decide_by_rules(readiness: ReadinessReport) -> AgentDecision:
    """Deterministic routing from the readiness status.

    Mapping (fail-safe - ambiguity always routes toward more scrutiny, never
    less):
      CONFLICT            -> INVESTIGATE_CONFLICT   (hand to the Swarm)
      MISSING_EVIDENCE    -> REQUEST_MISSING_EVIDENCE
      BLOCKED             -> HUMAN_REVIEW_REQUIRED
      READY_FOR_HUMAN_... -> CONTINUE_VERIFICATION  (proceed to safety review)
    """
    status = readiness.status

    if status == ReadinessStatus.CONFLICT:
        action = DeciderAction.INVESTIGATE_CONFLICT
        reason = (
            "A critical cross-document conflict was detected; routing to the "
            "exception investigation swarm. "
            + _first_summary(readiness)
        )
    elif status == ReadinessStatus.MISSING_EVIDENCE:
        action = DeciderAction.REQUEST_MISSING_EVIDENCE
        missing = [c.description for c in readiness.unsatisfied_requirements()]
        reason = "Required evidence is missing: " + ("; ".join(missing) or "see readiness report") + "."
    elif status == ReadinessStatus.BLOCKED:
        action = DeciderAction.HUMAN_REVIEW_REQUIRED
        reason = "Case is blocked by unresolved critical discrepancies; human review required."
    else:  # READY_FOR_HUMAN_REVIEW
        action = DeciderAction.CONTINUE_VERIFICATION
        reason = "All critical requirements satisfied with no blocking conflicts; continue to safety review."

    return AgentDecision(
        action=action,
        reason=reason,
        confidence=1.0,
        rule_based=True,
        considered_actions=list(_ALLOWED_ACTIONS),
    )


def _first_summary(readiness: ReadinessReport) -> str:
    blocking = readiness.blocking_discrepancies()
    if blocking:
        return blocking[0].summary
    if readiness.discrepancies:
        return readiness.discrepancies[0].summary
    return ""


def decide(
    readiness: ReadinessReport,
    use_model: bool = False,
) -> AgentDecision:
    """Entry point. Rules-based by default (preferred). `use_model` is a hook
    for a future model-based decider on genuinely ambiguous states; it is not
    enabled in this build because the deterministic routing covers every
    readiness status unambiguously and is cheaper + auditable.

    Regardless of which router chose the action, the deterministic
    safety/state engine (services.state_transition) still gates any actual
    case progression downstream - the Decider cannot by itself advance a case.
    """
    decision = decide_by_rules(readiness)
    if use_model:
        # Placeholder for a benchmarked model decider. Intentionally not wired
        # to a live model in this build; see tests/test_decider_routing.py for
        # the rules-vs-model benchmark harness contract.
        decision.rule_based = decision.rule_based
    return decision
