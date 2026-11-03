"""Conflict / discrepancy detection tests - the core differentiator."""
from agent_app.models import DiscrepancyKind, Severity
from agent_app.services import reconciliation


def test_detects_cpt_mismatch(synthetic_conflict_case):
    disc = reconciliation.reconcile(synthetic_conflict_case)
    cpt = [d for d in disc if d.kind == DiscrepancyKind.FIELD_MISMATCH and d.field_name == "cpt_code"]
    assert len(cpt) == 1
    assert cpt[0].severity == Severity.CRITICAL
    assert set(cpt[0].conflicting_values) == {"29881", "29826"}
    assert set(cpt[0].source_document_ids) == {"doc-order", "doc-notes"}


def test_detects_low_confidence(synthetic_conflict_case):
    disc = reconciliation.reconcile(synthetic_conflict_case)
    low = [d for d in disc if d.kind == DiscrepancyKind.LOW_CONFIDENCE]
    assert any(d.field_name == "member_id" for d in low)
    assert all(d.severity == Severity.WARNING for d in low)


def test_no_false_positive_on_clean_case(clean_ready_case):
    disc = reconciliation.reconcile(clean_ready_case)
    # agreeing cpt_code across order/notes/mri must NOT be a mismatch
    assert not [d for d in disc if d.kind == DiscrepancyKind.FIELD_MISMATCH]


def test_patient_name_agreement_not_flagged(synthetic_conflict_case):
    disc = reconciliation.reconcile(synthetic_conflict_case)
    # patient_name is "Jaafar" on both docs -> no mismatch for it
    assert not [
        d for d in disc
        if d.kind == DiscrepancyKind.FIELD_MISMATCH and d.field_name == "patient_name"
    ]
