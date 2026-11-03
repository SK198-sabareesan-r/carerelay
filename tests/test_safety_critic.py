"""Safety/state gate tests - the deterministic floor that blocks unsafe progress.

These exercise the deterministic safety pre-check inside run_case and the
state-transition engine. The agent Safety Critic's narrative is a live/model
concern; the GUARANTEE a judge cares about - 'an unsafe case can never
advance' - lives in deterministic code and is what we assert here.
"""
from agent_app.orchestration.case_state import CaseState
from agent_app.orchestration.case_graph import run_case
from agent_app.services import state_transition


def test_conflict_case_is_not_approved(synthetic_conflict_case):
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    assert st.safety_verdict.approved is False
    assert st.safety_verdict.requires_human_review is True
    assert st.current_status == "UNDER_REVIEW"  # never advanced


def test_clean_case_is_approved_and_advances(clean_ready_case):
    st = CaseState(case_id="c", evidence=clean_ready_case)
    run_case(st, run_swarm=False)
    assert st.safety_verdict.approved is True
    assert st.current_status == "READY_FOR_REVIEW"


def test_state_gate_blocks_progression_while_conflicted(synthetic_conflict_case):
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    # Even a direct attempt to push toward doctor approval must be refused.
    res = state_transition.validate_transition(
        "READY_FOR_REVIEW", "PENDING_DOCTOR_APPROVAL", st.readiness
    )
    assert res.allowed is False


def test_illegal_transition_rejected():
    res = state_transition.validate_transition("OPEN", "SCHEDULED")
    assert res.allowed is False


def test_clean_case_allows_doctor_approval(clean_ready_case):
    st = CaseState(case_id="c", evidence=clean_ready_case)
    run_case(st, run_swarm=False)
    res = state_transition.validate_transition(
        "READY_FOR_REVIEW", "PENDING_DOCTOR_APPROVAL", st.readiness
    )
    assert res.allowed is True
