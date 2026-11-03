"""Clinical Consistency Agent (NEW).

Compares the case documents against each other to surface conflicts and gaps
(e.g. a procedure code in the order that disagrees with the clinical notes).
The deterministic reconciliation service does the actual detection; this agent
explains each detected discrepancy in clinical terms and proposes a concrete
human follow-up. It cannot create or clear a discrepancy.
"""
from strands import Agent

from .. import model_config
from ..tools.sentinel_tools import detect_discrepancies

CLINICAL_CONSISTENCY_SYSTEM_PROMPT = """You are the Clinical Consistency \
Agent for CareRelay Sentinel.

Given the case evidence (documents + extracted fields), your job:
1. ALWAYS call detect_discrepancies(case_evidence). This deterministic tool \
finds cross-document field mismatches, low-confidence reads, and illegible \
documents. Its output is the complete, authoritative list - you may not add \
a discrepancy it didn't find, nor dismiss one it did.
2. For each discrepancy, explain in plain clinical/administrative language \
what disagrees, between which documents, and why it matters for the prior \
authorization.
3. Propose a specific, actionable human follow-up for each (e.g. "request a \
corrected procedure order so the CPT matches the clinical notes").

Quote the differing values exactly as the tool reported them. Do not guess \
which value is "correct" - flag the conflict for a human. You surface and \
explain inconsistencies; you never decide coverage or resolve a conflict \
unilaterally."""


def build_clinical_consistency_agent() -> Agent:
    return Agent(
        name="clinical_consistency_agent",
        description=(
            "Compares case documents to surface cross-document conflicts, "
            "gaps, and low-confidence reads, explaining each and proposing a "
            "human follow-up. Detection is deterministic."
        ),
        model=model_config.default_model(),
        system_prompt=CLINICAL_CONSISTENCY_SYSTEM_PROMPT,
        tools=[detect_discrepancies],
    )
