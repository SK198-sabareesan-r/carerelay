import { useParams, Link } from "react-router-dom";
import { useReadiness } from "../hooks/useCases";
import { ReadinessReport } from "../components/ReadinessReport";
import { EvidencePanel } from "../components/EvidencePanel";
import { ConflictPanel } from "../components/ConflictPanel";

/**
 * Case Readiness page: the human-verifiable view a reviewer opens to decide
 * whether a prior-auth case is complete, consistent, and safe to advance.
 * Composes the deterministic readiness report, the source-linked evidence
 * inventory, and the conflicts/gaps panel. All data is produced by the
 * Sentinel evidence pipeline; this page only presents it.
 */
export function CaseReadiness() {
  const { caseId } = useParams();
  const { data, isLoading, isError, error } = useReadiness(caseId);

  if (isLoading) {
    return <div className="p-6 text-sm text-ink-500">{"Loading readiness\u2026"}</div>;
  }
  if (isError || !data) {
    return (
      <div className="p-6">
        <p className="text-sm text-rose-600">
          Could not load readiness{error instanceof Error ? `: ${error.message}` : "."}
        </p>
        <Link to="/queue" className="mt-2 inline-block text-sm text-brand-700 underline">
          Back to intake queue
        </Link>
      </div>
    );
  }

  const { evidence, readiness, activity_log } = data;

  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-ink-900">
            Case readiness
          </h1>
          <p className="mt-0.5 text-sm text-ink-500">
            {evidence.patient_name ?? data.case_id}
            {evidence.procedure_name ? ` \u00b7 ${evidence.procedure_name}` : ""}
            {evidence.cpt_code ? ` (CPT ${evidence.cpt_code})` : ""}
          </p>
        </div>
        <Link
          to={`/cases/${encodeURIComponent(data.case_id)}`}
          className="text-sm text-brand-700 underline"
        >
          Open case detail
        </Link>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <ReadinessReport report={readiness} />
          <ConflictPanel discrepancies={readiness.discrepancies} />
          <EvidencePanel evidence={evidence} />
        </div>
        <div className="surface-3d h-fit rounded-2xl p-5">
          <h3 className="font-serif text-lg font-semibold text-ink-900">Activity</h3>
          <p className="mt-0.5 text-xs text-ink-500">
            Everything the system logged while reviewing this case.
          </p>
          <Link
            to={`/cases/${encodeURIComponent(data.case_id)}/activity`}
            className="mt-2 inline-block text-xs text-brand-700 underline"
          >
            View full activity log ({activity_log.length})
          </Link>
        </div>
      </div>
    </div>
  );
}
