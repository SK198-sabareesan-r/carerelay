import { useState } from "react";
import { useCreateCase } from "../hooks/useCases";
import { usePayerRules } from "../hooks/useCases";
import { ApiError } from "../lib/api";
import { getSession } from "../lib/auth";

/**
 * Lets front-desk/billing staff manually log a case that didn't come in
 * through WhatsApp (e.g. a phone call or walk-in). Runs through the SAME
 * deterministic rules_engine.evaluate() the Strands agent pipeline uses
 * (see dashboard_api.handler._evaluate_rules / lib/mockRules.ts) - never a
 * placeholder outcome.
 */
export function AddCaseModal({ onClose }: { onClose: () => void }) {
  const { data: rulesData } = usePayerRules();
  const createCase = useCreateCase();
  const session = getSession();

  const [patientName, setPatientName] = useState("");
  const [phone, setPhone] = useState("");
  const [payerId, setPayerId] = useState("");
  const [cptCode, setCptCode] = useState("");
  const [procedureName, setProcedureName] = useState("");
  const [channel, setChannel] = useState<"whatsapp" | "rcs" | "sms">("whatsapp");
  const [error, setError] = useState<string | null>(null);

  const payers = Array.from(new Set((rulesData?.rules ?? []).map((r) => r.payer_id))).sort();
  const rulesForPayer = (rulesData?.rules ?? []).filter((r) => r.payer_id === payerId);

  function pickRule(cpt: string) {
    setCptCode(cpt);
    const rule = rulesForPayer.find((r) => r.cpt_code === cpt);
    if (rule) setProcedureName(rule.procedure_name);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createCase.mutateAsync({
        patient_name: patientName.trim(),
        cpt_code: cptCode.trim(),
        procedure_name: procedureName.trim(),
        payer_id: payerId,
        channel,
        patient_phone_masked: phone.trim() ? `***${phone.trim().slice(-4)}` : undefined,
        actor: session?.username,
        // Tag the case with the signed-in staff member's hospital (Option A
        // multi-tenancy) so it shows up scoped to the right hospital.
        hospital_id: session?.hospital_id,
        hospital_name: session?.hospital_name,
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the case. Please try again.");
    }
  }

  const canSubmit = !!patientName.trim() && !!payerId && !!cptCode.trim() && !!procedureName.trim();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 px-4 backdrop-blur-md">
      <div className="glass-panel-strong w-full max-w-lg rounded-3xl p-6 shadow-popover animate-fade-in">
        <h2 className="font-serif text-lg font-semibold text-ink-900">Log a new case</h2>
        <p className="mt-1 text-sm text-ink-500">
          For phone calls or walk-ins that didn't come in through WhatsApp. Runs the same rule
          engine as the automated intake.
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Patient name
              </label>
              <input
                autoFocus
                value={patientName}
                onChange={(e) => setPatientName(e.target.value)}
                placeholder="R. Sharma"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Phone (last 4 digits)
              </label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="4821"
                maxLength={10}
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Intake channel
            </label>
            <div className="mt-1.5 flex gap-1 rounded-lg bg-ink-100 p-1">
              {(["whatsapp", "rcs", "sms"] as const).map((ch) => (
                <button
                  key={ch}
                  type="button"
                  onClick={() => setChannel(ch)}
                  className={
                    "flex-1 rounded-md px-3 py-1.5 text-xs font-semibold uppercase transition " +
                    (channel === ch ? "bg-white text-brand-700 shadow-card" : "text-ink-500 hover:text-ink-800")
                  }
                >
                  {ch}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">Payer</label>
            <select
              value={payerId}
              onChange={(e) => {
                setPayerId(e.target.value);
                setCptCode("");
                setProcedureName("");
              }}
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            >
              <option value="">Select payer...</option>
              {payers.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Procedure (CPT code)
            </label>
            <select
              value={cptCode}
              onChange={(e) => pickRule(e.target.value)}
              disabled={!payerId}
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25 disabled:bg-ink-50 disabled:text-ink-400"
            >
              <option value="">{payerId ? "Select procedure..." : "Select a payer first"}</option>
              {rulesForPayer.map((r) => (
                <option key={r.cpt_code} value={r.cpt_code}>
                  {r.cpt_code} - {r.procedure_name}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-ink-400">
              Picking a procedure here applies that payer's deterministic coverage rule
              automatically.
            </p>
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
              disabled={!canSubmit || createCase.isPending}
              className="rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 disabled:cursor-not-allowed disabled:from-ink-300 disabled:to-ink-300 disabled:shadow-none disabled:opacity-70"
            >
              {createCase.isPending ? "Logging case..." : "Log case"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
