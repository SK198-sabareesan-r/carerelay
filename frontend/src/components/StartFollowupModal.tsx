import { useState } from "react";
import { useStartFollowup, usePayerRules } from "../hooks/useCases";
import { ApiError } from "../lib/api";
import { getSession } from "../lib/auth";

/**
 * The primary CareRelay workflow entry point. After an in-person consult, a
 * doctor/staff member starts a follow-up: they enter the patient's phone,
 * the recommended procedure, the intended appointment date/time, and whether
 * the patient has insurance.
 *
 * - Insured  -> CareRelay WhatsApps the patient for their insurance card photo
 *   + a symptom voice note, verifies prior-auth, emails the payer, and only
 *   releases the appointment date/time once cleared.
 * - Self-pay -> CareRelay WhatsApps for a symptom voice note, routes it to the
 *   doctor for a 1-tap approval, then releases the date/time.
 *
 * The patient is never told the appointment time up front - it's withheld
 * until clearance/approval (see dashboard_api._handle_start_followup).
 */
export function StartFollowupModal({ onClose }: { onClose: () => void }) {
  const { data: rulesData } = usePayerRules();
  const startFollowup = useStartFollowup();
  const session = getSession();

  const [patientName, setPatientName] = useState("");
  const [phone, setPhone] = useState("");
  const [procedureName, setProcedureName] = useState("");
  const [apptDatetime, setApptDatetime] = useState("");
  const [hasInsurance, setHasInsurance] = useState(true);
  const [cptCode, setCptCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  // CPT options drawn from the known payer-rule catalog, de-duplicated by
  // CPT. Staff optionally pick the procedure's code; the PAYER itself is
  // NOT collected here - it is read from the patient's insurance card over
  // WhatsApp.
  const cptOptions = Array.from(
    new Map((rulesData?.rules ?? []).map((r) => [r.cpt_code, r])).values()
  ).sort((a, b) => a.cpt_code.localeCompare(b.cpt_code));

  function pickCpt(cpt: string) {
    setCptCode(cpt);
    const rule = cptOptions.find((r) => r.cpt_code === cpt);
    if (rule && !procedureName) setProcedureName(rule.procedure_name);
  }

  const canSubmit =
    !!patientName.trim() &&
    phone.replace(/[^0-9]/g, "").length >= 10 &&
    !!procedureName.trim() &&
    !!apptDatetime;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await startFollowup.mutateAsync({
        patient_name: patientName.trim(),
        patient_phone: phone.trim(),
        procedure_name: procedureName.trim(),
        appointment_datetime: formatDatetime(apptDatetime),
        has_insurance: hasInsurance,
        // Payer is omitted on purpose - resolved from the card over WhatsApp.
        cpt_code: hasInsurance && cptCode ? cptCode : undefined,
        actor: session?.username,
        hospital_id: session?.hospital_id,
        hospital_name: session?.hospital_name,
      });
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the follow-up. Please try again.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 px-4 backdrop-blur-md">
      <div className="glass-panel-strong max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-3xl p-6 shadow-popover animate-fade-in">
        <h2 className="font-serif text-lg font-semibold text-ink-900">Start a follow-up</h2>
        <p className="mt-1 text-sm text-ink-600">
          After the in-person consult. The patient gets a WhatsApp request; their appointment time is
          only released once insurance is cleared (or the doctor approves a self-pay visit).
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
                placeholder="Sarah Jenkins"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                WhatsApp number
              </label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+91 95007 99295"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Recommended procedure
            </label>
            <input
              value={procedureName}
              onChange={(e) => setProcedureName(e.target.value)}
              placeholder="Knee MRI with contrast"
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Intended appointment date &amp; time
            </label>
            <input
              type="datetime-local"
              value={apptDatetime}
              onChange={(e) => setApptDatetime(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
            />
            <p className="mt-1 text-[11px] text-ink-500">
              Withheld from the patient until insurance clearance / doctor approval.
            </p>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
              Does the patient have insurance?
            </label>
            <div className="mt-1.5 flex gap-1 rounded-lg bg-ink-100 p-1">
              {[
                { v: true, label: "Yes - insured" },
                { v: false, label: "No - self-pay" },
              ].map((opt) => (
                <button
                  key={String(opt.v)}
                  type="button"
                  onClick={() => setHasInsurance(opt.v)}
                  className={
                    "flex-1 rounded-md px-3 py-1.5 text-xs font-semibold transition " +
                    (hasInsurance === opt.v ? "bg-white text-brand-700 shadow-card" : "text-ink-600 hover:text-ink-800")
                  }
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {hasInsurance && (
            <div className="space-y-2 rounded-xl border border-ink-100 bg-ink-50/50 p-3">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Procedure CPT code <span className="font-normal text-ink-400">(optional)</span>
                </label>
                <select
                  value={cptCode}
                  onChange={(e) => pickCpt(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                >
                  <option value="">Not specified - infer from procedure</option>
                  {cptOptions.map((r) => (
                    <option key={r.cpt_code} value={r.cpt_code}>
                      {r.cpt_code} - {r.procedure_name}
                    </option>
                  ))}
                </select>
              </div>
              <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-ink-500">
                <svg viewBox="0 0 24 24" className="mt-0.5 h-3.5 w-3.5 flex-none text-brand-500" fill="currentColor">
                  <path d="M20 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V6a2 2 0 00-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z" />
                </svg>
                The insurer, member ID, and group number are read automatically from the insurance
                card the patient sends over WhatsApp - staff don't enter them here.
              </p>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm font-medium text-ink-600 hover:text-ink-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit || startFollowup.isPending}
              className="rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-2 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 disabled:cursor-not-allowed disabled:from-ink-300 disabled:to-ink-300 disabled:shadow-none disabled:opacity-70"
            >
              {startFollowup.isPending ? "Starting..." : "Start follow-up"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/** datetime-local gives "2026-10-27T10:00"; present it as a friendly string. */
function formatDatetime(value: string): string {
  if (!value) return value;
  const d = new Date(value);
  if (isNaN(d.getTime())) return value;
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
