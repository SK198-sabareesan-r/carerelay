"""Policy requirement model: a single payer requirement that a case must
satisfy, retrieved by the Policy Research agent / policy_retrieval service.

Requirements are deterministic records (sourced from the payer rules catalog
or an approved policy source), not model opinions. A requirement says *what*
is needed (a document kind, a field value, a timing window); the readiness
engine decides deterministically whether the case *evidence* satisfies it.
"""
from __future__ import annotations

import enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RequirementKind(str, enum.Enum):
    """The kinds of requirement the readiness engine knows how to check."""

    DOCUMENT_PRESENT = "document_present"      # a document of a given kind must exist and be legible
    FIELD_PRESENT = "field_present"            # a named field must be extracted (non-null)
    FIELD_MATCHES = "field_matches"            # a named field must equal an expected value
    TIMING_WINDOW = "timing_window"            # evidence must fall within N days (narrative-checked)


class PolicyRequirement(BaseModel):
    """One atomic, checkable payer requirement with provenance."""

    id: str = Field(description="Stable requirement id, e.g. 'ACME-29881-v1:req-imaging'.")
    payer_id: str
    cpt_code: Optional[str] = Field(default=None, description="CPT this requirement applies to, if specific.")
    kind: RequirementKind
    description: str = Field(description="Human-readable requirement text, shown in the readiness report.")

    # Target of the check (interpretation depends on `kind`):
    document_kind: Optional[str] = Field(
        default=None, description="For DOCUMENT_PRESENT: the DocumentKind value required."
    )
    field_name: Optional[str] = Field(
        default=None, description="For FIELD_PRESENT / FIELD_MATCHES: the field that must exist / match."
    )
    expected_value: Optional[str] = Field(
        default=None, description="For FIELD_MATCHES: the value the field must equal."
    )
    window_days: Optional[int] = Field(
        default=None, description="For TIMING_WINDOW: the maximum age in days."
    )

    source_rule_id: Optional[str] = Field(
        default=None, description="The rules-engine rule_id this requirement derives from (verbatim provenance)."
    )
    source_citation: Optional[str] = Field(
        default=None, description="Verbatim policy citation, e.g. 'ACME policy section 4.2'."
    )
    critical: bool = Field(
        default=True,
        description="If true, an unsatisfied/conflicting requirement blocks automatic progression.",
    )


class PolicyRequirementSet(BaseModel):
    """All requirements that apply to a case, plus the matched rule id so the
    whole set traces back to one deterministic rule row."""

    payer_id: str
    cpt_code: Optional[str] = None
    matched_rule_id: Optional[str] = None
    requires_prior_auth: bool = True
    requirements: List[PolicyRequirement] = Field(default_factory=list)
    retrieval_note: Optional[str] = Field(
        default=None, description="How these were retrieved, e.g. 'rules catalog PAYER-ACME/29881'."
    )
