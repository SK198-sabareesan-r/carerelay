"""Pytest fixtures + path/env setup for the CareRelay Sentinel test suite.

All tests here are OFFLINE and deterministic: they exercise the models,
services, and the orchestration normal path (run_case with run_swarm=False),
none of which make a Bedrock/AWS call. The live swarm path is covered by a
stubbed swarm_runner so even the conflict path is tested without a network.
"""
import os
import re
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Make agent_app importable without installing the package.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env values (non-blank only) so lambdas.common.config has table names
# etc.; pop a blank AWS_PROFILE which otherwise makes boto3 raise.
_env_file = ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line)
        if m and m.group(2).strip():
            os.environ.setdefault(m.group(1), m.group(2).strip())
if not os.environ.get("AWS_PROFILE"):
    os.environ.pop("AWS_PROFILE", None)


@pytest.fixture
def synthetic_conflict_case():
    """The P0 driving scenario: 5 documents with 3 deliberately-injected issues.

    Payer ACME, CPT 29881 (requires clinical_notes + xray_or_mri).
      1. insurance_card  - member_id read LOW confidence   (issue #3)
      2. procedure_order - cpt_code 29881
      3. clinical_notes  - cpt_code 29826                  (issue #1: mismatch)
      4. payer_policy     - policy doc present
      (NO xray_or_mri)                                     (issue #2: missing)
    """
    from agent_app.services import evidence_extraction as ee

    documents = [
        {"id": "doc-card", "kind": "insurance_card", "fields": [
            {"name": "payer_name", "value": "ACME Health"},
            {"name": "member_id", "value": "ACM-83920145", "confidence": "low", "note": "glare on card"},
            {"name": "patient_name", "value": "Jaafar"},
        ]},
        {"id": "doc-order", "kind": "procedure_order", "fields": [
            {"name": "cpt_code", "value": "29881"},
            {"name": "patient_name", "value": "Jaafar"},
            {"name": "procedure_name", "value": "Knee arthroscopy, meniscectomy"},
        ]},
        {"id": "doc-notes", "kind": "clinical_notes", "fields": [
            {"name": "cpt_code", "value": "29826"},
            {"name": "patient_name", "value": "Jaafar"},
        ]},
        {"id": "doc-policy", "kind": "payer_policy", "fields": [], "raw_text": "ACME policy section 4.2"},
    ]
    return ee.from_structured_documents(
        case_id="case-synthetic",
        documents=documents,
        patient_name="Jaafar",
        cpt_code="29881",
        procedure_name="Knee arthroscopy, meniscectomy",
        payer_id="ACME Health",
    )


@pytest.fixture
def clean_ready_case():
    """A clean case: all ACME 29881 requirements satisfiable, no conflicts."""
    from agent_app.services import evidence_extraction as ee

    documents = [
        {"id": "doc-card", "kind": "insurance_card", "fields": [
            {"name": "payer_name", "value": "ACME Health"},
            {"name": "member_id", "value": "ACM-1"},
        ]},
        {"id": "doc-order", "kind": "procedure_order", "fields": [
            {"name": "cpt_code", "value": "29881"},
            {"name": "patient_name", "value": "Asha"},
        ]},
        {"id": "doc-notes", "kind": "clinical_notes", "fields": [
            {"name": "cpt_code", "value": "29881"},
            {"name": "patient_name", "value": "Asha"},
        ]},
        {"id": "doc-mri", "kind": "xray_or_mri", "fields": [
            {"name": "cpt_code", "value": "29881"},
        ]},
    ]
    return ee.from_structured_documents(
        case_id="case-clean", documents=documents, patient_name="Asha",
        cpt_code="29881", payer_id="ACME Health",
    )


@pytest.fixture
def missing_evidence_case():
    """A case missing only the imaging document (no conflict)."""
    from agent_app.services import evidence_extraction as ee

    documents = [
        {"id": "doc-card", "kind": "insurance_card", "fields": [
            {"name": "payer_name", "value": "ACME Health"}]},
        {"id": "doc-order", "kind": "procedure_order", "fields": [
            {"name": "cpt_code", "value": "29881"}]},
        {"id": "doc-notes", "kind": "clinical_notes", "fields": [
            {"name": "cpt_code", "value": "29881"}]},
    ]
    return ee.from_structured_documents(
        case_id="case-missing", documents=documents, cpt_code="29881", payer_id="ACME Health",
    )
