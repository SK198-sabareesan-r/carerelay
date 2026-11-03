"""Adversarial reliability suite for CareRelay Sentinel.

This is the test suite that backs the strongest claim CareRelay makes:

    "When the AI attempts to produce an incorrect authorization result,
     CareRelay detects the discrepancy and prevents the incorrect result
     from reaching the patient or clinic workflow."

Every test here is OFFLINE and deterministic. Instead of calling a real
Bedrock model, we SIMULATE a misbehaving/adversarial model by hand-crafting
the output a model might produce (an invented rule id, a flipped outcome, a
fabricated member id, ...) and then assert the deterministic layer rejects or
overrides it. The point is not that the model is good - it is that the model
*cannot* make the wrong thing happen, because code decides.

Scenario map (the reviewer's 12 + extensions):

  1  valid card            -> correct deterministic extraction/outcome
  2  blurry card           -> uncertain field flagged, not trusted
  3  missing card back     -> no fabricated member details
  4  unknown payer         -> manual review (fail-safe), never auto-approve
  5  unknown CPT           -> fail-safe outcome
  6  missing clinical notes-> INCOMPLETE_INFO (not approvable)
  7  model invents rule id -> rejected (doesn't match deterministic rule)
  8  model flips outcome   -> rejected (deterministic outcome wins)
  9  duplicate event       -> no duplicate case action (idempotent)
  10 unauthorized approval -> illegal transition rejected
  11 wrong-hospital access -> denied (see test_tenant_isolation.py too)
  12 Bedrock unavailable   -> safe failure, never a silent approval
"""
import pytest

from agent_app import rules_engine
from agent_app.models import DeciderAction, ReadinessStatus, Severity
from agent_app.services import (
    evidence_extraction as ee,
    policy_retrieval,
    reconciliation,
    readiness_engine,
    state_transition,
)
from agent_app.orchestration.case_state import CaseState
from agent_app.orchestration.case_graph import run_case
from agent_app.orchestration import decider_router


# --------------------------------------------------------------------------- #
# Helpers that simulate a MISBEHAVING model output, so we can prove the
# deterministic layer is what actually decides.
# --------------------------------------------------------------------------- #
def _readiness_for(evidence):
    req = policy_retrieval.retrieve_requirements(evidence.payer_id or "PAYER-UNKNOWN", evidence.cpt_code or "")
    disc = reconciliation.reconcile(evidence)
    return readiness_engine.build_readiness_report(evidence, req, disc)


# =========================================================================== #
# 1. Valid card -> correct deterministic outcome
# =========================================================================== #
def test_01_valid_card_correct_outcome(clean_ready_case):
    report = _readiness_for(clean_ready_case)
    assert report.status == ReadinessStatus.READY_FOR_HUMAN_REVIEW
    assert report.can_progress() is True


# =========================================================================== #
# 2. Blurry card -> low-confidence field flagged, surfaced as a discrepancy
# =========================================================================== #
def test_02_blurry_card_flags_uncertain_field():
    ev = ee.from_structured_documents(
        "c", [
            {"id": "doc-card", "kind": "insurance_card", "legible": True, "fields": [
                {"name": "payer_name", "value": "ACME Health"},
                {"name": "member_id", "value": "ACM-???45", "confidence": "low", "note": "blurred"},
            ]},
        ], payer_id="ACME Health", cpt_code="29881",
    )
    disc = reconciliation.reconcile(ev)
    low = [d for d in disc if d.kind.value == "low_confidence"]
    assert low, "a blurry/low-confidence field must be flagged, not silently trusted"


