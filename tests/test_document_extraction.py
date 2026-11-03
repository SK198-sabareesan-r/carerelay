"""Evidence normalization / document inventory tests (deterministic, offline)."""
from agent_app.models import DocumentKind, FieldConfidence


def test_payer_name_canonicalized(synthetic_conflict_case):
    # "ACME Health" on the card resolves to the canonical catalog id.
    assert synthetic_conflict_case.payer_id == "PAYER-ACME"


def test_documents_classified(synthetic_conflict_case):
    kinds = {d.kind for d in synthetic_conflict_case.documents}
    assert DocumentKind.INSURANCE_CARD in kinds
    assert DocumentKind.PROCEDURE_ORDER in kinds
    assert DocumentKind.CLINICAL_NOTES in kinds
    assert DocumentKind.PAYER_POLICY in kinds
    # imaging deliberately absent
    assert DocumentKind.IMAGING_REPORT not in kinds


def test_documents_on_file_vocab(synthetic_conflict_case):
    # Maps to the rules-engine required_documents vocabulary.
    on_file = synthetic_conflict_case.documents_on_file()
    assert "clinical_notes" in on_file
    assert "xray_or_mri" not in on_file


def test_low_confidence_field_preserved(synthetic_conflict_case):
    low = synthetic_conflict_case.low_confidence_fields()
    names = {f.name for f in low}
    assert "member_id" in names
    member = next(f for f in low if f.name == "member_id")
    assert member.confidence == FieldConfidence.LOW
    assert member.source_document_id == "doc-card"


def test_cross_document_field_lookup(synthetic_conflict_case):
    cpts = synthetic_conflict_case.all_fields("cpt_code")
    values = {f.value for f in cpts}
    assert values == {"29881", "29826"}  # the injected mismatch is visible
