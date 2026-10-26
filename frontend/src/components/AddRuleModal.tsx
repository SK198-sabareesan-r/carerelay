import { useState } from "react";
import { useCreatePayerRule } from "../hooks/useCases";
import { ApiError } from "../lib/api";

export function AddRuleModal({ onClose }: { onClose: () => void }) {
  const createRule = useCreatePayerRule();

  const [payerId, setPayerId] = useState("");
  const [cptCode, setCptCode] = useState("");
  const [procedureName, setProcedureName] = useState("");
  const [requiresAuth, setRequiresAuth] = useState(true);
  const [docsText, setDocsText] = useState("");
  const [ruleId, setRuleId] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const requiredDocuments = docsText
    .split(",")
    .map((d) => d.trim().toLowerCase().replace(/\s+/g, "_"))
    .filter(Boolean);

  function suggestRuleId(payer: string, cpt: string): string {
    const prefix = payer.replace(/^PAYER-/, "").slice(0, 8);
    return cpt ? `${prefix}-${cpt}-v1` : "";
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createRule.mutateAsync({
        payer_id: payerId.trim().toUpperCase(),
        cpt_code: cptCode.trim(),
        procedure_name: procedureName.trim(),
        requires_prior_auth: requiresAuth,
        required_documents: requiresAuth ? requiredDocuments : [],
        rule_id: ruleId.trim() || suggestRuleId(payerId.trim(), cptCode.trim()),
        notes: notes.trim(),
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the rule. Please try again.");
    }
  }

  const canSubmit = !!payerId.trim() && !!cptCode.trim() && !!procedureName.trim();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 px-4 backdrop-blur-md">
      <div className="glass-panel-strong w-full max-w-lg rounded-3xl p-6 shadow-popover animate-fade-in">
        <h2 className="font-serif text-lg font-semibold text-ink-900">Add a payer rule</h2>
        <p className="mt-1 text-sm text-ink-500">
          Adds a new deterministic coverage rule. This row - not a model - will decide every
          future case for this payer + CPT code.
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Payer ID
              </label>
              <input
                autoFocus
                value={payerId}
                onChange={(e) => setPayerId(e.target.value)}
                placeholder="PAYER-ACME"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                CPT code
              </label>
              <input
                value={cptCode}
                onChange={(e) => setCptCode(e.target.value)}
                placeholder="29881"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Procedure name
            </label>
            <input
              value={procedureName}
              onChange={(e) => setProcedureName(e.target.value)}
              placeholder="Knee arthroscopy, meniscectomy"
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Requires prior authorization?
            </label>
            <div className="mt-1.5 flex gap-1 rounded-lg bg-ink-100 p-1">
              {[
                { v: true, label: "Yes, requires auth" },
                { v: false, label: "No, auto-approved" },
              ].map((opt) => (
                <button
                  key={String(opt.v)}
                  type="button"
                  onClick={() => setRequiresAuth(opt.v)}
                  className={
                    "flex-1 rounded-md px-3 py-1.5 text-xs font-semibold transition " +
                    (requiresAuth === opt.v ? "bg-white text-brand-700 shadow-card" : "text-ink-500 hover:text-ink-800")
                  }
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {requiresAuth && (
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Required documents (comma-separated)
              </label>
              <input
                value={docsText}
                onChange={(e) => setDocsText(e.target.value)}
                placeholder="clinical notes, xray or mri"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Rule ID <span className="text-ink-400">(auto-suggested if left blank)</span>
            </label>
            <input
              value={ruleId}
              onChange={(e) => setRuleId(e.target.value)}
              placeholder={suggestRuleId(payerId, cptCode) || "ACME-29881-v1"}
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 font-mono text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Notes / policy citation
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Requires imaging within 90 days per policy section 4.2"
              rows={2}
              className="mt-1.5 w-full resize-none rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            />
          </div>

          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-ink-500 hover:text-ink-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit || createRule.isPending}
              className="rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 disabled:cursor-not-allowed disabled:from-ink-300 disabled:to-ink-300 disabled:shadow-none disabled:opacity-70"
            >
              {createRule.isPending ? "Adding rule..." : "Add rule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
