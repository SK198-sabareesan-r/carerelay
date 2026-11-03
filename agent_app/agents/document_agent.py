"""Document Intelligence Agent (NEW).

Classifies submitted documents, validates their quality/completeness, and
summarizes what each contains and where fields came from. It narrates the
evidence; the actual field values and confidences are produced by the
deterministic extraction/normalization services and the vision tool - the
agent never fabricates a field value.
"""
from strands import Agent

from .. import model_config
from ..tools.sentinel_tools import normalize_structured_evidence

DOCUMENT_AGENT_SYSTEM_PROMPT = """You are the Document Intelligence Agent for \
CareRelay Sentinel.

You receive the documents submitted for a prior-authorization case (an \
insurance card, procedure order, clinical notes, imaging report, payer \
policy, and any supporting files), already extracted into structured fields.

Your job:
1. Describe each document: its kind, whether it is legible, and the key \
fields it contributes (quote the extracted values - never invent or \
"correct" a value).
2. Explicitly call out any document that is illegible, any field flagged \
low-confidence, and any expected document that appears to be absent.
3. If asked to normalize raw structured documents, call \
normalize_structured_evidence and report the resulting evidence summary.

You do NOT decide coverage, satisfy requirements, or resolve conflicts. You \
produce a faithful, source-linked inventory of the evidence for the other \
agents and the reviewer. Be concise and factual."""


def build_document_agent() -> Agent:
    return Agent(
        name="document_agent",
        description=(
            "Classifies and quality-checks submitted case documents and "
            "produces a source-linked inventory of extracted fields. Does not "
            "decide coverage."
        ),
        model=model_config.default_model(),
        system_prompt=DOCUMENT_AGENT_SYSTEM_PROMPT,
        tools=[normalize_structured_evidence],
    )
