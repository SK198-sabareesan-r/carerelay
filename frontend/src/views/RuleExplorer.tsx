import { useMemo, useState } from "react";
import clsx from "clsx";
import { usePayerRules } from "../hooks/useCases";
import type { PayerRule } from "../types/case";

/**
 * Browses the deterministic PayerRulesTable directly - the literal "code
 * decides" data behind every prior-auth outcome. This view exists so a
 * reviewer can see the rule logic as plain structured data, independent of
 * any AI narration, and verify every case outcome traces back to a real row.
 */
export function RuleExplorer() {
  const { data, isLoading, isError } = usePayerRules();
  const [payerFilter, setPayerFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");

  const payers = useMemo(
    () => Array.from(new Set((data?.rules ?? []).map((r) => r.payer_id))).sort(),
    [data]
  );

  const filtered = useMemo(() => {
    const rules = data?.rules ?? [];
    return rules.filter((r) => {
      if (payerFilter !== "ALL" && r.payer_id !== payerFilter) return false;
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        r.cpt_code.toLowerCase().includes(q) ||
        r.procedure_name.toLowerCase().includes(q) ||
        r.rule_id.toLowerCase().includes(q)
      );
    });
  }, [data, payerFilter, search]);

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink-900">Rule Explorer</h1>
        <p className="mt-1 text-sm text-ink-500">
          The deterministic payer/CPT rule table that decides every prior-authorization outcome.
          No model ever touches this data - see{" "}
          <code className="rounded bg-ink-100 px-1 py-0.5 text-xs text-ink-700">agent_app/rules_engine.py</code>.
        </p>
      </header>

      <div className="glass-panel mb-5 flex flex-wrap items-center gap-3 rounded-2xl p-2">
        <div className="flex gap-1 rounded-xl bg-white/70 p-1">
          <button
            onClick={() => setPayerFilter("ALL")}
            className={clsx(
              "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
              payerFilter === "ALL"
                ? "bg-gradient-to-b from-brand-600 to-brand-700 text-white shadow-raised"
                : "text-ink-500 hover:bg-white hover:text-ink-800"
            )}
          >
            All payers
          </button>
          {payers.map((p) => (
            <button
              key={p}
              onClick={() => setPayerFilter(p)}
              className={clsx(
                "rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                payerFilter === p
                  ? "bg-gradient-to-b from-brand-600 to-brand-700 text-white shadow-raised"
                  : "text-ink-500 hover:bg-white hover:text-ink-800"
              )}
            >
              {p.replace("PAYER-", "")}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search CPT code, procedure, rule ID..."
          className="min-w-[260px] flex-1 rounded-xl border border-white/60 bg-white/70 px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-400 focus:bg-white focus:ring-1 focus:ring-brand-400"
        />
      </div>

      {isLoading && <div className="py-16 text-center text-sm text-ink-400">Loading rules...</div>}
      {isError && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          Failed to load payer rules.
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {filtered.map((r) => (
          <RuleCard key={r.rule_id} rule={r} />
        ))}
      </div>
    </div>
  );
}

function RuleCard({ rule }: { rule: PayerRule }) {
  return (
    <div className="surface-3d rounded-2xl p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs text-brand-700">{rule.rule_id}</div>
          <div className="mt-1 text-sm font-semibold text-ink-900">{rule.procedure_name}</div>
          <div className="mt-0.5 text-xs text-ink-500">
            {rule.payer_id} <span className="text-ink-300">&middot;</span> CPT{" "}
            <span className="font-mono">{rule.cpt_code}</span>
          </div>
        </div>
        <span
          className={clsx(
            "flex-none rounded-full px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide ring-1 ring-inset",
            rule.requires_prior_auth
              ? "bg-amber-50 text-amber-800 ring-amber-200"
              : "bg-brand-50 text-brand-700 ring-brand-200"
          )}
        >
          {rule.requires_prior_auth ? "Auth required" : "No auth"}
        </span>
      </div>

      {rule.required_documents.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {rule.required_documents.map((d) => (
            <span
              key={d}
              className="rounded-md bg-ink-100 px-2 py-0.5 text-[11px] font-medium text-ink-600 ring-1 ring-inset ring-ink-200"
            >
              {d.replace(/_/g, " ")}
            </span>
          ))}
        </div>
      )}

      <p className="mt-3 border-t border-ink-100 pt-3 text-[13px] leading-relaxed text-ink-500">{rule.notes}</p>
    </div>
  );
}
