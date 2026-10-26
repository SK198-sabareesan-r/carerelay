import clsx from "clsx";
import type { AgentTraceStep } from "../types/case";

/**
 * Maps each internal processing stage to a plain, activity-oriented label
 * and tool description for the console. The UI intentionally does NOT
 * surface internal agent names - staff see WHAT happened (the logged
 * activity), not which component did it.
 */
const STAGE_META: Record<string, { label: string; dot: string; accent: string }> = {
  Intake: { label: "Documents captured", dot: "bg-sky-500", accent: "text-sky-700" },
  Verification: { label: "Coverage checked", dot: "bg-brand-600", accent: "text-brand-700" },
  Notification: { label: "Notifications sent", dot: "bg-violet-500", accent: "text-violet-700" },
};

const TOOL_LABELS: Record<string, string> = {
  "extract_insurance_card + transcribe_voice_note": "Insurance card read + voice note transcribed",
  check_prior_auth: "Prior-authorization rule evaluated",
  "send_payer_prior_auth_request (Amazon SES)": "Prior-auth request emailed to payer (Amazon SES)",
  "draft_patient_message + draft_doctor_approval_card + draft_audit_summary":
    "Patient message, doctor card, and audit summary prepared",
};

function toolLabel(tool: string): string {
  if (TOOL_LABELS[tool]) return TOOL_LABELS[tool];
  // Strip any lingering internal/simulated tool markers.
  return tool.replace(/\s*\(SIMULATED.*?\)/i, "").replace(/_/g, " ");
}

/**
 * Renders the case processing log: a timestamp-free, ordered record of the
 * activities performed on a case (documents captured, coverage checked,
 * notifications sent). Deterministic rule-engine steps get the "ledger"
 * treatment so they read visually distinct from narrated steps.
 */
export function AgentTrace({ steps }: { steps: AgentTraceStep[] }) {
  return (
    <ol className="relative space-y-0">
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        const isRuleStep = step.tool.startsWith("check_prior_auth");
        const meta = STAGE_META[step.agent] ?? {
          label: step.agent,
          dot: "bg-ink-400",
          accent: "text-ink-700",
        };
        return (
          <li key={idx} className="relative flex gap-4 pb-7 last:pb-0">
            {!isLast && <span className="absolute left-[7px] top-5 h-full w-px bg-ink-200" />}
            <div className="relative z-10 flex h-4 w-4 flex-none items-center justify-center pt-1.5">
              <span className={clsx("h-2.5 w-2.5 rounded-full ring-4 ring-white", meta.dot)} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className={clsx("text-sm font-semibold", meta.accent)}>{meta.label}</span>
                {isRuleStep && (
                  <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-700 ring-1 ring-inset ring-brand-200">
                    Deterministic
                  </span>
                )}
              </div>
              <code className="mt-1.5 block w-fit rounded bg-ink-100 px-2 py-0.5 font-mono text-[11px] text-ink-700">
                {toolLabel(step.tool)}
              </code>

              {isRuleStep ? (
                <ul className="mt-2.5 space-y-1 rounded-lg border border-brand-200 bg-brand-50/40 px-3 py-2.5">
                  {step.detail.map((line, i) => (
                    <li key={i} className="ledger-line text-brand-900">
                      {line}
                    </li>
                  ))}
                </ul>
              ) : (
                <ul className="mt-2 space-y-1">
                  {step.detail.map((line, i) => (
                    <li key={i} className="text-[13px] leading-relaxed text-ink-600">
                      <span className="mr-1.5 text-ink-300">&bull;</span>
                      {line}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
