"""Pydantic schema for the supervisor's final case result.

The supervisor agent is configured with structured_output_model=CaseResult,
so Strands guarantees the final response validates against this schema
instead of relying on the model to format free-text JSON correctly. This is
the hand-off contract between the AgentCore Runtime and channel_dispatcher
Lambda: the Lambda only ever reads these typed fields, never parses prose.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedCard(BaseModel):
    payer_name: Optional[str] = None
    member_id: Optional[str] = None
    group_number: Optional[str] = None
    payer_id: Optional[str] = None
    confidence: float = 0.0


class CardVisionExtraction(BaseModel):
    """Strict-JSON contract for the Bedrock vision-model insurance-card read.

    Used only inside tools/documents.py to validate the vision model's raw
    output before it is reshaped into the extract_insurance_card tool
    result. Keeping this separate from ExtractedCard (the agent-facing
    shape) lets the vision prompt enforce its own null/uncertainty rules
    without coupling to how the rest of the pipeline consumes the field.
    """

    payer_name: Optional[str] = Field(
        default=None, description="Insurance company / plan name as printed on the card, or null if not visible."
    )
    member_id: Optional[str] = Field(
        default=None, description="Member/Subscriber/Policy ID as printed on the card, or null if not visible."
    )
    group_number: Optional[str] = Field(
        default=None, description="Group number as printed on the card, or null if not visible."
    )
    payer_id: Optional[str] = Field(
        default=None, description="Electronic payer ID as printed on the card, or null if not visible."
    )
    legible: bool = Field(description="False if the photo is too blurry/dark/cropped to read reliably.")
    uncertain_fields: List[str] = Field(
        default_factory=list,
        description="Field names the model is NOT confident about, even if a value was still returned for them.",
    )


class VerificationResult(BaseModel):
    outcome: str = Field(
        description="PRIOR_AUTH_REQUIRED | NOT_REQUIRED | INCOMPLETE_INFO | NO_MATCHING_RULE, "
        "verbatim from check_prior_auth - never altered by the model."
    )
    requires_prior_auth: bool
    missing_documents: List[str] = Field(default_factory=list)
    matched_rule_id: Optional[str] = None
    rationale: str = Field(description="Verbatim rule rationale, not a model paraphrase.")
    payer_simulated: bool = Field(
        default=False, description="True if call_payer_ivr was invoked for this case."
    )
    payer_eligible: Optional[bool] = None
    approval_code: Optional[str] = None


class DraftedMessages(BaseModel):
    patient_message_body: str
    patient_message_buttons: List[dict] = Field(default_factory=list)
    doctor_card_body: str
    doctor_card_buttons: List[dict] = Field(default_factory=list)
    audit_headline: str
    audit_detail_lines: List[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    """The supervisor's single structured response for one patient case."""

    symptom_summary: Optional[str] = None
    extracted_card: ExtractedCard = Field(default_factory=ExtractedCard)
    verification: VerificationResult
    messages: DraftedMessages
