"""Case lifecycle Graph: the main orchestrator.

This is the Graph-led coordinator for a case. It runs the deterministic
pipeline, consults the bounded Decider for the next action, conditionally
dispatches the exception Swarm, applies the Safety Critic + deterministic
safety/state gate, and returns the finished CaseState.

Two complementary representations:

  run_case(...)        - the executable orchestration (deterministic control
                         flow with conditional Swarm). This is what the app,
                         tests, and the dashboard actually call. It is fully
                         testable with zero model calls on the normal path.

  build_case_graph()   - a Strands GraphBuilder structural graph of the same
                         lifecycle (entry -> evidence -> decider -> {swarm |
                         readiness} -> safety -> gate). Built with real Strands
                         node/edge/condition APIs so the "Graph as the main
                         orchestrator" pattern is expressed with the SDK, and
                         so the dashboard can render the node/edge topology.

Decisions remain deterministic: the Decider only routes, the Swarm only
narrates, and services.state_transition has the final say on progression.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..models import (
    AgentDecision,
    DeciderAction,
    SafetyVerdict,
)
from ..services import state_transition
from .case_state import CaseState
from .evidence_workflow import run_evidence_workflow
from . import decider_router


# --------------------------------------------------------------------------- #
# Executable orchestration (deterministic control flow)
# --------------------------------------------------------------------------- #
def run_case(
    state: CaseState,
    *,
    run_swarm: bool = False,
    swarm_runner: Optional[Callable[[CaseState], CaseState]] = None,
) -> CaseState:
    """Run a case through the full Sentinel lifecycle.

    Args:
        state: a CaseState with .evidence already populated (by intake /
            document normalization).
        run_swarm: if True and the Decider routes to INVESTIGATE_CONFLICT,
            actually dispatch the exception Swarm (makes model calls). If
            False (default / unit tests), the conflict is recorded and routed
            to human review without invoking the live swarm, keeping the
            normal path deterministic and offline-testable.
        swarm_runner: injectable swarm function (defaults to the real
            exception_swarm.run_exception_swarm); lets tests stub it.

    Returns the same CaseState, fully populated.
    """
    state.audit.record("GRAPH_START", "case_graph", f"Case {state.case_id} entered the lifecycle graph.")

    # 1. Deterministic evidence workflow (parallel) -> readiness report.
    run_evidence_workflow(state)
    assert state.readiness is not None  # guaranteed by the workflow

    # 2. Bounded Decider: choose the next action from the closed set.
    decision: AgentDecision = decider_router.decide(state.readiness)
    state.decision = decision
    state.audit.record(
        "DECIDER_ROUTED", "decider",
        f"action={decision.action.value} ({'rule' if decision.rule_based else 'model'}): {decision.reason}",
        data={"action": decision.action.value, "rule_based": decision.rule_based},
    )

    # 3. Conditional routing.
    if decision.action == DeciderAction.INVESTIGATE_CONFLICT:
        if run_swarm:
            runner = swarm_runner or _default_swarm_runner
            runner(state)
        else:
            state.audit.record(
                "SWARM_SKIPPED", "case_graph",
                "Critical conflict present; swarm dispatch disabled for this run - "
                "routing to human review.",
            )

    # 4. Safety Critic gate (deterministic pre-check; agent critic is layered
    #    on in the live/integration path via the swarm's safety_critic node).
    verdict = _deterministic_safety_precheck(state)
    state.safety_verdict = verdict
    state.audit.record(
        "SAFETY_VERDICT", "safety_critic",
        ("approved" if verdict.approved else "human review required")
        + (f": {verdict.notes}" if verdict.notes else ""),
        data={"approved": verdict.approved, "requires_human_review": verdict.requires_human_review},
    )

    # 5. Deterministic safety/state engine has the final say on progression.
    target = _progression_target_for(decision.action)
    if target:
        result = state_transition.validate_transition(
            state.current_status, target, state.readiness
        )
        state.audit.record(
            "STATE_GATE", "state_engine",
            f"{state.current_status} -> {target}: "
            + ("ALLOWED" if result.allowed else "BLOCKED")
            + f" ({result.reason})",
            data={"allowed": result.allowed, "target": target},
        )
        if result.allowed and verdict.approved:
            state.current_status = target

    state.audit.record("GRAPH_DONE", "case_graph", f"Case {state.case_id} finished the lifecycle graph.")
    return state


def _default_swarm_runner(state: CaseState) -> CaseState:
    # Imported lazily so the normal/offline path never imports the swarm
    # (which pulls in the live agent roster / Bedrock model construction).
    from .exception_swarm import run_exception_swarm

    return run_exception_swarm(state)


def _deterministic_safety_precheck(state: CaseState) -> SafetyVerdict:
    """A deterministic floor under the agent Safety Critic: regardless of any
    model output, the case is NOT approved to advance if the readiness report
    says it cannot progress or any blocking conflict remains."""
    readiness = state.readiness
    unresolved = []
    if readiness is not None:
        unresolved = [d.summary for d in readiness.blocking_discrepancies()]

    can_progress = bool(readiness and readiness.can_progress())
    approved = can_progress and not unresolved
    return SafetyVerdict(
        approved=approved,
        unresolved_conflicts=unresolved,
        requires_human_review=not approved,
        notes=(
            "Deterministic pre-check: "
            + ("clear to advance to human review." if approved
               else "unresolved critical items block progression.")
        ),
    )


def _progression_target_for(action: DeciderAction) -> Optional[str]:
    """Map a Decider action to the case status it would advance toward, so the
    state-transition gate can validate it. Only CONTINUE_VERIFICATION proposes
    forward progress (to READY_FOR_REVIEW); the others hold or route sideways."""
    if action == DeciderAction.CONTINUE_VERIFICATION:
        return "READY_FOR_REVIEW"
    return None


# --------------------------------------------------------------------------- #
# Structural Strands Graph (SDK expression of the same lifecycle)
# --------------------------------------------------------------------------- #
def build_case_graph():
    """Build a Strands GraphBuilder graph of the case lifecycle.

    Nodes are the roster agents; edges + conditions express the flow:
        intake -> document -> policy -> consistency -> readiness
                 -> (safety_critic)
    with a conditional edge into the consistency/safety path when a conflict
    is present. This is the SDK-level "Graph as orchestrator" artifact; the
    executable deterministic control flow above (run_case) is what production
    calls, but this graph is real and buildable for topology/visualization.
    """
    from strands.multiagent import GraphBuilder

    from ..agents import roster

    agents = roster.build_all()
    b = GraphBuilder()
    b.add_node(agents["intake_agent"], "intake")
    b.add_node(agents["document_agent"], "document")
    b.add_node(agents["policy_research_agent"], "policy")
    b.add_node(agents["clinical_consistency_agent"], "consistency")
    b.add_node(agents["readiness_agent"], "readiness")
    b.add_node(agents["safety_critic_agent"], "safety")

    b.set_entry_point("intake")
    b.add_edge("intake", "document")
    b.add_edge("document", "policy")
    b.add_edge("policy", "consistency")
    b.add_edge("consistency", "readiness")
    b.add_edge("readiness", "safety")

    b.set_max_node_executions(20)
    b.set_execution_timeout(600.0)
    b.set_node_timeout(120.0)
    return b.build()
