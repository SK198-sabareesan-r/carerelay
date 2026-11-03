"""Decider 2B bounded-routing tests + the rules-vs-model benchmark contract."""
from agent_app.models import DeciderAction, ReadinessStatus
from agent_app.services import policy_retrieval, reconciliation, readiness_engine
from agent_app.orchestration import decider_router


def _readiness_for(evidence):
    req = policy_retrieval.retrieve_requirements(evidence.payer_id, evidence.cpt_code)
    disc = reconciliation.reconcile(evidence)
    return readiness_engine.build_readiness_report(evidence, req, disc)


def test_conflict_routes_to_investigate(synthetic_conflict_case):
    r = _readiness_for(synthetic_conflict_case)
    assert r.status == ReadinessStatus.CONFLICT
    d = decider_router.decide(r)
    assert d.action == DeciderAction.INVESTIGATE_CONFLICT
    assert d.rule_based is True


def test_clean_routes_to_continue(clean_ready_case):
    r = _readiness_for(clean_ready_case)
    assert r.status == ReadinessStatus.READY_FOR_HUMAN_REVIEW
    d = decider_router.decide(r)
    assert d.action == DeciderAction.CONTINUE_VERIFICATION


def test_missing_routes_to_request_evidence(missing_evidence_case):
    r = _readiness_for(missing_evidence_case)
    assert r.status == ReadinessStatus.MISSING_EVIDENCE
    d = decider_router.decide(r)
    assert d.action == DeciderAction.REQUEST_MISSING_EVIDENCE


def test_action_space_is_bounded(synthetic_conflict_case):
    """Every decision must come from the closed 4-action set and present that
    full set as the considered options (the 'bounded' property)."""
    r = _readiness_for(synthetic_conflict_case)
    d = decider_router.decide(r)
    assert d.action in set(DeciderAction)
    assert set(d.considered_actions) == set(DeciderAction)


def test_decider_never_approves_or_authorizes(clean_ready_case, synthetic_conflict_case):
    """Decider actions must not include any approve/authorize verb - it only
    routes. This guards the 'Decider never decides coverage' invariant."""
    for case in (clean_ready_case, synthetic_conflict_case):
        d = decider_router.decide(_readiness_for(case))
        assert d.action.value in {
            "CONTINUE_VERIFICATION", "REQUEST_MISSING_EVIDENCE",
            "INVESTIGATE_CONFLICT", "HUMAN_REVIEW_REQUIRED",
        }
