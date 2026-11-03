"""Deterministic readiness engine: the authoritative verdict.

Given the case evidence, the retrieved policy requirements, and the detected
discrepancies, it computes:
  - a per-requirement satisfied/unsatisfied check (with the document that
    satisfied it, for provenance), and
  - an overall ReadinessStatus.

This is the single source of truth for "can this case progress?". No model
can override it - agents only attach narrative to the report it returns.
"""
from __future__ import annotations

from typing import List

from ..models import (
    CaseEvidence,
    Discrepancy,
    DiscrepancyKind,
    PolicyRequirement,
    PolicyRequirementSet,
    ReadinessReport,
    ReadinessStatus,
    RequirementCheck,
    RequirementKind,
    Severity,
)
from ..models.case_evidence import DocumentKind


def _check_requirement(
    req: PolicyRequirement, evidence: CaseEvidence
) -> RequirementCheck:
    """Deterministically evaluate one requirement against the evidence."""
    if req.kind == RequirementKind.DOCUMENT_PRESENT:
        for d in evidence.documents:
            if d.kind.value == req.document_kind and d.legible:
                return RequirementCheck(
                    requirement_id=req.id, description=req.description,
                    satisfied=True, satisfied_by_document_id=d.id,
                    critical=req.critical,
                    note=f"Satisfied by {d.id} ({d.kind.value}).",
                )
        # present but illegible?
        for d in evidence.documents:
            if d.kind.value == req.document_kind and not d.legible:
                return RequirementCheck(
                    requirement_id=req.id, description=req.description, satisfied=False,
                    critical=req.critical,
                    note=f"A {req.document_kind} was submitted ({d.id}) but is illegible.",
                )
        return RequirementCheck(
            requirement_id=req.id, description=req.description, satisfied=False,
            critical=req.critical, note=f"No {req.document_kind} document on file.",
        )

    if req.kind == RequirementKind.FIELD_PRESENT:
        occ = [f for f in evidence.all_fields(req.field_name or "") if f.value]
        if occ:
            return RequirementCheck(
                requirement_id=req.id, description=req.description, satisfied=True,
                satisfied_by_document_id=occ[0].source_document_id, critical=req.critical,
                note=f"Field '{req.field_name}' present.",
            )
        return RequirementCheck(
            requirement_id=req.id, description=req.description, satisfied=False,
            critical=req.critical, note=f"Field '{req.field_name}' is missing.",
        )

    if req.kind == RequirementKind.FIELD_MATCHES:
        occ = [f for f in evidence.all_fields(req.field_name or "") if f.value]
        if not occ:
            return RequirementCheck(
                requirement_id=req.id, description=req.description, satisfied=False,
                critical=req.critical, note=f"Field '{req.field_name}' not found on any document.",
            )
        expected = (req.expected_value or "").strip().lower()
        mismatches = [f for f in occ if f.value.strip().lower() != expected]
        if mismatches:
            where = ", ".join(f"{f.value} ({f.source_document_id})" for f in mismatches)
            return RequirementCheck(
                requirement_id=req.id, description=req.description, satisfied=False,
                critical=req.critical,
                note=f"Expected '{req.expected_value}' but found {where}.",
            )
        return RequirementCheck(
            requirement_id=req.id, description=req.description, satisfied=True,
            satisfied_by_document_id=occ[0].source_document_id, critical=req.critical,
            note=f"All documents agree '{req.field_name}' = '{req.expected_value}'.",
        )

    # TIMING_WINDOW and any future kinds: not deterministically checkable here
    # without dated metadata, so we mark unsatisfied-pending and let it surface
    # as a requirement the reviewer confirms. (Conservative / fail-safe.)
    return RequirementCheck(
        requirement_id=req.id, description=req.description, satisfied=False,
        critical=req.critical, note="Timing requirement requires human confirmation.",
    )


