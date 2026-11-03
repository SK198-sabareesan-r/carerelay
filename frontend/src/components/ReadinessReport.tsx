import clsx from "clsx";
import type {
  ReadinessReport as ReadinessReportType,
  ReadinessStatus,
  RequirementCheck,
} from "../types/case";

const STATUS_META: Record<
  ReadinessStatus,
  { label: string; style: string; blurb: string }
> = {
  ready_for_human_review: {
    label: "Ready for review",
    style: "bg-gradient-to-b from-brand-50 to-brand-100 text-brand-800",
    blurb: "All critical requirements are satisfied with no blocking conflicts.",
  },
  missing_evidence: {
    label: "Missing evidence",
    style: "bg-gradient-to-b from-amber-50 to-amber-100 text-amber-800",
    blurb: "A required document or field is not yet on file.",
  },
  conflict: {
    label: "Conflict detected",
    style: "bg-gradient-to-b from-orange-50 to-orange-100 text-orange-800",
    blurb: "Documents disagree with each other and need investigation.",
  },
  blocked: {
    label: "Blocked",
    style: "bg-gradient-to-b from-rose-50 to-rose-100 text-rose-700",
    blurb: "A critical issue blocks progression until a human resolves it.",
  },
};

function CheckRow({ check }: { check: RequirementCheck }) {
  return (
    <li className="flex items-start gap-2.5 py-2">
      <span
        className={clsx(
          "mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full text-[11px] font-bold ring-1 ring-inset",
          check.satisfied
            ? "bg-brand-50 text-brand-700 ring-brand-200"
            : "bg-rose-50 text-rose-600 ring-rose-200"
        )}
        aria-hidden="true"
      >
        {check.satisfied ? "\u2713" : "\u2717"}
      </span>
      <div className="flex-1">
        <p className="text-[13px] font-medium text-ink-900">
          {check.description}
          {check.critical && (
            <span className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-rose-500">
              critical
            </span>
          )}
        </p>
        {check.note && <p className="mt-0.5 text-xs text-ink-600">{check.note}</p>}
        {check.satisfied && check.satisfied_by_document_id && (
          <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide text-ink-500">
            Source: {check.satisfied_by_document_id}
          </p>
        )}
      </div>
    </li>
  );
}

/**
 * The human-verifiable case-readiness report. Shows the overall status, a
 * per-requirement satisfied/unsatisfied checklist (each satisfied item naming
 * the source document), and - when present - the deterministic can_progress
 * gate. The status and checks come straight from the readiness engine; this
 * component only renders them.
 */
export function ReadinessReport({ report }: { report: ReadinessReportType }) {
  const meta = STATUS_META[report.status];
  const satisfied = report.requirement_checks.filter((c) => c.satisfied).length;
  const total = report.requirement_checks.length;

  return (
    <div className="surface-3d rounded-2xl p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-serif text-lg font-semibold text-ink-900">Case readiness</h3>
          <p className="mt-0.5 text-xs text-ink-500">{meta.blurb}</p>
        </div>
        <span
          className={clsx(
            "pill-3d inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
            meta.style
          )}
        >
          <span className="h-1.5 w-1.5 rounded-full bg-current" />
          {meta.label}
        </span>
      </div>

      <div className="mt-4 flex items-center gap-4 text-xs text-ink-600">
        <span>
          <span className="font-serif text-base font-semibold tabular-nums text-ink-900">
            {satisfied}
          </span>
          /{total} requirements satisfied
        </span>
        {report.matched_rule_id && <span>Rule: {report.matched_rule_id}</span>}
        {typeof report.can_progress === "boolean" && (
          <span
            className={clsx(
              "rounded-md px-2 py-0.5 text-[11px] font-semibold",
              report.can_progress
                ? "bg-brand-50 text-brand-700"
                : "bg-rose-50 text-rose-600"
            )}
          >
            {report.can_progress ? "Clear to advance" : "Hold \u2013 cannot advance"}
          </span>
        )}
      </div>

      <ul className="mt-3 divide-y divide-ink-100">
        {report.requirement_checks.map((c) => (
          <CheckRow key={c.requirement_id} check={c} />
        ))}
      </ul>

      {report.summary && (
        <p className="mt-4 rounded-xl bg-ink-50 p-3 text-[13px] leading-relaxed text-ink-700">
          {report.summary}
        </p>
      )}
    </div>
  );
}
