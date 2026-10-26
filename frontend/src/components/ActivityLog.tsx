import type { ActivityLogEntry } from "../types/case";

const EVENT_ICONS: Record<string, string> = {
  CREATED: "\u2728", // sparkle
  FOLLOWUP_INITIATED: "\u{1F4C5}", // calendar
  AGENT_PROCESSED: "\u2699\uFE0F", // gear - case processed
  PAYER_CHECK: "\u2696\uFE0F", // scale
  STATUS_CHANGED: "\u{1F504}", // refresh
  APPOINTMENT_RELEASED: "\u2705", // check
  NOTIFIED: "\u{1F4AC}", // speech bubble
  STAFF_MESSAGE_SENT: "\u{1F4AC}", // speech bubble
  DOCTOR_APPROVED: "\u{1F469}\u200D\u2695\uFE0F", // health worker
};

// Human-facing relabeling of raw event codes that carry internal naming.
const EVENT_LABELS: Record<string, string> = {
  AGENT_PROCESSED: "Case processed",
  FOLLOWUP_INITIATED: "Follow-up started",
  STAFF_MESSAGE_SENT: "Message sent to patient",
  APPOINTMENT_RELEASED: "Appointment confirmed",
  DOCTOR_APPROVED: "Approved by doctor",
  DOCTOR_REQUESTED_NOTES: "Doctor requested more detail",
};

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function actorLabel(actor: string): string {
  if (actor.startsWith("staff:")) return `Staff - ${actor.slice(6)}`;
  if (actor === "agent") return "Automated processing";
  if (actor === "doctor") return "Doctor";
  if (actor === "patient") return "Patient";
  if (actor === "system") return "System";
  return actor;
}

/**
 * Full timestamped history for a case - every creation and status change
 * traces to a logged entry (see activity_log on PriorAuthTable items,
 * dashboard_api.handler._append_activity). Rendered as a vertical timeline
 * so staff can see exactly what happened and when, not just the current
 * state.
 */
export function ActivityLog({ entries }: { entries: ActivityLogEntry[] }) {
  if (!entries || entries.length === 0) {
    return <p className="text-sm text-ink-500">No activity recorded for this case yet.</p>;
  }

  return (
    <ol className="relative space-y-0">
      {entries.map((entry, i) => (
        <li key={i} className="relative flex gap-3 pb-5 last:pb-0">
          {i < entries.length - 1 && (
            <span className="absolute left-[15px] top-8 h-[calc(100%-1.75rem)] w-px bg-ink-200" aria-hidden="true" />
          )}
          <span className="relative z-10 flex h-8 w-8 flex-none items-center justify-center rounded-full bg-brand-50 text-sm ring-1 ring-inset ring-brand-200">
            {EVENT_ICONS[entry.event] ?? "\u2022"}
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
              {actorLabel(entry.actor)}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
