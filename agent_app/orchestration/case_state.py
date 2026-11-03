"""Shared, serializable state for a single case run through the pipeline.

CaseState is the one object that flows through the graph, workflow, and swarm.
It accumulates the deterministic artifacts (evidence, requirements,
discrepancies, readiness report, decider action, safety verdict) plus the
audit trail. Keeping it a plain dataclass of model objects (not an agent
conversation) means the pipeline's state is always inspectable and testable
without any model call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models import (
    AgentDecision,
    CaseEvidence,
    Discrepancy,
    PolicyRequirementSet,
    ReadinessReport,
    SafetyVerdict,
)
from ..services.audit_service import AuditTrail


@dataclass
class CaseState:
    case_id: str
    evidence: Optional[CaseEvidence] = None
    requirement_set: Optional[PolicyRequirementSet] = None
    discrepancies: List[Discrepancy] = field(default_factory=list)
    readiness: Optional[ReadinessReport] = None
    decision: Optional[AgentDecision] = None
    safety_verdict: Optional[SafetyVerdict] = None

    # Narrative produced by the swarm during exception investigation.
    investigation_narrative: Optional[str] = None

    # The case status this run started from (for the state-transition gate).
    current_status: str = "UNDER_REVIEW"

    audit: AuditTrail = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.audit is None:
            self.audit = AuditTrail(self.case_id)

    # Convenience predicates used by the graph edge conditions ------------
    def has_blocking_conflict(self) -> bool:
        return any(d.is_blocking() for d in self.discrepancies) or (
            self.readiness is not None and bool(self.readiness.blocking_discrepancies())
        )

    def has_critical_conflict(self) -> bool:
        """A critical cross-document mismatch - the trigger for the Swarm."""
        from ..models import DiscrepancyKind, Severity

        pool = list(self.discrepancies)
        if self.readiness is not None:
            pool = list(self.readiness.discrepancies)
        return any(
            d.kind == DiscrepancyKind.FIELD_MISMATCH
            and d.severity == Severity.CRITICAL
            and not d.resolved
            for d in pool
        )

    def to_dict(self) -> Dict[str, Any]:
        """Full serializable snapshot - what the dashboard / tests consume."""
        return {
            "case_id": self.case_id,
            "current_status": self.current_status,
            "evidence": self.evidence.model_dump() if self.evidence else None,
            "requirement_set": self.requirement_set.model_dump() if self.requirement_set else None,
            "discrepancies": [d.model_dump() for d in self.discrepancies],
            "readiness": self.readiness.model_dump() if self.readiness else None,
            "decision": self.decision.model_dump() if self.decision else None,
            "safety_verdict": self.safety_verdict.model_dump() if self.safety_verdict else None,
            "investigation_narrative": self.investigation_narrative,
            "audit": self.audit.to_list(),
            "can_progress": self.readiness.can_progress() if self.readiness else False,
        }
