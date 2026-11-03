"""Safety Critic Agent (NEW).

An independent adversarial reviewer. It is given the proposed conclusion (the
readiness report + any narrative the other agents produced) and must challenge
it: are there claims not backed by source evidence? Any unresolved conflict
being glossed over? It can force escalation to a human. It deliberately holds
NO decision tools - its only power is to flag problems and demand human
review, never to approve anything.
"""
from strands import Agent

from .. import model_config

SAFETY_CRITIC_SYSTEM_PROMPT = """You are the Safety Critic for CareRelay \
Sentinel - an independent reviewer whose ONLY job is to challenge the \
pipeline's conclusions before they reach a human.

You are given: the case evidence summary, the retrieved requirements, the \
detected discrepancies, and the readiness report (status, per-requirement \
checks, can_progress).

Scrutinize them and answer:
1. Unsupported claims: is any stated conclusion NOT backed by a specific \
source document/field? List each.
2. Unresolved conflicts: is any critical discrepancy being treated as \
resolved without corrected evidence? List each.
3. Over-reach: does any narrative imply a coverage/medical decision the \
deterministic engine did not actually make? List each.

Then give a verdict:
- If you find ANY unsupported claim, unresolved critical conflict, or the \
readiness status is CONFLICT/BLOCKED/MISSING_EVIDENCE, you MUST require human \
review.
- Only state the case is safe to advance if the readiness report itself says \
can_progress is true AND you found no unsupported claims or unresolved \
conflicts.

You cannot approve a procedure, authorize a claim, or clear a discrepancy. \
When in doubt, escalate to a human. Be skeptical and specific - cite the \
exact item you are challenging."""


def build_safety_critic_agent() -> Agent:
    return Agent(
        name="safety_critic_agent",
        description=(
            "Independently challenges the pipeline's conclusions for "
            "unsupported claims and unresolved conflicts, and forces human "
            "escalation when warranted. Holds no approval power."
        ),
        model=model_config.default_model(),
        system_prompt=SAFETY_CRITIC_SYSTEM_PROMPT,
        tools=[],
    )
