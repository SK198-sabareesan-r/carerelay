import type { ActivityLogEntry } from "../types/case";

/**
 * Vertical timeline of everything the system did on a case - evidence
 * analysis, policy retrieval, reconciliation, the readiness verdict, routing,
 * and the safety/state gate. This renders the case audit trail (see
 * agent_app/services/audit_service.AuditTrail) as activity entries. It is
 * presented as "Activity" / "Log activities", not internal step names, so the
 * view stays product-facing.
 */

const EVENT_LABELS: Record<string, string> = {
  GRAPH_START: "Case entered review",
  EVIDENCE_WORKFLOW_START: "Evidence analysis started",
  POLICY_RETRIEVED: "Payer requirements retrieved",
  RECONCILED: "Documents reconciled",
  READINESS_COMPUTED: "Readiness computed",
  DECIDER_ROUTED: "Next action selected",
  SWARM_INVESTIGATION_START: "Exception investigation started",
  SWARM_INVESTIGATION_DONE: "Exception investigation complete",
  SWARM_SKIPPED: "Routed to human review",
  SAFETY_VERDICT: "Safety review",
  STATE_GATE: "Status gate evaluated",
  GRAPH_DONE: "Review complete",
};

const ACTOR_LABELS: Record<string, string> = {
  case_graph: "Workflow",
  evidence_workflow: "Evidence analysis",
  policy_retrieval: "Policy lookup",
  reconciliation: "Reconciliation",
  readiness_engine: "Readiness engine",
  decider: "Router",
  exception_swarm: "Investigation",
  safety_critic: "Safety review",
  state_engine: "Status gate",
};

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function AgentTimeline({ entries }: { entries: ActivityLogEntry[] }) {
  if (!entries || entries.length === 0) {
    return <p className="text-sm text-ink-500">No activity logged for this case yet.</p>;
  }

  return (
    <ol className="relative space-y-0">
      {entries.map((entry, i) => (
        <li key={i} className="relative flex gap-3 pb-5 last:pb-0">
          {i < entries.length - 1 && (
            <span
              className="absolute left-[15px] top-8 h-[calc(100%-1.75rem)] w-px bg-ink-200"
              aria-hidden="true"
            />
          )}
          <span className="relative z-10 flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700 ring-1 ring-inset ring-brand-200">
            {i + 1}
          </span>
          <div className="flex-1 pt-0.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <span className="text-[13px] font-semibold text-ink-900">
                {EVENT_LABELS[entry.event] ?? entry.event.replace(/_/g, " ")}
              </span>
              <time className="text-xs text-ink-500">{formatTimestamp(entry.timestamp)}</time>
            </div>
            <p className="mt-0.5 text-[13px] leading-relaxed text-ink-700">{entry.detail}</p>
            <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-500">
              {ACTOR_LABELS[entry.actor] ?? entry.actor}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