def build_readiness_report(
    evidence: CaseEvidence,
    requirement_set: PolicyRequirementSet,
    discrepancies: List[Discrepancy],
) -> ReadinessReport:
    """Compute the per-requirement checks and the overall status."""
    checks = [_check_requirement(r, evidence) for r in requirement_set.requirements]

    # Turn unsatisfied critical requirements into discrepancies too, so the
    # report's discrepancy list is the complete picture a reviewer needs.
    merged = list(discrepancies)
    for chk, req in zip(checks, requirement_set.requirements):
        if not chk.satisfied and req.critical:
            if req.kind == RequirementKind.DOCUMENT_PRESENT:
                kind = DiscrepancyKind.MISSING_DOCUMENT
            elif req.kind == RequirementKind.FIELD_MATCHES:
                kind = DiscrepancyKind.FIELD_MISMATCH
            elif req.kind == RequirementKind.FIELD_PRESENT:
                kind = DiscrepancyKind.MISSING_FIELD
            else:
                kind = DiscrepancyKind.UNSUPPORTED_REQUIREMENT
            # Avoid duplicating a mismatch the reconciliation step already flagged.
            if not any(d.related_requirement_id == req.id for d in merged):
                merged.append(
                    Discrepancy(
                        id=f"disc-req-{req.id}",
                        kind=kind,
                        severity=Severity.CRITICAL,
                        field_name=req.field_name,
                        summary=f"Requirement not satisfied: {chk.note}",
                        related_requirement_id=req.id,
                        source_document_ids=(
                            [chk.satisfied_by_document_id] if chk.satisfied_by_document_id else []
                        ),
                    )
                )

    status = _overall_status(checks, merged)

    return ReadinessReport(
        case_id=evidence.case_id,
        payer_id=requirement_set.payer_id,
        cpt_code=requirement_set.cpt_code,
        matched_rule_id=requirement_set.matched_rule_id,
        status=status,
        requirement_checks=checks,
        discrepancies=merged,
    )


def _overall_status(
    checks: List[RequirementCheck], discrepancies: List[Discrepancy]
) -> ReadinessStatus:
    """Deterministic status precedence.

    Classification of the critical issues present drives the status, and the
    distinction matters because each routes to a different next action:
      - CONFLICT: a critical cross-document FIELD_MISMATCH / unsupported
        requirement - genuinely contradictory evidence that needs
        investigation (-> Swarm). This takes top precedence.
      - MISSING_EVIDENCE: a required document/field is simply absent -
        recoverable by asking for it (-> REQUEST_MISSING_EVIDENCE). A missing
        item is NOT "blocked"; it is pending.
      - BLOCKED: a critical issue that is neither a plain mismatch nor a
        plain missing item (e.g. an illegible required doc, a timing failure)
        that a human must resolve.
      - READY_FOR_HUMAN_REVIEW: no critical issues outstanding.

    All three non-ready states leave can_progress() false; the status only
    selects the appropriate next action, never a silent advance.
    """
    _CONFLICT_KINDS = {
        DiscrepancyKind.FIELD_MISMATCH,
        DiscrepancyKind.UNSUPPORTED_REQUIREMENT,
    }
    _MISSING_KINDS = {
        DiscrepancyKind.MISSING_DOCUMENT,
        DiscrepancyKind.MISSING_FIELD,
    }

    criticals = [d for d in discrepancies if d.severity == Severity.CRITICAL and not d.resolved]
    has_conflict = any(d.kind in _CONFLICT_KINDS for d in criticals)
    has_missing = any(d.kind in _MISSING_KINDS for d in criticals)
    other_blocking = any(
        d.kind not in _CONFLICT_KINDS and d.kind not in _MISSING_KINDS for d in criticals
    )

    if has_conflict:
        return ReadinessStatus.CONFLICT
    if has_missing:
        return ReadinessStatus.MISSING_EVIDENCE
    if other_blocking:
        return ReadinessStatus.BLOCKED

    unsatisfied_critical = [c for c in checks if (not c.satisfied) and c.critical]
    if unsatisfied_critical:
        return ReadinessStatus.MISSING_EVIDENCE

    return ReadinessStatus.READY_FOR_HUMAN_REVIEW
