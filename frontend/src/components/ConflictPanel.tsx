import clsx from "clsx";
import type { Discrepancy, Severity } from "../types/case";

const SEVERITY_META: Record<Severity, { label: string; style: string; dot: string }> = {
  critical: { label: "Critical", style: "border-rose-200 bg-rose-50/60", dot: "bg-rose-500" },
  warning: { label: "Warning", style: "border-amber-200 bg-amber-50/60", dot: "bg-amber-500" },
  info: { label: "Info", style: "border-ink-200 bg-ink-50/60", dot: "bg-ink-400" },
};

const KIND_LABELS: Record<string, string> = {
  field_mismatch: "Cross-document conflict",
  missing_document: "Missing document",
  missing_field: "Missing field",
  low_confidence: "Low-confidence read",
  illegible_document: "Illegible document",
  unsupported_requirement: "Unsupported requirement",
  timing: "Timing issue",
};

function DiscrepancyCard({ d }: { d: Discrepancy }) {
  const meta = SEVERITY_META[d.severity];
  return (
    <li className={clsx("rounded-xl border p-3.5", meta.style, d.resolved && "opacity-60")}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={clsx("h-2 w-2 flex-none rounded-full", meta.dot)} aria-hidden="true" />
        <span className="text-[13px] font-semibold text-ink-900">
          {KIND_LABELS[d.kind] ?? d.kind.replace(/_/g, " ")}
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-500">
          {meta.label}
        </span>
        {d.resolved && (
          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-semibold text-brand-700">
            resolved
          </span>
        )}
      </div>

      <p className="mt-1.5 text-[13px] leading-relaxed text-ink-800">{d.summary}</p>

      {d.conflicting_values.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {d.conflicting_values.map((v, i) => (
            <span
              key={i}
              className="rounded-md bg-white px-2 py-0.5 font-mono text-[11px] text-ink-700 ring-1 ring-inset ring-ink-200"
            >
              {v}
            </span>
          ))}
        </div>
      )}

      {d.source_document_ids.length > 0 && (
        <p className="mt-2 text-[11px] font-medium uppercase tracking-wide text-ink-500">
          Sources: {d.source_document_ids.join(", ")}
        </p>
      )}

      {d.explanation && <p className="mt-2 text-xs text-ink-700">{d.explanation}</p>}
      {d.recommended_action && (
        <p className="mt-1.5 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs text-ink-700 ring-1 ring-inset ring-ink-200">
          <span className="font-semibold text-ink-900">Recommended: </span>
          {d.recommended_action}
        </p>
      )}
    </li>
  );
}

/**
 * Lists every detected discrepancy for a case - cross-document conflicts,
 * missing items, and low-confidence reads - with severity, the differing
 * values, and the source documents. Detection is deterministic; this only
 * renders what the reconciliation + readiness engine produced.
 */
export function ConflictPanel({ discrepancies }: { discrepancies: Discrepancy[] }) {
  const open = discrepancies.filter((d) => !d.resolved);
  if (!discrepancies.length) {
    return (
      <div className="surface-3d rounded-2xl p-5">
        <h3 className="font-serif text-lg font-semibold text-ink-900">Conflicts &amp; gaps</h3>
        <p className="mt-2 text-sm text-ink-500">
          No discrepancies detected. Documents are consistent and complete.
        </p>
      </div>
    );
  }
  return (
    <div className="surface-3d rounded-2xl p-5">
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-lg font-semibold text-ink-900">Conflicts &amp; gaps</h3>
        <span className="text-xs text-ink-500">{open.length} open</span>
      </div>
      <ul className="mt-3 space-y-2.5">
        {discrepancies.map((d) => (
          <DiscrepancyCard key={d.id} d={d} />
        ))}
      </ul>
    </div>
  );
}
