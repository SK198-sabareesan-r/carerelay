"""Evidence-processing Workflow: independent analysis tasks run in parallel.

Per the plan, "Workflow" here is a composed task-DAG, not a separate Strands
orchestrator class. The three evidence-analysis tasks are independent given
the normalized CaseEvidence, so we run them concurrently:

  - policy retrieval        (what does the payer require?)
  - reconciliation          (do the documents agree with each other?)
  - (document inventory is already captured in the evidence itself)

and then the deterministic readiness engine fans them in. Every task here is
a deterministic service call, so the parallelism is pure speed-up with no
nondeterminism. The workflow records each task in the audit trail.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import List

from ..models import Discrepancy, PolicyRequirementSet
from ..services import policy_retrieval, reconciliation, readiness_engine
from .case_state import CaseState


def run_evidence_workflow(state: CaseState) -> CaseState:
    """Populate state.requirement_set, state.discrepancies, state.readiness.

    Requires state.evidence to already be set (by the intake/document step).
    Runs policy retrieval and reconciliation in parallel, then the readiness
    engine. Deterministic throughout.
    """
    if state.evidence is None:
        raise ValueError("run_evidence_workflow requires state.evidence to be set first.")

    evidence = state.evidence
    payer_id = evidence.payer_id or "PAYER-UNKNOWN"
    cpt_code = evidence.cpt_code or ""

    state.audit.record(
        "EVIDENCE_WORKFLOW_START", "evidence_workflow",
        f"Parallel evidence analysis for payer={payer_id} cpt={cpt_code}.",
    )

    # --- parallel independent tasks ---
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_policy = pool.submit(policy_retrieval.retrieve_requirements, payer_id, cpt_code)
        fut_recon = pool.submit(reconciliation.reconcile, evidence)
        requirement_set: PolicyRequirementSet = fut_policy.result()
        discrepancies: List[Discrepancy] = fut_recon.result()

    state.requirement_set = requirement_set
    state.discrepancies = discrepancies
    state.audit.record(
        "POLICY_RETRIEVED", "policy_retrieval",
        f"Matched rule {requirement_set.matched_rule_id}; "
        f"{len(requirement_set.requirements)} requirement(s).",
        data={"matched_rule_id": requirement_set.matched_rule_id},
    )
    state.audit.record(
        "RECONCILED", "reconciliation",
        f"{len(discrepancies)} discrepancy(ies) detected.",
        data={"count": len(discrepancies)},
    )

    # --- fan-in: deterministic readiness verdict ---
    report = readiness_engine.build_readiness_report(
        evidence, requirement_set, discrepancies
    )
    state.readiness = report
    state.audit.record(
        "READINESS_COMPUTED", "readiness_engine",
        f"Status={report.status.value}; can_progress={report.can_progress()}.",
        data={"status": report.status.value, "can_progress": report.can_progress()},
    )
    return state
