"""Normalized data models shared across the CareRelay pipeline.

Inbound WhatsApp messages (card photo, voice note, text, button taps) are
normalized into `InboundIntakeMessage`. The deterministic rules engine
produces a `RuleDecision`. Keeping these separate from the Bedrock narration
layer is what makes "code decides, AI talks" auditable: every RuleDecision
field traces to a specific rule, never to a model completion.
"""
import dataclasses
from typing import Optional, Dict, Any, List

CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_RCS = "rcs"
CHANNEL_SMS = "sms"

KIND_TEXT = "text"
KIND_IMAGE = "image"
KIND_AUDIO = "audio"
KIND_BUTTON = "button"
KIND_UNKNOWN = "unknown"

PRIOR_AUTH_REQUIRED = "PRIOR_AUTH_REQUIRED"
PRIOR_AUTH_NOT_REQUIRED = "NOT_REQUIRED"
PRIOR_AUTH_INCOMPLETE = "INCOMPLETE_INFO"

STATUS_AWAITING_DOCS = "AWAITING_DOCUMENTS"
STATUS_PENDING_PAYER = "PENDING_PAYER_VERIFICATION"
STATUS_PENDING_DOCTOR = "PENDING_DOCTOR_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_DENIED = "DENIED"


@dataclasses.dataclass
class InboundIntakeMessage:
    """A single normalized inbound WhatsApp message from a patient."""

    channel: str
    kind: str
    sender: str  # patient's E.164 WhatsApp number
    phone_number_id: str  # origination phone-number-id (needed to reply / fetch media)
    message_id: str
    timestamp: str
    text: Optional[str] = None
    media_id: Optional[str] = None
    media_mime: Optional[str] = None
    button_payload: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def to_item(self, ttl_epoch: int) -> Dict[str, Any]:
        return {
            "pk": f"PATIENT#{self.sender}",
            "sk": f"{self.timestamp}#{self.message_id}",
            "channel": self.channel,
            "kind": self.kind,
            "sender": self.sender,
            "phone_number_id": self.phone_number_id,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
            "text": self.text,
            "media_id": self.media_id,
            "media_mime": self.media_mime,
            "button_payload": self.button_payload,
            "s3_media_key": None,
            "ttl": ttl_epoch,
        }


@dataclasses.dataclass
class ExtractedInsuranceCard:
    """Fields pulled from the insurance card photo by the Bedrock vision
    model (see agent_app/tools/documents.py).

    Fields are null unless the model actually read them off the card image;
    see agent_app/schemas.CardVisionExtraction for the strict-JSON contract
    enforced on the model's output.
    """

    payer_name: Optional[str] = None
    member_id: Optional[str] = None
    group_number: Optional[str] = None
    payer_id: Optional[str] = None
    raw_text_lines: Optional[List[str]] = None
    confidence: float = 0.0


@dataclasses.dataclass
class RuleDecision:
    """Output of the deterministic prior-authorization rules engine.

    This is the auditable core of CareRelay: every field below is produced by
    plain Python rule evaluation against PayerRulesTable, never by an LLM.
    """

    cpt_code: str
    payer_id: str
    requires_prior_auth: bool
    outcome: str  # PRIOR_AUTH_REQUIRED | NOT_REQUIRED | INCOMPLETE_INFO
    missing_documents: List[str]
    matched_rule_id: Optional[str]
    rationale: str  # plain statement of which rule fired, no model involved

    def to_item(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
