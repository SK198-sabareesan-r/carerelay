import type { DateRange } from "../lib/api";
import { toDateInput } from "../lib/dateRange";

/**
 * Simple from/to date range control. Defaults (past 7 days incl. today) are
 * computed by the caller (see IntakeQueue.tsx defaultDateRange()) - this
 * component is just the two native date inputs + a couple of quick presets.
 */
export function DateRangePicker({
  range,
  onChange,
}: {
  range: DateRange;
  onChange: (range: DateRange) => void;
}) {
  function setPreset(days: number) {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - (days - 1));
    onChange({ from: toDateInput(from), to: toDateInput(to) });
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1.5 rounded-xl border border-white/60 bg-white/70 px-2.5 py-1.5">
        <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4 flex-none text-ink-400">
          <rect x="3" y="5" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
          <path d="M3 9h18M8 3v4M16 3v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input
          type="date"
          value={range.from ?? ""}
          onChange={(e) => onChange({ ...range, from: e.target.value || undefined })}
          className="bg-transparent text-xs text-ink-700 outline-none"
          aria-label="From date"
        />
        <span className="text-xs text-ink-300">&rarr;</span>
        <input
          type="date"
          value={range.to ?? ""}
          onChange={(e) => onChange({ ...range, to: e.target.value || undefined })}
          className="bg-transparent text-xs text-ink-700 outline-none"
          aria-label="To date"
        />
      </div>
      <div className="flex gap-1">
        <button
          onClick={() => setPreset(7)}
          className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-ink-500 hover:bg-white hover:text-ink-800"
        >
          7d
        </button>
        <button
          onClick={() => setPreset(30)}
          className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-ink-500 hover:bg-white hover:text-ink-800"
        >
          30d
        </button>
        <button
          onClick={() => onChange({})}
          className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-ink-500 hover:bg-white hover:text-ink-800"
        >
          All time
        </button>
      </div>
    </div>
  );
}


