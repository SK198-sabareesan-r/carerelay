"""Evidence model: the documents and extracted fields for one prior-auth case.

A `CaseEvidence` is the normalized, source-linked view of everything the
clinic submitted for a case - the insurance card, procedure order, clinical
notes, imaging report, payer policy, etc. Each extracted field carries a
`source` pointer (which document it came from) and a `confidence`, so every
downstream claim is traceable back to a document. This traceability is what
lets the readiness report say "satisfied by clinical_notes" rather than just
"satisfied".
"""
from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentKind(str, enum.Enum):
    """The document types CareRelay Sentinel understands. `UNKNOWN` is used
    when the Document Intelligence agent cannot confidently classify a file -
    that itself becomes a low-confidence signal the readiness engine flags."""

    INSURANCE_CARD = "insurance_card"
    PROCEDURE_ORDER = "procedure_order"
    CLINICAL_NOTES = "clinical_notes"
    IMAGING_REPORT = "xray_or_mri"
    CONSERVATIVE_TREATMENT_HISTORY = "conservative_treatment_history"
    REFERRAL = "referral"
    LAB_RESULT = "lab_result"
    PAYER_POLICY = "payer_policy"
    UNKNOWN = "unknown"


class FieldConfidence(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractedField(BaseModel):
    """A single field pulled from a document, with provenance + confidence.

    `source_document_id` links the value back to the exact `EvidenceDocument`
    it was read from, so a reconciliation conflict can name both sides
    (e.g. "cpt_code=29881 in procedure_order vs 29826 in clinical_notes")."""

    name: str = Field(description="Canonical field name, e.g. 'cpt_code', 'patient_name', 'member_id'.")
    value: Optional[str] = Field(default=None, description="Extracted value as printed, or null if unreadable.")
    source_document_id: str = Field(description="id of the EvidenceDocument this field came from.")
    confidence: FieldConfidence = FieldConfidence.HIGH
    note: Optional[str] = Field(default=None, description="Optional provenance note, e.g. 'partially obscured'.")


class EvidenceDocument(BaseModel):
    """One submitted file in the case, after classification + extraction."""

    id: str = Field(description="Stable per-case document id, e.g. 'doc-order', 'doc-notes'.")
    kind: DocumentKind = DocumentKind.UNKNOWN
    s3_key: Optional[str] = Field(default=None, description="S3 object key, if stored. None for synthetic/test docs.")
    legible: bool = True
    classification_confidence: FieldConfidence = FieldConfidence.HIGH
    fields: List[ExtractedField] = Field(default_factory=list)
    raw_text: Optional[str] = Field(default=None, description="Optional extracted/supplied text body of the document.")

    def field(self, name: str) -> Optional[ExtractedField]:
        """First extracted field with the given canonical name, or None."""
        for f in self.fields:
            if f.name == name:
                return f
        return None


class CaseEvidence(BaseModel):
    """Everything known about a case's documents, normalized and traceable."""

    case_id: str
    patient_name: Optional[str] = None
    payer_id: Optional[str] = Field(default=None, description="Canonical payer id if resolvable from the card.")
    cpt_code: Optional[str] = Field(default=None, description="The case-level CPT the clinic is pursuing.")
    procedure_name: Optional[str] = None
    documents: List[EvidenceDocument] = Field(default_factory=list)
    symptom_summary: Optional[str] = None

    # Convenience accessors -------------------------------------------------
    def document_kinds(self) -> List[DocumentKind]:
        return [d.kind for d in self.documents]

    def has_kind(self, kind: DocumentKind) -> bool:
        return any(d.kind == kind for d in self.documents)

    def documents_on_file(self) -> List[str]:
        """The deterministic rules engine expects a list of document-type
        strings (its `required_documents` vocabulary). We map our
        DocumentKind values to that vocabulary here so the existing
        rules_engine.evaluate() keeps working unchanged."""
        return [d.kind.value for d in self.documents if d.kind != DocumentKind.UNKNOWN]

    def all_fields(self, name: str) -> List[ExtractedField]:
        """Every extracted field with this name across all documents -
        used by the reconciliation service to detect cross-document
        mismatches (e.g. two different cpt_code values)."""
        out: List[ExtractedField] = []
        for d in self.documents:
            for f in d.fields:
                if f.name == name:
                    out.append(f)
        return out

    def low_confidence_fields(self) -> List[ExtractedField]:
        out: List[ExtractedField] = []
        for d in self.documents:
            for f in d.fields:
                if f.confidence == FieldConfidence.LOW:
                    out.append(f)
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CaseEvidence":
        return cls.model_validate(data)
