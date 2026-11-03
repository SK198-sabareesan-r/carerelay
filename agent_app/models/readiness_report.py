"""Readiness report model: the human-verifiable output of the whole pipeline.

The report is the single artifact a clinic reviewer reads. It says, per
requirement, whether the case evidence satisfies it (and which document
satisfied it), lists every open discrepancy with provenance, and gives an
overall readiness status. The overall status and per-requirement checks are
computed deterministically by the readiness engine; agents contribute only
the human-readable narrative sections.
"""
from __future__ import annotations

import enum
from typing import List, Optional

from pydantic import BaseModel, Field

from .discrepancy import Discrepancy


class ReadinessStatus(str, enum.Enum):
    """Deterministic overall verdict for the case."""

    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"   # all critical requirements satisfied, no blocking issues
    MISSING_EVIDENCE = "missing_evidence"               # a required document/field is absent
    CONFLICT = "conflict"                               # a cross-document conflict is unresolved
    BLOCKED = "blocked"                                 # one or more critical discrepancies block progression


class RequirementCheck(BaseModel):
    """Per-requirement satisfied/unsatisfied result, source-linked."""

    requirement_id: str
    description: str
    satisfied: bool
    satisfied_by_document_id: Optional[str] = Field(
        default=None, description="Which document satisfied it (provenance), if satisfied."
    )
    critical: bool = True
    note: Optional[str] = Field(default=None, description="Why it is/ isn't satisfied, deterministic.")


class ReadinessReport(BaseModel):
    """The final, source-linked case-readiness report."""

    case_id: str
    payer_id: Optional[str] = None
    cpt_code: Optional[str] = None
    matched_rule_id: Optional[str] = None

    status: ReadinessStatus
    requirement_checks: List[RequirementCheck] = Field(default_factory=list)
    discrepancies: List[Discrepancy] = Field(default_factory=list)

    # Narrative sections (agent-authored) - never override `status`.
    summary: Optional[str] = Field(default=None, description="Plain-language summary for the reviewer.")
    safety_notes: Optional[str] = Field(default=None, description="Safety Critic's independent assessment.")

    # Derived convenience fields.
    def satisfied_requirements(self) -> List[RequirementCheck]:
        return [c for c in self.requirement_checks if c.satisfied]

    def unsatisfied_requirements(self) -> List[RequirementCheck]:
        return [c for c in self.requirement_checks if not c.satisfied]

    def blocking_discrepancies(self) -> List[Discrepancy]:
        return [d for d in self.discrepancies if d.is_blocking()]

    def can_progress(self) -> bool:
        """Deterministic gate: a case may progress only when ready and with no
        blocking discrepancies. The orchestrator/state engine consults this -
        it is never decided by a model."""
        return self.status == ReadinessStatus.READY_FOR_HUMAN_REVIEW and not self.blocking_discrepancies()
