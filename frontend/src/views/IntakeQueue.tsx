import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { useCases, useStats } from "../hooks/useCases";
import { StatusBadge, OutcomeBadge, ChannelPill } from "../components/Badge";
import { StatTile } from "../components/StatTile";
import { DateRangePicker } from "../components/DateRangePicker";
import { defaultDateRange } from "../lib/dateRange";
import { AddCaseModal } from "../components/AddCaseModal";
import { StartFollowupModal } from "../components/StartFollowupModal";
import type { CaseStatus } from "../types/case";
import type { DateRange } from "../lib/api";

/**
 * The raw backend statuses are collapsed into a handful of meaningful
 * lifecycle stages so the queue stays readable. CRUCIALLY, the stat tiles
 * and the filter chips both use this SAME grouping, so a tile's number
 * always equals the number of cases behind its matching filter (no more
 * "Scheduled: 4" up top but 0 cases when you click Scheduled).
 */
type StageId = "ALL" | "AWAITING_PATIENT" | "PENDING_DOCTOR" | "SCHEDULED" | "DENIED";

const STAGES: { id: StageId; label: string; statuses: CaseStatus[] }[] = [
  { id: "ALL", label: "All", statuses: [] },
  {
    id: "AWAITING_PATIENT",
    label: "Awaiting patient",
    statuses: ["AWAITING_INSURANCE_DOCS", "AWAITING_VOICE_NOTE", "AWAITING_DOCUMENTS", "OPEN"],
  },
  { id: "PENDING_DOCTOR", label: "Pending approval", statuses: ["PENDING_DOCTOR_APPROVAL"] },
  { id: "SCHEDULED", label: "Scheduled", statuses: ["SCHEDULED", "APPROVED"] },
  { id: "DENIED", label: "Denied", statuses: ["DENIED"] },
];

function stageCount(byStatus: Record<string, number> | undefined, statuses: CaseStatus[]): number {
  if (!byStatus) return 0;
  return statuses.reduce((sum, s) => sum + (byStatus[s] ?? 0), 0);
}

export function IntakeQueue() {
  const [range, setRange] = useState<DateRange>(defaultDateRange());
  const { data, isLoading, isError, error } = useCases(range);
  const { data: stats } = useStats(range);
  const navigate = useNavigate();
  const [filter, setFilter] = useState<StageId>("ALL");
  const [search, setSearch] = useState("");
  const [showAddCase, setShowAddCase] = useState(false);
  const [showFollowup, setShowFollowup] = useState(false);

  const filtered = useMemo(() => {
    const cases = data?.cases ?? [];
    const activeStage = STAGES.find((s) => s.id === filter);
    const allowed = activeStage ? activeStage.statuses : [];
    return cases.filter((c) => {
      if (filter !== "ALL" && !allowed.includes(c.status)) return false;
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        c.patient_name.toLowerCase().includes(q) ||
        c.procedure_name.toLowerCase().includes(q) ||
        c.cpt_code.toLowerCase().includes(q) ||
        c.payer_id.toLowerCase().includes(q)
      );
    });
  }, [data, filter, search]);

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink-900">Intake Queue</h1>
          <p className="mt-1.5 text-sm text-ink-600">
            Prior-authorization cases, routed through WhatsApp intake and verified by the
            deterministic rules engine.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddCase(true)}
            className="flex items-center gap-1.5 rounded-xl border border-ink-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink-700 shadow-xs transition hover:border-brand-300 hover:text-brand-700"
          >
            Log a case
          </button>
          <button
            onClick={() => setShowFollowup(true)}
            className="flex items-center gap-1.5 rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-2.5 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 active:translate-y-px"
          >
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" />
            </svg>
            Start follow-up
          </button>
        </div>
      </header>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <DateRangePicker range={range} onChange={setRange} />
        <p className="text-xs text-ink-500">
          Showing activity {range.from || range.to ? "in the selected range" : "for all time"}
          {range.from || range.to ? ` (${range.from ?? "…"} to ${range.to ?? "…"})` : ""}.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total cases" value={stats?.total_cases ?? "-"} />
        <StatTile
          label="Awaiting patient"
          value={stageCount(stats?.by_status, STAGES[1].statuses)}
          accent="amber"
        />
        <StatTile
          label="Pending approval"
          value={stageCount(stats?.by_status, STAGES[2].statuses)}
          accent="default"
        />
        <StatTile
          label="Scheduled"
          value={stageCount(stats?.by_status, STAGES[3].statuses)}
          accent="brand"
        />
      </div>

      <div className="glass-panel mb-5 flex flex-wrap items-center gap-3 rounded-2xl p-2">
        <div className="flex flex-wrap gap-1 rounded-xl bg-white/70 p-1">
          {STAGES.map((stage) => {
            const count =
              stage.id === "ALL" ? stats?.total_cases ?? 0 : stageCount(stats?.by_status, stage.statuses);
            return (
              <button
                key={stage.id}
                onClick={() => setFilter(stage.id)}
                className={clsx(
                  "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                  filter === stage.id
                    ? "bg-gradient-to-b from-brand-600 to-brand-700 text-white shadow-raised"
                    : "text-ink-600 hover:bg-white hover:text-ink-800"
                )}
              >
                {stage.label}
                <span
                  className={clsx(
                    "ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-bold",
                    filter === stage.id ? "bg-white/25 text-white" : "bg-ink-100 text-ink-500"
                  )}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search patient, procedure, CPT, payer..."
          className="min-w-[260px] flex-1 rounded-xl border border-white/60 bg-white/70 px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-400"
        />
      </div>

      {isLoading && <div className="py-16 text-center text-sm text-ink-500">Loading cases...</div>}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {(error as Error)?.message ?? "Failed to load cases."}
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-ink-300 py-16 text-center text-sm text-ink-500">
          No cases match the current filter or date range.
        </div>
      )}

      <div className="space-y-2.5">
        {filtered.map((c) => (
          <button
            key={c.case_id}
            onClick={() => navigate(`/cases/${c.case_id}`)}
            className="surface-3d group flex w-full items-center gap-4 rounded-2xl px-4 py-3.5 text-left"
          >
            <div className="flex-1">
              <div className="flex items-center gap-2.5">
                <span className="font-semibold text-ink-900">{c.patient_name}</span>
                <ChannelPill channel={c.channel} />
                <span className="text-xs text-ink-500">{c.patient_phone_masked}</span>
              </div>
              <div className="mt-1 text-sm text-ink-600">
                {c.procedure_name} <span className="text-ink-400">&middot;</span>{" "}
                <span className="font-mono text-xs">{c.cpt_code}</span>{" "}
                <span className="text-ink-400">&middot;</span> {c.payer_id}
              </div>
            </div>
            <OutcomeBadge outcome={c.verification.outcome} />
            <StatusBadge status={c.status} />
            <time className="w-20 flex-none text-right text-xs text-ink-500">{relativeTime(c.created_at)}</time>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="h-4 w-4 flex-none text-ink-400 transition group-hover:text-brand-600"
            >
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        ))}
      </div>

      {showAddCase && <AddCaseModal onClose={() => setShowAddCase(false)} />}
      {showFollowup && <StartFollowupModal onClose={() => setShowFollowup(false)} />}
    </div>
  );
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
