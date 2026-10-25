"""CareRelay agent backend: a Strands multi-agent application hosted on
Amazon Bedrock AgentCore Runtime.

Architecture rule (do not violate this when extending the codebase):

    CODE DECIDES, AI TALKS.

    `rules_engine.py` is plain, deterministic Python. It is the only place
    that decides whether a prior authorization is required, what documents
    are missing, and what the final outcome is. It contains no model calls
    and no Strands agent.

    The Strands agents in `agents/` and the tools in `tools/` only narrate,
    summarize, extract, and communicate. When an agent needs a coverage
    decision, it calls the `check_prior_auth` tool, which is a thin wrapper
    around `rules_engine.evaluate()` - the agent cannot see or influence the
    rule logic, it can only read the structured result.

This separation exists so every prior-authorization outcome is auditable
back to a specific rule row, independent of anything a language model
generated, which is the core trust claim of CareRelay.
"""
