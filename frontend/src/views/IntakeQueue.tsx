import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import clsx from "clsx";
import { useCases, useStats } from "../hooks/useCases";
import { StatusBadge, OutcomeBadge, ChannelPill } from "../components/Badge";
import { StatTile } from "../components/StatTile";
import type { CaseStatus } from "../types/case";

const STATUS_FILTERS: (CaseStatus | "ALL")[] = ["ALL", "OPEN", "AWAITING_DOCUMENTS", "APPROVED", "DENIED"];

export function IntakeQueue() {
  const { data, isLoading, isError, error } = useCases();
  const { data: stats } = useStats();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<CaseStatus | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const cases = data?.cases ?? [];
    return cases.filter((c) => {
      if (filter !== "ALL" && c.status !== filter) return false;
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
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink-900">Intake Queue</h1>
          <p className="mt-1.5 text-sm text-ink-500">
            Live prior-authorization cases, routed through WhatsApp intake and verified by the
            deterministic rules engine.
          </p>
        </div>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total cases" value={stats?.total_cases ?? "-"} />
        <StatTile
          label="Awaiting documents"
          value={stats?.by_status?.AWAITING_DOCUMENTS ?? 0}
          accent="amber"
        />
        <StatTile label="Approved" value={stats?.by_status?.APPROVED ?? 0} accent="brand" />
        <StatTile
          label="Avg. card extraction confidence"
          value={stats?.avg_card_extraction_confidence != null ? `${stats.avg_card_extraction_confidence}%` : "-"}
          accent="default"
        />
      </div>

      <div className="glass-panel mb-5 flex flex-wrap items-center gap-3 rounded-2xl p-2">
        <div className="flex gap-1 rounded-xl bg-white/70 p-1">
          {STATUS_FILTERS.map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={clsx(
                "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                filter === s
                  ? "bg-gradient-to-b from-brand-600 to-brand-700 text-white shadow-raised"
                  : "text-ink-500 hover:bg-white hover:text-ink-800"
              )}
            >
              {s === "ALL" ? "All" : s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search patient, procedure, CPT, payer..."
          className="min-w-[260px] flex-1 rounded-xl border border-white/60 bg-white/70 px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-400"
        />
      </div>

      {isLoading && <div className="py-16 text-center text-sm text-ink-400">Loading cases...</div>}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {(error as Error)?.message ?? "Failed to load cases."}
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-ink-300 py-16 text-center text-sm text-ink-400">
          No cases match the current filter.
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
                <span className="text-xs text-ink-400">{c.patient_phone_masked}</span>
              </div>
              <div className="mt-1 text-sm text-ink-500">
                {c.procedure_name} <span className="text-ink-300">&middot;</span>{" "}
                <span className="font-mono text-xs">{c.cpt_code}</span>{" "}
                <span className="text-ink-300">&middot;</span> {c.payer_id}
              </div>
            </div>
            <OutcomeBadge outcome={c.verification.outcome} />
            <StatusBadge status={c.status} />
            <time className="w-20 flex-none text-right text-xs text-ink-400">{relativeTime(c.created_at)}</time>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              className="h-4 w-4 flex-none text-ink-300 transition group-hover:text-brand-600"
            >
              <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        ))}
      </div>
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
