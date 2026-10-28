import { useState } from "react";
import type { CaseStatus } from "../types/case";

const STATUSES: CaseStatus[] = [
  "OPEN",
  "AWAITING_DOCUMENTS",
  "AWAITING_PAYER",
  "PENDING_DOCTOR_APPROVAL",
  "APPROVED",
  "SCHEDULED",
  "DENIED",
];

/**
 * Lets staff change a case's status directly from the console. Every
 * change is appended to the case's activity_log with a timestamp (see
 * dashboard_api.handler._handle_update_status) - this control never edits
 * history, it only adds to it.
 */
export function StatusUpdateControl({
  currentStatus,
  onChange,
  isSaving,
}: {
  currentStatus: CaseStatus;
  onChange: (status: CaseStatus, note: string) => Promise<void>;
  isSaving: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<CaseStatus | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function confirm() {
    if (!pending) return;
    setError(null);
    try {
      await onChange(pending, note.trim());
      setOpen(false);
      setPending(null);
      setNote("");
    } catch {
      setError("Could not update status. Please try again.");
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-lg border border-ink-200 bg-white px-3 py-1.5 text-xs font-semibold text-ink-700 shadow-xs transition hover:border-brand-300 hover:text-brand-700"
      >
        <svg viewBox="0 0 24 24" fill="none" className="h-3.5 w-3.5">
          <path
            d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        Update status
      </button>
    );
  }

  return (
    <div className="w-72 rounded-xl border border-ink-200 bg-white p-3 shadow-popover">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">Change status to</p>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {STATUSES.map((s) => (
          <button
            key={s}
            onClick={() => setPending(s)}
            disabled={s === currentStatus}
            className={
              "rounded-lg px-2 py-1.5 text-[11px] font-semibold transition " +
              (pending === s
                ? "bg-brand-700 text-white"
                : s === currentStatus
                ? "cursor-not-allowed bg-ink-50 text-ink-400"
                : "bg-ink-100 text-ink-700 hover:bg-ink-200")
            }
          >
            {s.replace(/_/g, " ")}
          </button>
        ))}
      </div>

      {pending && (
        <div className="mt-2.5">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note (e.g. reason)"
            className="w-full rounded-lg border border-ink-200 px-2.5 py-1.5 text-xs text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
          />
        </div>
      )}

      {error && <p className="mt-2 text-[11px] text-rose-600">{error}</p>}

      <div className="mt-3 flex justify-end gap-1.5">
        <button
          onClick={() => {
            setOpen(false);
            setPending(null);
            setNote("");
            setError(null);
          }}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-ink-600 hover:text-ink-800"
        >
          Cancel
        </button>
        <button
          onClick={confirm}
          disabled={!pending || isSaving}
          className="rounded-lg bg-brand-700 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-ink-300"
        >
          {isSaving ? "Saving..." : "Confirm"}
        </button>
      </div>
    </div>
  );
}
