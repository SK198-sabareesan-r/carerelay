"""Deterministic policy retrieval: turn the matched payer rule into a set of
atomic, checkable PolicyRequirements.

This bridges the existing rules_engine (which answers "is prior-auth required
and which documents") into the finer-grained requirement model the readiness
engine checks. No model is involved: requirements are derived mechanically
from the rule row, carrying the rule_id and policy citation as provenance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import rules_engine
from ..models import (
    PolicyRequirement,
    PolicyRequirementSet,
    RequirementKind,
)


def retrieve_requirements(
    payer_id: str,
    cpt_code: str,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> PolicyRequirementSet:
    """Retrieve the applicable requirement set for a payer + CPT.

    Uses rules_engine.evaluate() as the authoritative source (so payer-name
    normalization and rule matching stay in one place), then expands the
    matched rule's required_documents into one DOCUMENT_PRESENT requirement
    each, plus a CPT consistency requirement that the case CPT must match the
    rule's CPT (this is what catches a procedure-code mismatch)."""
    decision = rules_engine.evaluate(
        payer_id=payer_id, cpt_code=cpt_code, documents_on_file=[], rules=rules
    )

    requirements: List[PolicyRequirement] = []
    rule_id = decision.matched_rule_id
    citation = decision.rationale

    if decision.requires_prior_auth and rule_id is not None:
        # One requirement per required document kind.
        for doc in decision.required_documents:
            requirements.append(
                PolicyRequirement(
                    id=f"{rule_id}:doc-{doc}",
                    payer_id=decision.payer_id,
                    cpt_code=cpt_code,
                    kind=RequirementKind.DOCUMENT_PRESENT,
                    description=f"A legible {doc.replace('_', ' ')} document must be on file.",
                    document_kind=doc,
                    source_rule_id=rule_id,
                    source_citation=citation,
                    critical=True,
                )
            )
        # Procedure-code consistency: the CPT the clinic is pursuing must be
        # the CPT the matched rule governs. A mismatch here is the classic
        # "procedure code differs across documents" issue.
        requirements.append(
            PolicyRequirement(
                id=f"{rule_id}:cpt-consistency",
                payer_id=decision.payer_id,
                cpt_code=cpt_code,
                kind=RequirementKind.FIELD_MATCHES,
                description=f"The procedure code on all documents must be {cpt_code}.",
                field_name="cpt_code",
                expected_value=cpt_code,
                source_rule_id=rule_id,
                source_citation=citation,
                critical=True,
            )
        )

    return PolicyRequirementSet(
        payer_id=decision.payer_id,
        cpt_code=cpt_code,
        matched_rule_id=rule_id,
        requires_prior_auth=decision.requires_prior_auth,
        requirements=requirements,
        retrieval_note=(
            f"Derived from rules catalog match {rule_id or 'NONE'} "
            f"for payer={decision.payer_id} cpt={cpt_code}."
        ),
    )
