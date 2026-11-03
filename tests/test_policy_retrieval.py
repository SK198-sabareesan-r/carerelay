"""Policy retrieval tests: deterministic requirement derivation + provenance."""
from agent_app.models import RequirementKind
from agent_app.services import policy_retrieval


def test_matches_rule_and_requires_prior_auth():
    req_set = policy_retrieval.retrieve_requirements("PAYER-ACME", "29881")
    assert req_set.matched_rule_id == "ACME-29881-v1"
    assert req_set.requires_prior_auth is True


def test_required_documents_become_requirements():
    req_set = policy_retrieval.retrieve_requirements("PAYER-ACME", "29881")
    doc_reqs = [r for r in req_set.requirements if r.kind == RequirementKind.DOCUMENT_PRESENT]
    kinds = {r.document_kind for r in doc_reqs}
    assert kinds == {"clinical_notes", "xray_or_mri"}


def test_cpt_consistency_requirement_present():
    req_set = policy_retrieval.retrieve_requirements("PAYER-ACME", "29881")
    cpt_reqs = [r for r in req_set.requirements if r.kind == RequirementKind.FIELD_MATCHES]
    assert len(cpt_reqs) == 1
    assert cpt_reqs[0].field_name == "cpt_code"
    assert cpt_reqs[0].expected_value == "29881"


def test_every_requirement_has_provenance():
    req_set = policy_retrieval.retrieve_requirements("PAYER-ACME", "29881")
    for r in req_set.requirements:
        assert r.source_rule_id == "ACME-29881-v1"
        assert r.source_citation  # non-empty verbatim citation


def test_payer_name_normalized_in_retrieval():
    # Passing the raw card name still resolves to the ACME rule.
    req_set = policy_retrieval.retrieve_requirements("ACME Health", "29881")
    assert req_set.matched_rule_id == "ACME-29881-v1"


def test_not_required_procedure_yields_no_doc_requirements():
    # ACME D0150 is NOT_REQUIRED in the fallback catalog.
    req_set = policy_retrieval.retrieve_requirements("PAYER-ACME", "D0150")
    assert req_set.requires_prior_auth is False
    assert req_set.requirements == []
