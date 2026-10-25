"""Supervisor: orchestrates Intake -> Verification -> Notification using the
Strands "agents as tools" pattern.

The supervisor is itself a Strands Agent whose `tools` list contains the
three specialist agents directly (Strands wraps each agent as a callable
tool automatically, using its `name`/`description`). The supervisor decides
WHEN to call each specialist and in what order, but it never touches
coverage logic itself - that still lives only in rules_engine.py, reached
through the Verification Agent's check_prior_auth tool.
"""
from strands import Agent

from .. import model_config
from ..schemas import CaseResult
from .intake_agent import build_intake_agent
from .verification_agent import build_verification_agent
from .notification_agent import build_notification_agent

SUPERVISOR_SYSTEM_PROMPT = """You are the CareRelay Supervisor, coordinating \
a patient prior-authorization intake case end to end.

You have three specialist agents as tools: intake_agent, verification_agent, \
and notification_agent. For every case, call them IN THIS ORDER:

1. intake_agent - give it the S3 locations of the patient's insurance card \
photo and/or voice note (and the cpt_code/procedure_name for the planned \
treatment if already known). It returns extracted card fields and a symptom \
summary.
2. verification_agent - give it the payer_id (map from the extracted \
payer_name if needed, otherwise "PAYER-UNKNOWN") and cpt_code, plus any \
documents_on_file you already know about. It returns the prior-auth outcome, \
required/missing documents, and (if applicable) the simulated payer \
eligibility result. Treat everything it reports as ground truth - you must \
not change or second-guess the outcome it gives you.
3. notification_agent - give it the case identifiers and the exact outcome \
from step 2. It drafts the patient message, the doctor approval card, and \
the audit summary.

Your final response MUST conform to the required structured output schema. \
Populate verification.outcome, verification.missing_documents, and \
verification.rationale with EXACTLY what verification_agent reported -
never alter, soften, or second-guess a coverage outcome. Populate \
verification.payer_simulated/payer_eligible/approval_code only if \
verification_agent actually ran the simulated payer check; otherwise leave \
them at their defaults. You are a coordinator and narrator, not a \
decision-maker."""


def build_supervisor() -> Agent:
    intake = build_intake_agent()
    verification = build_verification_agent()
    notification = build_notification_agent()

    return Agent(
        name="carerelay_supervisor",
        description="Coordinates the end-to-end CareRelay prior-auth intake case.",
        model=model_config.default_model(),
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        tools=[intake, verification, notification],
        structured_output_model=CaseResult,
    )
