import clsx from "clsx";
import type { CaseEvidence, EvidenceDocument, FieldConfidence } from "../types/case";

const KIND_LABELS: Record<string, string> = {
  insurance_card: "Insurance card",
  procedure_order: "Procedure order",
  clinical_notes: "Clinical notes",
  xray_or_mri: "Imaging report",
  conservative_treatment_history: "Conservative treatment history",
  referral: "Referral",
  lab_result: "Lab result",
  payer_policy: "Payer policy",
  unknown: "Unclassified",
};

const CONF_STYLE: Record<FieldConfidence, string> = {
  high: "bg-brand-50 text-brand-700",
  medium: "bg-amber-50 text-amber-700",
  low: "bg-rose-50 text-rose-600",
};

function DocumentCard({ doc }: { doc: EvidenceDocument }) {
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[13px] font-semibold text-ink-900">
          {KIND_LABELS[doc.kind] ?? doc.kind}
        </span>
        <span className="font-mono text-[10px] text-ink-400">{doc.id}</span>
        {!doc.legible && (
          <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-semibold text-rose-600">
            illegible
          </span>
        )}
      </div>

      {doc.fields.length > 0 ? (
        <table className="mt-2 w-full text-[13px]">
          <tbody>
            {doc.fields.map((f, i) => (
              <tr key={i} className="border-t border-ink-100 first:border-t-0">
                <td className="py-1 pr-3 text-ink-500">{f.name.replace(/_/g, " ")}</td>
                <td className="py-1 pr-3 font-medium text-ink-900">
                  {f.value ?? <span className="text-ink-400">{"\u2014"}</span>}
                </td>
                <td className="py-1 text-right">
                  <span
                    className={clsx(
                      "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                      CONF_STYLE[f.confidence]
                    )}
                    title={f.note ?? undefined}
                  >
                    {f.confidence}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="mt-2 text-xs text-ink-500">No fields extracted.</p>
      )}
    </div>
  );
}

/**
 * Source-linked inventory of every document submitted for a case and the
 * fields extracted from each, with a per-field confidence chip. This is the
 * provenance view: everything the downstream readiness verdict relies on,
 * traceable back to the document it came from.
 */
export function EvidencePanel({ evidence }: { evidence: CaseEvidence }) {
  return (
    <div className="surface-3d rounded-2xl p-5">
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-lg font-semibold text-ink-900">Evidence</h3>
        <span className="text-xs text-ink-500">{evidence.documents.length} documents</span>
      </div>
      {evidence.symptom_summary && (
        <p className="mt-2 rounded-lg bg-ink-50 px-3 py-2 text-[13px] text-ink-700">
          <span className="font-semibold text-ink-900">Reported symptoms: </span>
          {evidence.symptom_summary}
        </p>
      )}
      <div className="mt-3 grid gap-2.5">
        {evidence.documents.map((d) => (
          <DocumentCard key={d.id} doc={d} />
        ))}
      </div>
    </div>
  );
}
