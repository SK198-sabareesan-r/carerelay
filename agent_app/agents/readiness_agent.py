"""Case Readiness Agent (NEW).

Produces the human-readable case-readiness summary by invoking the
deterministic readiness engine and narrating its result: which requirements
are satisfied (and by which document), which are missing or conflicting, and
the overall status. The status and per-requirement verdicts come from the
engine; the agent only writes the summary prose around them.
"""
from strands import Agent

from .. import model_config
from ..tools.sentinel_tools import compute_readiness

READINESS_AGENT_SYSTEM_PROMPT = """You are the Case Readiness Agent for \
CareRelay Sentinel.

Given the case evidence, the retrieved requirement set, and the detected \
discrepancies, your job:
1. ALWAYS call compute_readiness(case_evidence, requirement_set, \
discrepancies). This returns the authoritative per-requirement checks, the \
full discrepancy list, the overall `status`, and `can_progress`.
2. Write a clear readiness summary for the clinic reviewer: state the overall \
status first, then list what is satisfied (naming the document that \
satisfied each requirement), what is missing, and what is conflicting.
3. Report `status` and `can_progress` EXACTLY as the tool returned them. If \
`can_progress` is false, say plainly that the case cannot proceed until the \
listed items are resolved by a human.

You never upgrade a status, mark a case ready when the tool said it is not, \
or omit an unsatisfied critical requirement. You are the narrator of a \
deterministic readiness verdict."""


def build_readiness_agent() -> Agent:
    return Agent(
        name="readiness_agent",
        description=(
            "Narrates the deterministic case-readiness verdict: satisfied vs "
            "missing vs conflicting requirements and the overall status. Never "
            "overrides the engine."
        ),
        model=model_config.default_model(),
        system_prompt=READINESS_AGENT_SYSTEM_PROMPT,
        tools=[compute_readiness],
    )
