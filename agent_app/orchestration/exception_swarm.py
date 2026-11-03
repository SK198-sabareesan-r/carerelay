"""Exception-investigation Swarm: autonomous specialist collaboration for
complex conflicts.

When the Decider routes a case to INVESTIGATE_CONFLICT, this builds a Strands
Swarm of the relevant specialists (Document Intelligence, Policy Research,
Clinical Consistency) with the Safety Critic always included. They hand off to
each other to investigate the conflict, propose a resolution, and have the
Safety Critic challenge it.

Hard bounds are set (max handoffs/iterations/timeouts + repetitive-handoff
detection) so the swarm cannot loop forever - exactly the controls the plan
calls for. The swarm produces NARRATIVE only; it never clears a discrepancy or
changes the deterministic readiness verdict. Any resolution it proposes still
has to be re-verified by re-running the deterministic pipeline on corrected
evidence (see orchestration/case_graph reprocessing).
"""
from __future__ import annotations

import json
from typing import Optional

from strands.multiagent import Swarm

from ..agents import roster
from .case_state import CaseState


def build_exception_swarm() -> Swarm:
    """Construct the bounded investigation swarm from the roster subset."""
    agents = roster.build_subset(roster.SWARM_AGENT_NAMES)
    nodes = list(agents.values())
    entry = agents["clinical_consistency_agent"]  # start where the conflict lives
    return Swarm(
        nodes=nodes,
        entry_point=entry,
        max_handoffs=8,
        max_iterations=12,
        execution_timeout=240.0,
        node_timeout=90.0,
        repetitive_handoff_detection_window=4,
        repetitive_handoff_min_unique_agents=2,
        id="carerelay_exception_swarm",
    )


def _build_investigation_prompt(state: CaseState) -> str:
    """Deterministic string build of the conflict briefing for the swarm."""
    evidence = state.evidence.model_dump() if state.evidence else {}
    readiness = state.readiness.model_dump() if state.readiness else {}
    conflicts = [
        d.model_dump()
        for d in (state.readiness.discrepancies if state.readiness else state.discrepancies)
        if d.severity.value == "critical"
    ]
    return (
        "A prior-authorization case has a critical, unresolved conflict that "
        "needs investigation before it can go to a human reviewer.\n\n"
        f"Case evidence (source-linked):\n{json.dumps(evidence, indent=2)}\n\n"
        f"Detected critical conflicts:\n{json.dumps(conflicts, indent=2)}\n\n"
        f"Deterministic readiness verdict:\n{json.dumps(readiness, indent=2)}\n\n"
        "Investigate collaboratively: identify exactly which documents/fields "
        "disagree, what additional evidence would resolve it, and a concrete "
        "recommended follow-up. The Safety Critic must challenge any proposed "
        "resolution for unsupported claims. You CANNOT clear the conflict or "
        "approve anything - your output is an investigation summary and a "
        "recommended human action only."
    )


def run_exception_swarm(state: CaseState, swarm: Optional[Swarm] = None) -> CaseState:
    """Run the swarm over the case conflict and capture its narrative.

    This calls the live Strands Swarm (which invokes Bedrock), so it is only
    exercised on the complex path / in integration tests with AWS access. The
    deterministic discrepancies and readiness verdict are NOT modified here -
    the swarm only adds investigation_narrative and an audit entry.
    """
    swarm = swarm or build_exception_swarm()
    state.audit.record(
        "SWARM_INVESTIGATION_START", "exception_swarm",
        "Dispatching exception investigation swarm for a critical conflict.",
    )
    prompt = _build_investigation_prompt(state)
    result = swarm(prompt)

    narrative = str(result)
    state.investigation_narrative = narrative
    state.audit.record(
        "SWARM_INVESTIGATION_DONE", "exception_swarm",
        f"Swarm completed (status={getattr(result, 'status', 'n/a')}).",
        data={"status": str(getattr(result, "status", ""))},
    )
    return state
