import { useParams, Link } from "react-router-dom";
import { useReadiness } from "../hooks/useCases";
import { AgentTimeline } from "../components/AgentTimeline";

/**
 * Activity Log page: the full, timestamped record of what the system did on a
 * case - evidence analysis, policy retrieval, reconciliation, the readiness
 * verdict, routing, and the safety/state gate. Deliberately presented as
 * "Activity" (not internal step/agent names) so the view stays product-facing.
 *
 * (File kept as AgentTrace.tsx only to match the planned route module name;
 * the UI label everywhere is "Activity" / "Log activities".)
 */
export function AgentTrace() {
  const { caseId } = useParams();
  const { data, isLoading, isError, error } = useReadiness(caseId);

  if (isLoading) {
    return <div className="p-6 text-sm text-ink-500">{"Loading activity\u2026"}</div>;
  }
  if (isError || !data) {
    return (
      <div className="p-6">
        <p className="text-sm text-rose-600">
          Could not load activity{error instanceof Error ? `: ${error.message}` : "."}
        </p>
        <Link to="/queue" className="mt-2 inline-block text-sm text-brand-700 underline">
          Back to intake queue
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="font-serif text-2xl font-semibold text-ink-900">Activity log</h1>
          <p className="mt-0.5 text-sm text-ink-500">
            {data.evidence.patient_name ?? data.case_id}
            {" \u00b7 log activities for this case"}
          </p>
        </div>
        <Link
          to={`/cases/${encodeURIComponent(data.case_id)}/readiness`}
          className="text-sm text-brand-700 underline"
        >
          Back to readiness
        </Link>
      </div>

      <div className="surface-3d rounded-2xl p-5">
        <AgentTimeline entries={data.activity_log} />
      </div>
    </div>
  );
}
