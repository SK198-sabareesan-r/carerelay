"""End-to-end workflow tests over the orchestration normal path, plus the
corrected-evidence reprocessing loop and a STUBBED swarm (no network).
"""
import copy

from agent_app.models import DeciderAction
from agent_app.orchestration.case_state import CaseState
from agent_app.orchestration.case_graph import run_case


def test_full_pipeline_detects_all_three_issues(synthetic_conflict_case):
    st = CaseState(case_id="case-synthetic", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    report = st.readiness

    # issue #1: cpt mismatch (critical conflict)
    assert any(d.field_name == "cpt_code" and d.kind.value == "field_mismatch"
               for d in report.discrepancies)
    # issue #2: missing imaging
    assert any("xray_or_mri" in (c.requirement_id) and not c.satisfied
               for c in report.requirement_checks)
    # issue #3: low-confidence member_id
    assert any(d.kind.value == "low_confidence" and d.field_name == "member_id"
               for d in report.discrepancies)


def test_pipeline_produces_source_linked_report(synthetic_conflict_case):
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    # every satisfied requirement names the document that satisfied it
    for chk in st.readiness.requirement_checks:
        if chk.satisfied:
            assert chk.satisfied_by_document_id is not None


def test_audit_trail_is_complete(synthetic_conflict_case):
    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=False)
    events = [e["event"] for e in st.audit.to_list()]
    for expected in ("GRAPH_START", "POLICY_RETRIEVED", "RECONCILED",
                     "READINESS_COMPUTED", "DECIDER_ROUTED", "SAFETY_VERDICT", "GRAPH_DONE"):
        assert expected in events


def test_stubbed_swarm_invoked_on_conflict(synthetic_conflict_case):
    """The conflict path dispatches the swarm when run_swarm=True; we stub the
    runner so the test stays offline but still proves the wiring."""
    calls = {}

    def stub_runner(state):
        calls["ran"] = True
        state.investigation_narrative = "stub investigation summary"
        state.audit.record("SWARM_INVESTIGATION_DONE", "exception_swarm", "stub")
        return state

    st = CaseState(case_id="c", evidence=synthetic_conflict_case)
    run_case(st, run_swarm=True, swarm_runner=stub_runner)
    assert calls.get("ran") is True
    assert st.decision.action == DeciderAction.INVESTIGATE_CONFLICT
    assert st.investigation_narrative == "stub investigation summary"


def test_reprocessing_after_correction_clears_case(synthetic_conflict_case):
    """Upload corrected evidence (fix cpt mismatch + add imaging) and re-run:
    the case should move from CONFLICT to ready + approved."""
    from agent_app.models import DocumentKind, ExtractedField, EvidenceDocument, FieldConfidence

    corrected = copy.deepcopy(synthetic_conflict_case)
    # fix the clinical notes cpt to match the order
    for d in corrected.documents:
        if d.id == "doc-notes":
            for f in d.fields:
                if f.name == "cpt_code":
                    f.value = "29881"
        if d.id == "doc-card":
            for f in d.fields:
                if f.name == "member_id":
                    f.confidence = FieldConfidence.HIGH
                    f.note = None
    # add the missing imaging document
    corrected.documents.append(
        EvidenceDocument(
            id="doc-mri", kind=DocumentKind.IMAGING_REPORT, legible=True,
            fields=[ExtractedField(name="cpt_code", value="29881", source_document_id="doc-mri")],
        )
    )

    st = CaseState(case_id="case-synthetic", evidence=corrected)
    run_case(st, run_swarm=False)
    assert st.readiness.status.value == "ready_for_human_review"
    assert st.safety_verdict.approved is True
    assert st.current_status == "READY_FOR_REVIEW"
