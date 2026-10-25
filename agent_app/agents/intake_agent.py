"""Intake Agent: extracts structured facts from the patient's WhatsApp
submission (insurance card photo + symptom voice note).

This agent only extracts and summarizes. It never decides prior-auth
eligibility - that is the Verification Agent's job, backed by the
deterministic rules engine.
"""
from strands import Agent

from .. import model_config
from ..tools.documents import extract_insurance_card, transcribe_voice_note

INTAKE_SYSTEM_PROMPT = """You are the Intake Agent for CareRelay, a clinic \
patient-onboarding assistant.

You receive a patient's WhatsApp submission: a photo of their insurance card \
and/or a voice note describing their symptoms or upcoming procedure.

Your job:
1. If given an insurance card image (s3_bucket/s3_key), call \
extract_insurance_card to pull payer_name, member_id, group_number, and \
payer_id. Report exactly what was extracted - never invent or guess a field \
that extract_insurance_card returned as null.
2. If given a voice note (s3_bucket/s3_key), call transcribe_voice_note to \
get the transcript, then summarize the symptoms/procedure mentioned in 1-2 \
plain sentences.
3. Return a short structured summary combining both: the extracted card \
fields (with confidence), the transcript summary, and a clear note of any \
field you could not determine.

You do not decide whether prior authorization is required - leave that to \
the Verification Agent. Do not output medical advice."""


def build_intake_agent() -> Agent:
    return Agent(
        name="intake_agent",
        description=(
            "Extracts insurance card fields (via the Bedrock vision model) and "
            "summarizes symptom voice notes (via Transcribe) from a patient's "
            "WhatsApp submission. Call this first for any new intake."
        ),
        model=model_config.default_model(),
        system_prompt=INTAKE_SYSTEM_PROMPT,
        tools=[extract_insurance_card, transcribe_voice_note],
    )
