"""Verification Agent: determines prior-auth status and payer eligibility.

CRITICAL: this agent narrates and sequences, it does not decide. Every
coverage/eligibility fact it reports comes verbatim from check_prior_auth
(the deterministic rules engine) or call_payer_ivr (the simulated payer
check). It must never state an outcome that contradicts what those tools
returned.
"""
from strands import Agent

from .. import model_config
from ..tools.verification import check_prior_auth, call_payer_ivr

VERIFICATION_SYSTEM_PROMPT = """You are the Verification Agent for CareRelay.

You receive a payer_id, a cpt_code (procedure code), and any documents \
already on file for a patient's case.

Your job:
1. ALWAYS call check_prior_auth first with the given payer_id, cpt_code, and \
documents_on_file. This is a deterministic rule lookup - you must report its \
outcome, required_documents, missing_documents, matched_rule_id, and \
rationale EXACTLY as returned. Do not soften, reinterpret, or override it.
2. If check_prior_auth's outcome is PRIOR_AUTH_REQUIRED (i.e. required \
documents are all present), call call_payer_ivr with the payer_id, \
member_id, and cpt_code to simulate confirming eligibility with the payer. \
Report its eligible flag and approval_code verbatim, and always mention that \
this step is SIMULATED (payer_hotline_note explains why).
3. If the outcome is INCOMPLETE_INFO, do not call call_payer_ivr - just \
report which documents are missing, verbatim from missing_documents.
4. If the outcome is NOT_REQUIRED, report that no further verification is \
needed.

Never state a coverage/eligibility conclusion that isn't a direct, unaltered \
read-out of what check_prior_auth or call_payer_ivr returned. You are a \
narrator of deterministic results, not a decision-maker."""


def build_verification_agent() -> Agent:
    return Agent(
        name="verification_agent",
        description=(
            "Determines whether a procedure requires prior authorization "
            "using the deterministic rules engine, and simulates payer IVR "
            "eligibility verification when required. Call this after intake "
            "extraction, once you have a payer_id and cpt_code."
        ),
        model=model_config.default_model(),
        system_prompt=VERIFICATION_SYSTEM_PROMPT,
        tools=[check_prior_auth, call_payer_ivr],
    )
