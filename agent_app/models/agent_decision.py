"""Agent decision models: the bounded Decider action and the Safety Critic
verdict.

Decider 2B is a *bounded* router: given a compact, structured case state it
selects exactly one next processing action from a closed set. It never
approves a procedure or authorizes a claim - it only chooses what the
pipeline does next. The Safety Critic independently challenges the pipeline's
conclusions and can force escalation to a human.
"""
from __future__ import annotations

import enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DeciderAction(str, enum.Enum):
    """The closed set of next-actions Decider 2B may choose. This is the
    ENTIRE decision space of the router - nothing outside this set is a valid
    output, which is what keeps the decision bounded and auditable."""

    CONTINUE_VERIFICATION = "CONTINUE_VERIFICATION"        # normal path: run deterministic readiness
    REQUEST_MISSING_EVIDENCE = "REQUEST_MISSING_EVIDENCE"  # ask the clinic/patient for a missing document
    INVESTIGATE_CONFLICT = "INVESTIGATE_CONFLICT"          # hand off to the exception Swarm
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"        # stop; a human must resolve


class AgentDecision(BaseModel):
    """A single routing decision with provenance + confidence.

    `rule_based` records whether a deterministic rule produced this routing
    (preferred) or the Decider model did - so we can benchmark the Decider
    against plain rules, exactly as the implementation plan requires."""

    action: DeciderAction
    reason: str = Field(description="Why this action was chosen, referencing concrete case state.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rule_based: bool = Field(
        default=True, description="True if a deterministic rule chose this; False if the Decider model did."
    )
    considered_actions: List[DeciderAction] = Field(
        default_factory=list, description="The allowed choices presented to the router for this state."
    )


class SafetyVerdict(BaseModel):
    """The Safety Critic's independent review of a proposed conclusion."""

    approved: bool = Field(description="True only if the critic found no unsupported claims / unresolved conflicts.")
    unsupported_claims: List[str] = Field(
        default_factory=list, description="Conclusions not backed by source evidence."
    )
    unresolved_conflicts: List[str] = Field(
        default_factory=list, description="Discrepancies the critic judged still open."
    )
    requires_human_review: bool = Field(
        default=False, description="Force escalation regardless of the readiness status."
    )
    notes: Optional[str] = Field(default=None, description="Plain-language assessment for the report.")
