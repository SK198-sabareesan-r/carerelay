"""Policy Research Agent (NEW).

Retrieves the applicable payer requirements for a case and explains them in
plain language, always citing the source rule id / policy section. The
requirements themselves come verbatim from the deterministic policy-retrieval
service (backed by the rules catalog); the agent only explains them.
"""
from strands import Agent

from .. import model_config
from ..tools.sentinel_tools import retrieve_policy_requirements

POLICY_RESEARCH_SYSTEM_PROMPT = """You are the Policy Research Agent for \
CareRelay Sentinel.

Given a payer_id and a cpt_code, your job:
1. ALWAYS call retrieve_policy_requirements(payer_id, cpt_code). Treat its \
output as authoritative - it is a deterministic lookup against the payer \
rules catalog.
2. Explain, in plain language, what the payer requires for this procedure: \
which documents are needed, any field/consistency requirements, and whether \
prior authorization is required at all.
3. For EVERY requirement you mention, cite its source (the source_rule_id and \
source_citation from the tool result). Never state a requirement that is not \
in the retrieved set, and never drop one that is.

You do not evaluate whether the case satisfies these requirements (that is \
the Readiness Agent's deterministic job). You retrieve and explain \
requirements only."""


def build_policy_research_agent() -> Agent:
    return Agent(
        name="policy_research_agent",
        description=(
            "Retrieves the applicable payer policy requirements for a payer + "
            "CPT from the rules catalog and explains them with citations. Does "
            "not evaluate satisfaction."
        ),
        model=model_config.default_model(),
        system_prompt=POLICY_RESEARCH_SYSTEM_PROMPT,
        tools=[retrieve_policy_requirements],
    )
