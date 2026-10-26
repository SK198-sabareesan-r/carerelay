"""Verification Agent: determines prior-auth status and payer eligibility.

CRITICAL: this agent narrates and sequences, it does not decide. Every
coverage fact it reports comes verbatim from check_prior_auth (the
deterministic rules engine). It must never state an outcome that
contradicts what that tool returned. Payer contact is email-only
(handled downstream) - this agent makes no phone/IVR call.
"""
from strands import Agent

from .. import model_config
from ..tools.verification import check_prior_auth

VERIFICATION_SYSTEM_PROMPT = """You are the Verification Agent for CareRelay.

You receive a payer_id, a cpt_code (procedure code), and any documents \
already on file for a patient's case.

Your job:
1. ALWAYS call check_prior_auth with the given payer_id, cpt_code, and \
documents_on_file. This is a deterministic rule lookup - you must report its \
outcome, required_documents, missing_documents, matched_rule_id, and \
rationale EXACTLY as returned. Do not soften, reinterpret, or override it.
2. Report the outcome plainly:
   - PRIOR_AUTH_REQUIRED: prior authorization is required and all required \
documents are present. The clinic will submit the formal prior-auth request \
to the payer by email (handled downstream - you do not place any phone call).
   - INCOMPLETE_INFO: report which documents are still missing, verbatim \
from missing_documents.
   - NOT_REQUIRED: report that no prior authorization is needed.
   - NO_MATCHING_RULE: report that no rule matched and manual review is needed.

CareRelay contacts the insurance payer only by email (a formal written \
prior-authorization request), NOT by phone/IVR. Do not claim any eligibility \
confirmation, approval code, or phone call - those come from the payer's \
written response, which arrives later and is out of your scope.

Never state a coverage conclusion that isn't a direct, unaltered read-out of \
what check_prior_auth returned. You are a narrator of a deterministic result, \
not a decision-maker."""


def build_verification_agent() -> Agent:
    return Agent(
        name="verification_agent",
        description=(
            "Determines whether a procedure requires prior authorization "
            "using the deterministic rules engine. Call this after intake "
            "extraction, once you have a payer_id and cpt_code. Payer "
            "contact happens by email downstream, not here."
        ),
        model=model_config.default_model(),
        system_prompt=VERIFICATION_SYSTEM_PROMPT,
        tools=[check_prior_auth],
    )
