"""The CareRelay Sentinel agent roster: one place to build every specialist.

Seven agents total - two carried over from the original CareRelay (Intake,
Notification) and five new Sentinel specialists (Document Intelligence, Policy
Research, Clinical Consistency, Case Readiness, Safety Critic). The
orchestration layer (orchestration/case_graph.py, exception_swarm.py) imports
these builders rather than constructing agents inline, so the graph/swarm
wiring stays readable and the agent set is defined in exactly one place.

Every agent uses the same shared Bedrock model (model_config.default_model())
and the "code decides, AI talks" contract: perception + narration in the
agents, decisions in the deterministic services/rules.
"""
from __future__ import annotations

from typing import Callable, Dict

from strands import Agent

from .intake_agent import build_intake_agent
from .notification_agent import build_notification_agent
from .document_agent import build_document_agent
from .policy_research_agent import build_policy_research_agent
from .clinical_consistency_agent import build_clinical_consistency_agent
from .readiness_agent import build_readiness_agent
from .safety_critic_agent import build_safety_critic_agent

# name -> builder, so callers can build individually or in bulk.
AGENT_BUILDERS: Dict[str, Callable[[], Agent]] = {
    "intake_agent": build_intake_agent,
    "document_agent": build_document_agent,
    "policy_research_agent": build_policy_research_agent,
    "clinical_consistency_agent": build_clinical_consistency_agent,
    "readiness_agent": build_readiness_agent,
    "safety_critic_agent": build_safety_critic_agent,
    "notification_agent": build_notification_agent,
}

# The subset that participates in the exception-investigation Swarm. The
# Safety Critic is always included so no swarm resolution escapes review.
SWARM_AGENT_NAMES = [
    "document_agent",
    "policy_research_agent",
    "clinical_consistency_agent",
    "safety_critic_agent",
]


def build_all() -> Dict[str, Agent]:
    """Instantiate every roster agent once and return them by name."""
    return {name: builder() for name, builder in AGENT_BUILDERS.items()}


def build_subset(names) -> Dict[str, Agent]:
    """Instantiate only the named agents (e.g. the swarm subset)."""
    return {name: AGENT_BUILDERS[name]() for name in names}