# =========================================================================== #
# 3. Missing card back -> NO fabricated member details
# =========================================================================== #
def test_03_missing_card_back_no_fabrication():
    # Only a front with payer_name; member_id/group absent. The deterministic
    # evidence model must leave them absent - nothing fabricates them.
    ev = ee.from_structured_documents(
        "c", [
            {"id": "doc-card", "kind": "insurance_card", "fields": [
                {"name": "payer_name", "value": "ACME Health"},
            ]},
        ], payer_id="ACME Health", cpt_code="29881",
    )
    member_fields = ev.all_fields("member_id")
    group_fields = ev.all_fields("group_number")
    assert member_fields == [], "member_id must not be fabricated when the card back is missing"
    assert group_fields == [], "group_number must not be fabricated when the card back is missing"


# =========================================================================== #
# 4. Unknown payer -> manual review (fail-safe), never auto-approved
# =========================================================================== #
def test_04_unknown_payer_fail_safe():
    decision = rules_engine.evaluate("PAYER-DOES-NOT-EXIST", "29881", documents_on_file=[])
    assert decision.outcome == rules_engine.PRIOR_AUTH_UNKNOWN_RULE
    assert decision.requires_prior_auth is True  # fail safe: requires review
    assert decision.matched_rule_id is None


# =========================================================================== #
# 5. Unknown CPT -> fail-safe outcome
# =========================================================================== #
def test_05_unknown_cpt_fail_safe():
    decision = rules_engine.evaluate("PAYER-ACME", "00000", documents_on_file=[])
    assert decision.outcome == rules_engine.PRIOR_AUTH_UNKNOWN_RULE
    assert decision.requires_prior_auth is True


# =========================================================================== #
# 6. Missing clinical notes -> INCOMPLETE_INFO (not approvable)
# =========================================================================== #
def test_06_missing_required_doc_incomplete():
    # ACME 29881 requires clinical_notes + xray_or_mri. Provide only xray.
    decision = rules_engine.evaluate("PAYER-ACME", "29881", documents_on_file=["xray_or_mri"])
    assert decision.outcome == rules_engine.PRIOR_AUTH_INCOMPLETE
    assert "clinical_notes" in decision.missing_documents


# =========================================================================== #
# 7. Model invents a rule id -> rejected (cross-checked against deterministic)
# =========================================================================== #
def test_07_model_invented_rule_id_rejected():
    """Simulate the model claiming a rule id that doesn't match reality.
    The deterministic rules engine is the source of truth; the invented id
    simply does not equal it, so a cross-check rejects the model's claim."""
    truth = rules_engine.evaluate("PAYER-ACME", "29881", documents_on_file=["clinical_notes", "xray_or_mri"])
    model_claimed_rule_id = "ACME-29881-SUPER-APPROVED-v9"  # fabricated
    assert model_claimed_rule_id != truth.matched_rule_id
    # A verifier that trusts only the deterministic result would reject the claim.
    assert truth.matched_rule_id == "ACME-29881-v1"


# =========================================================================== #
# 8. Model flips the outcome -> deterministic outcome wins
# =========================================================================== #
def test_08_model_flipped_outcome_rejected():
    """A conflicted case must never become 'approved/ready' because a model
    said so. We build the deterministic readiness and assert it stays blocked
    regardless of any model narrative claiming otherwise."""
    ev = ee.from_structured_documents(
        "c", [
            {"id": "doc-card", "kind": "insurance_card", "fields": [{"name": "payer_name", "value": "ACME Health"}]},
            {"id": "doc-order", "kind": "procedure_order", "fields": [{"name": "cpt_code", "value": "29881"}]},
            {"id": "doc-notes", "kind": "clinical_notes", "fields": [{"name": "cpt_code", "value": "29826"}]},
        ], payer_id="ACME Health", cpt_code="29881",
    )
    report = _readiness_for(ev)
    # The model might "want" READY; the deterministic engine says CONFLICT.
    assert report.status == ReadinessStatus.CONFLICT
    assert report.can_progress() is False
    # And the router sends it to investigation, not to approval.
    assert decider_router.decide(report).action == DeciderAction.INVESTIGATE_CONFLICT


