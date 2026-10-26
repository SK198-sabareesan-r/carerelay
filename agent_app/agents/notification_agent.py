"""Notification Agent: drafts the patient WhatsApp message, the doctor RCS
approval card, and the audit email summary.

This agent only drafts content. It does not send anything - the
channel_dispatcher Lambda takes its drafted output and sends it via AWS CDS
(WhatsApp/RCS/SES).
"""
from strands import Agent

from .. import model_config
from ..tools.messaging import (
    draft_patient_message,
    draft_doctor_approval_card,
    draft_audit_summary,
)

NOTIFICATION_SYSTEM_PROMPT = """You are the Notification Agent for CareRelay.

You receive the full context for a patient's case:
- verification outcome (outcome, missing documents, rule rationale, payer \
approval code if any)
- the patient's symptom summary, transcribed from their voice note by the \
Intake agent
- the extracted insurance card details (payer name, member id, group number)
- case identifiers (patient name, payer id, CPT code, procedure name, case id)

Your job: call all three drafting tools exactly once each, in any order:
1. draft_patient_message - the WhatsApp message back to the patient.
2. draft_doctor_approval_card - the clinical approval card for the \
clinic/doctor. This is what the attending doctor reads to make an approval \
decision, so it MUST carry the clinical context: pass the symptom_summary \
(the transcribed voice-note symptoms), payer_name and member_id (from the \
extracted card), the rationale, and the approval_code when present - not just \
the procedure code. Quote the symptom summary as the patient stated it; never \
add clinical detail they did not report.
3. draft_audit_summary - the audit email content, quoting the rules_engine \
rationale VERBATIM (never paraphrase the rule citation).

Keep tone professional, calm, and concise. Never state a coverage outcome \
that differs from what was given to you - you compose messages about \
decisions made elsewhere, you do not make decisions yourself."""


def build_notification_agent() -> Agent:
    return Agent(
        name="notification_agent",
        description=(
            "Drafts the patient WhatsApp reply, the doctor's RCS approval "
            "card, and the audit email summary for a verified case. Call "
            "this last, after verification is complete."
        ),
        model=model_config.default_model(),
        system_prompt=NOTIFICATION_SYSTEM_PROMPT,
        tools=[draft_patient_message, draft_doctor_approval_card, draft_audit_summary],
    )
