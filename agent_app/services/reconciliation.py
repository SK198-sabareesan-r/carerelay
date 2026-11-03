"""Deterministic cross-document reconciliation.

Compares the same logical field extracted from multiple documents and flags
disagreements, plus low-confidence reads and illegible documents. This is
pure Python over the CaseEvidence model - no LLM. It is what deterministically
detects a procedure-code mismatch between, say, the procedure order and the
clinical notes.
"""
from __future__ import annotations

from typing import List

from ..models import (
    CaseEvidence,
    Discrepancy,
    DiscrepancyKind,
    FieldConfidence,
    Severity,
)

# Fields where a cross-document disagreement is clinically/financially
# significant enough to be CRITICAL. Others are surfaced as WARNING.
_CRITICAL_FIELDS = {"cpt_code", "patient_name", "member_id", "procedure_name"}


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def reconcile(evidence: CaseEvidence) -> List[Discrepancy]:
    """Return every detected discrepancy in the case evidence.

    Detects:
      - FIELD_MISMATCH: same field name, differing non-null values across docs
      - LOW_CONFIDENCE: a field extracted with low confidence
      - ILLEGIBLE_DOCUMENT: a submitted document that could not be read
    """
    discrepancies: List[Discrepancy] = []

    # 1. Cross-document field mismatches.
    field_names = {f.name for d in evidence.documents for f in d.fields}
    for name in sorted(field_names):
        occurrences = [f for f in evidence.all_fields(name) if f.value is not None]
        distinct = {}
        for f in occurrences:
            distinct.setdefault(_norm(f.value), f)
        if len(distinct) > 1:
            severity = Severity.CRITICAL if name in _CRITICAL_FIELDS else Severity.WARNING
            values = [f.value for f in distinct.values()]
            doc_ids = [f.source_document_id for f in distinct.values()]
            discrepancies.append(
                Discrepancy(
                    id=f"disc-mismatch-{name}",
                    kind=DiscrepancyKind.FIELD_MISMATCH,
                    severity=severity,
                    field_name=name,
                    summary=(
                        f"'{name}' disagrees across documents: "
                        + " vs ".join(f"{f.value} ({f.source_document_id})" for f in distinct.values())
                    ),
                    source_document_ids=doc_ids,
                    conflicting_values=values,
                )
            )

    # 2. Low-confidence fields.
    for f in evidence.low_confidence_fields():
        discrepancies.append(
            Discrepancy(
                id=f"disc-lowconf-{f.source_document_id}-{f.name}",
                kind=DiscrepancyKind.LOW_CONFIDENCE,
                severity=Severity.WARNING,
                field_name=f.name,
                summary=(
                    f"'{f.name}' was extracted with low confidence from "
                    f"{f.source_document_id}"
                    + (f" ({f.note})" if f.note else "")
                    + "."
                ),
                source_document_ids=[f.source_document_id],
                conflicting_values=[f.value] if f.value else [],
            )
        )

    # 3. Illegible documents.
    for d in evidence.documents:
        if not d.legible:
            discrepancies.append(
                Discrepancy(
                    id=f"disc-illegible-{d.id}",
                    kind=DiscrepancyKind.ILLEGIBLE_DOCUMENT,
                    severity=Severity.WARNING,
                    summary=f"Document {d.id} ({d.kind.value}) could not be read reliably.",
                    source_document_ids=[d.id],
                )
            )

    return discrepancies