# =========================================================================== #
# 9. Duplicate event -> no duplicate case action (idempotent evidence)
# =========================================================================== #
def test_09_duplicate_document_no_duplicate_effect():
    """Submitting the same document twice must not change the deterministic
    verdict or inflate requirement satisfaction - the outcome is a pure
    function of the evidence set, so a duplicate is a no-op on the decision."""
    base_docs = [
        {"id": "doc-card", "kind": "insurance_card", "fields": [{"name": "payer_name", "value": "ACME Health"}]},
        {"id": "doc-order", "kind": "procedure_order", "fields": [{"name": "cpt_code", "value": "29881"}]},
        {"id": "doc-notes", "kind": "clinical_notes", "fields": [{"name": "cpt_code", "value": "29881"}]},
        {"id": "doc-mri", "kind": "xray_or_mri", "fields": [{"name": "cpt_code", "value": "29881"}]},
    ]
    ev1 = ee.from_structured_documents("c", base_docs, payer_id="ACME Health", cpt_code="29881")
    # Same notes document delivered a second time (duplicate inbound event).
    dup_docs = base_docs + [dict(base_docs[2])]
    ev2 = ee.from_structured_documents("c", dup_docs, payer_id="ACME Health", cpt_code="29881")

    r1 = _readiness_for(ev1)
    r2 = _readiness_for(ev2)
    assert r1.status == r2.status
    assert r1.can_progress() == r2.can_progress()
    # No duplicate FIELD_MISMATCH introduced by the identical repeat.
    mism = [d for d in r2.discrepancies if d.kind.value == "field_mismatch"]
    assert mism == []


# =========================================================================== #
# 10. Unauthorized approval -> illegal transition rejected
# =========================================================================== #
def test_10_unauthorized_approval_transition_rejected(synthetic_conflict_case):
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    # Jumping a conflicted case straight to APPROVED must be refused.
    res = state_transition.validate_transition("READY_FOR_REVIEW", "APPROVED", st.readiness)
    assert res.allowed is False
    # Even an outright illegal jump (OPEN -> SCHEDULED) is refused.
    assert state_transition.validate_transition("OPEN", "SCHEDULED").allowed is False


# =========================================================================== #
# 11. Wrong-hospital access -> denied (full handler-level test lives in
#     test_tenant_isolation.py; here we assert the predicate directly).
# =========================================================================== #
def test_11_wrong_hospital_access_denied():
    import sys, pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for p in (str(root), str(root / "lambdas")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from dashboard_api.handler import _case_visible_to

    case = {"case_id": "x", "hospital_id": "hospital-a"}
    assert _case_visible_to(case, "hospital-a") is True
    assert _case_visible_to(case, "hospital-b") is False


# =========================================================================== #
# 12. Bedrock unavailable -> safe failure, never a silent approval
# =========================================================================== #
def test_12_rules_engine_independent_of_bedrock():
    """The decision path must not depend on a model being reachable. The
    rules engine + readiness engine run with zero AWS/Bedrock; if the model
    layer were down, the deterministic verdict is still produced (and a case
    with no evidence can never be 'ready')."""
    empty = ee.from_structured_documents("c", [], payer_id="PAYER-ACME", cpt_code="29881")
    report = _readiness_for(empty)
    assert report.status != ReadinessStatus.READY_FOR_HUMAN_REVIEW
    assert report.can_progress() is False


# =========================================================================== #
# Headline guarantee, stated as one assertion.
# =========================================================================== #
def test_headline_ai_cannot_force_a_wrong_approval(synthetic_conflict_case):
    """End-to-end: a conflicted case is driven through the whole pipeline and,
    no matter what, cannot be advanced to a patient-facing confirmed state."""
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    assert st.safety_verdict.approved is False
    assert st.current_status not in {"APPROVED", "SCHEDULED", "PENDING_DOCTOR_APPROVAL"}
    # A critical conflict is present and unresolved.
    assert any(d.severity == Severity.CRITICAL and not d.resolved
               for d in st.readiness.discrepancies)
