"""Agent-facing Strands tools for the CareRelay Sentinel layer.

Each tool is a thin, read-only wrapper over a deterministic service. The
specialist agents call these to OBSERVE deterministic facts (requirements,
discrepancies, the readiness verdict); they never let the model compute those
facts itself. This is how "code decides, AI talks" is enforced at the tool
boundary: the agent can only narrate what the service returned.

The tools accept/return plain JSON-able dicts (not Pydantic objects) because
Strands serializes tool I/O. Callers in the orchestration layer convert to/
from the models/ types.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from strands import tool

from ..services import (
    policy_retrieval,
    reconciliation,
    readiness_engine,
)
from ..services import evidence_extraction
from ..models import CaseEvidence, PolicyRequirementSet, Discrepancy


@tool
def retrieve_policy_requirements(payer_id: str, cpt_code: str) -> Dict[str, Any]:
    """Retrieve the deterministic payer requirement set for a payer + CPT.

    Returns the matched rule id, whether prior auth is required, and the list
    of atomic requirements (each with a source rule id and policy citation).
    The agent reports these verbatim; it must not invent requirements.
    """
    req_set = policy_retrieval.retrieve_requirements(payer_id, cpt_code)
    return req_set.model_dump()


@tool
def detect_discrepancies(case_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run the deterministic cross-document reconciliation over case evidence.

    `case_evidence` is a CaseEvidence dict (documents + extracted fields).
    Returns the list of detected discrepancies (field mismatches, low
    confidence reads, illegible documents) with severity and provenance. The
    agent explains these; it cannot add or remove a discrepancy.
    """
    evidence = CaseEvidence.model_validate(case_evidence)
    return [d.model_dump() for d in reconciliation.reconcile(evidence)]


@tool
def compute_readiness(
    case_evidence: Dict[str, Any],
    requirement_set: Dict[str, Any],
    discrepancies: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute the authoritative readiness report (deterministic).

    Combines evidence, the requirement set, and any discrepancies into the
    per-requirement checks and the overall readiness status. This result is
    final - the agent may summarize it but must never contradict `status` or
    `can_progress`.
    """
    evidence = CaseEvidence.model_validate(case_evidence)
    req_set = PolicyRequirementSet.model_validate(requirement_set)
    disc = [Discrepancy.model_validate(d) for d in (discrepancies or [])]
    report = readiness_engine.build_readiness_report(evidence, req_set, disc)
    out = report.model_dump()
    out["can_progress"] = report.can_progress()
    return out


@tool
def normalize_structured_evidence(
    case_id: str,
    documents_json: str,
    cpt_code: str = "",
    payer_hint: str = "",
    patient_name: str = "",
) -> Dict[str, Any]:
    """Normalize a JSON array of structured documents into a CaseEvidence dict.

    `documents_json` is a JSON string: a list of {id, kind, legible?, fields:[
    {name, value, confidence?, note?}]}. Used when documents are already
    extracted (e.g. uploaded text docs) rather than coming from the live card/
    voice intake path. Payer is canonicalized deterministically.
    """
    documents = json.loads(documents_json)
    evidence = evidence_extraction.from_structured_documents(
        case_id=case_id,
        documents=documents,
        patient_name=patient_name or None,
        cpt_code=cpt_code or None,
        payer_id=payer_hint or None,
    )
    return evidence.model_dump()
