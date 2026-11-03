"""Shared data models for the CareRelay Sentinel evidence-reconciliation and
exception-investigation layer.

These Pydantic models are the hand-off contract between the deterministic
services (agent_app/services/*), the specialist agents (agent_app/agents/*),
and the orchestration layer (agent_app/orchestration/*).

Design rule that mirrors the rest of CareRelay ("code decides, AI talks"):
every *decision-bearing* field here (a discrepancy severity, a readiness
status, a satisfied/unsatisfied requirement) is produced by deterministic
services, not by a model. Agents produce *narrative* fields (explanations,
summaries). The models keep the two clearly separated so the deterministic
truth is never silently overwritten by model prose.
"""
from .case_evidence import (
    CaseEvidence,
    DocumentKind,
    EvidenceDocument,
    ExtractedField,
    FieldConfidence,
)
from .policy_requirement import (
    PolicyRequirement,
    PolicyRequirementSet,
    RequirementKind,
)
from .discrepancy import Discrepancy, DiscrepancyKind, Severity
from .readiness_report import (
    ReadinessReport,
    ReadinessStatus,
    RequirementCheck,
)
from .agent_decision import (
    AgentDecision,
    DeciderAction,
    SafetyVerdict,
)

__all__ = [
    # case_evidence
    "CaseEvidence",
    "DocumentKind",
    "EvidenceDocument",
    "ExtractedField",
    "FieldConfidence",
    # policy_requirement
    "PolicyRequirement",
    "PolicyRequirementSet",
    "RequirementKind",
    # discrepancy
    "Discrepancy",
    "DiscrepancyKind",
    "Severity",
    # readiness_report
    "ReadinessReport",
    "ReadinessStatus",
    "RequirementCheck",
    # agent_decision
    "AgentDecision",
    "DeciderAction",
    "SafetyVerdict",
]
