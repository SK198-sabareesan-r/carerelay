"""Deterministic evidence normalization.

Turns raw case inputs into a CaseEvidence model. Two entry points:

  - from_structured_documents(...): build evidence from already-structured
    document dicts (used by the synthetic test scenario and by any caller that
    has pre-extracted fields). This path is pure Python, zero AWS.

  - from_live_intake(...): build evidence from the live intake tools - the
    Bedrock vision card read (tools.documents.extract_insurance_card) and
    Transcribe (transcribe_voice_note). Only this path touches AWS, and it
    only EXTRACTS; it makes no decision.

Normalization (payer-id canonicalization, document-kind coercion) is done
here so every downstream service sees one consistent shape.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import rules_engine
from ..models import (
    CaseEvidence,
    DocumentKind,
    EvidenceDocument,
    ExtractedField,
    FieldConfidence,
)


def _coerce_kind(raw: str) -> DocumentKind:
    try:
        return DocumentKind(raw)
    except ValueError:
        return DocumentKind.UNKNOWN


def _coerce_confidence(raw: Any) -> FieldConfidence:
    if isinstance(raw, FieldConfidence):
        return raw
    if isinstance(raw, (int, float)):
        if raw >= 80:
            return FieldConfidence.HIGH
        if raw >= 50:
            return FieldConfidence.MEDIUM
        return FieldConfidence.LOW
    try:
        return FieldConfidence(str(raw).lower())
    except ValueError:
        return FieldConfidence.HIGH


def from_structured_documents(
    case_id: str,
    documents: List[Dict[str, Any]],
    patient_name: Optional[str] = None,
    cpt_code: Optional[str] = None,
    procedure_name: Optional[str] = None,
    payer_id: Optional[str] = None,
    symptom_summary: Optional[str] = None,
) -> CaseEvidence:
    """Build a CaseEvidence from structured document dicts.

    Each document dict: {id, kind, legible?, classification_confidence?,
    s3_key?, raw_text?, fields:[{name, value, confidence?, note?}]}.
    """
    docs: List[EvidenceDocument] = []
    for d in documents:
        fields = [
            ExtractedField(
                name=f["name"],
                value=f.get("value"),
                source_document_id=d["id"],
                confidence=_coerce_confidence(f.get("confidence", FieldConfidence.HIGH)),
                note=f.get("note"),
            )
            for f in d.get("fields", [])
        ]
        docs.append(
            EvidenceDocument(
                id=d["id"],
                kind=_coerce_kind(d.get("kind", "unknown")),
                s3_key=d.get("s3_key"),
                legible=bool(d.get("legible", True)),
                classification_confidence=_coerce_confidence(
                    d.get("classification_confidence", FieldConfidence.HIGH)
                ),
                fields=fields,
                raw_text=d.get("raw_text"),
            )
        )

    resolved_payer = (
        rules_engine._canonical_payer_id(payer_id) if payer_id else None  # noqa: SLF001
    )

    return CaseEvidence(
        case_id=case_id,
        patient_name=patient_name,
        payer_id=resolved_payer,
        cpt_code=cpt_code,
        procedure_name=procedure_name,
        documents=docs,
        symptom_summary=symptom_summary,
    )


def from_live_intake(
    case_id: str,
    card_s3_bucket: str,
    card_s3_key: str,
    card_back_s3_bucket: str = "",
    card_back_s3_key: str = "",
    voice_s3_bucket: str = "",
    voice_s3_key: str = "",
    voice_media_format: str = "ogg",
    cpt_code: Optional[str] = None,
    procedure_name: Optional[str] = None,
    patient_name: Optional[str] = None,
    extra_documents: Optional[List[Dict[str, Any]]] = None,
) -> CaseEvidence:
    """Build evidence from the live intake tools (Bedrock vision + Transcribe).

    Imported lazily so the structured path and all unit tests stay free of any
    AWS / boto3 dependency.
    """
    from ..tools.documents import extract_insurance_card, transcribe_voice_note

    documents: List[Dict[str, Any]] = []

    card = extract_insurance_card(
        s3_bucket=card_s3_bucket, s3_key=card_s3_key,
        back_s3_bucket=card_back_s3_bucket, back_s3_key=card_back_s3_key,
    )
    card_conf = FieldConfidence.HIGH if card.get("confidence", 0) >= 80 else (
        FieldConfidence.MEDIUM if card.get("confidence", 0) >= 50 else FieldConfidence.LOW
    )
    uncertain = set(card.get("uncertain_fields", []) or [])
    card_fields = []
    for fname in ("payer_name", "member_id", "group_number", "payer_id"):
        if card.get(fname) is not None:
            card_fields.append({
                "name": fname, "value": card.get(fname),
                "confidence": FieldConfidence.LOW if fname in uncertain else card_conf,
            })
    documents.append({
        "id": "doc-card", "kind": DocumentKind.INSURANCE_CARD.value,
        "s3_key": card_s3_key, "legible": bool(card.get("legible", False)),
        "fields": card_fields,
    })

    symptom_summary = None
    if voice_s3_key:
        voice = transcribe_voice_note(
            s3_bucket=voice_s3_bucket or card_s3_bucket, s3_key=voice_s3_key,
            media_format=voice_media_format,
        )
        symptom_summary = voice.get("transcript") or None

    if extra_documents:
        documents.extend(extra_documents)

    card_payer = next((f["value"] for f in card_fields if f["name"] == "payer_id"), None)
    card_payer_name = next((f["value"] for f in card_fields if f["name"] == "payer_name"), None)

    return from_structured_documents(
        case_id=case_id,
        documents=documents,
        patient_name=patient_name,
        cpt_code=cpt_code,
        procedure_name=procedure_name,
        payer_id=card_payer or card_payer_name,
        symptom_summary=symptom_summary,
    )
