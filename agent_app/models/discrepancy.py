"""Discrepancy model: a detected inconsistency, gap, or low-confidence read.

Discrepancies are produced deterministically by the reconciliation service
(cross-document comparisons) and the readiness engine (missing requirements,
low-confidence fields). The Clinical Consistency and Safety Critic agents add
*narrative* (explanation, recommended follow-up) but never invent or clear a
discrepancy on their own - clearing requires corrected evidence + a re-run.
"""
from __future__ import annotations

import enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Severity(str, enum.Enum):
    """CRITICAL blocks automatic progression; WARNING is surfaced but
    non-blocking; INFO is purely advisory."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class DiscrepancyKind(str, enum.Enum):
    FIELD_MISMATCH = "field_mismatch"            # same field, different values across documents
    MISSING_DOCUMENT = "missing_document"        # a required document is absent
    MISSING_FIELD = "missing_field"              # a required field is absent/null
    LOW_CONFIDENCE = "low_confidence"            # a field was extracted with low confidence
    ILLEGIBLE_DOCUMENT = "illegible_document"    # a submitted document could not be read
    UNSUPPORTED_REQUIREMENT = "unsupported_requirement"  # evidence doesn't establish a requirement
    TIMING = "timing"                            # evidence falls outside a required window


class Discrepancy(BaseModel):
    """One detected issue, source-linked for human verification."""

    id: str = Field(description="Stable per-case discrepancy id, e.g. 'disc-cpt-mismatch'.")
    kind: DiscrepancyKind
    severity: Severity
    field_name: Optional[str] = Field(default=None, description="Field involved, if applicable.")
    summary: str = Field(description="One-line deterministic statement of the issue.")

    # Provenance: which documents / values are in conflict.
    source_document_ids: List[str] = Field(default_factory=list)
    conflicting_values: List[str] = Field(
        default_factory=list, description="The differing values, when kind=FIELD_MISMATCH."
    )
    related_requirement_id: Optional[str] = Field(
        default=None, description="The PolicyRequirement this discrepancy violates, if any."
    )

    # Narrative, added by agents - never changes severity/kind.
    explanation: Optional[str] = Field(default=None, description="Agent's plain-language explanation.")
    recommended_action: Optional[str] = Field(
        default=None, description="Suggested human follow-up, e.g. 'request corrected procedure order'."
    )
    resolved: bool = Field(default=False, description="Set true only after corrected evidence re-run clears it.")

    def is_blocking(self) -> bool:
        return self.severity == Severity.CRITICAL and not self.resolved
