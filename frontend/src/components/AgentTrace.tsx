import clsx from "clsx";
import type { AgentTraceStep } from "../types/case";

const AGENT_STYLES: Record<string, { dot: string; label: string }> = {
  Intake: { dot: "bg-sky-500", label: "text-sky-700" },
  Verification: { dot: "bg-brand-600", label: "text-brand-700" },
  Notification: { dot: "bg-violet-500", label: "text-violet-700" },
};

/**
 * Renders the Strands multi-agent pipeline (Intake -> Verification ->
 * Notification) as a visual trace. This is the "code decides, AI talks"
 * claim made legible: deterministic rule-engine steps get the "ledger"
 * treatment (monospace, left rule, "Deterministic" tag) so they read
 * visually distinct from AI-narrated steps, the same way clinical software
 * separates a verified lab value from a clinician's free-text note.
 */
export function AgentTrace({ steps }: { steps: AgentTraceStep[] }) {
  return (
    <ol className="relative space-y-0">
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        const isRuleStep = step.tool.startsWith("check_prior_auth");
        const isSimStep = step.tool.includes("SIMULATED");
        const style = AGENT_STYLES[step.agent] ?? { dot: "bg-ink-400", label: "text-ink-700" };
        return (
          <li key={idx} className="relative flex gap-4 pb-7 last:pb-0">
            {!isLast && <span className="absolute left-[7px] top-5 h-full w-px bg-ink-200" />}
            <div className="relative z-10 flex h-4 w-4 flex-none items-center justify-center pt-1.5">
              <span className={clsx("h-2.5 w-2.5 rounded-full ring-4 ring-white", style.dot)} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className={clsx("text-sm font-semibold", style.label)}>{step.agent} agent</span>
                {isRuleStep && (
                  <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-700 ring-1 ring-inset ring-brand-200">
                    Deterministic
                  </span>
                )}
                {isSimStep && (
                  <span className="rounded-md bg-ink-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink-600 ring-1 ring-inset ring-ink-200">
                    Simulated
                  </span>
                )}
              </div>
              <code className="mt-1.5 block w-fit rounded bg-ink-100 px-2 py-0.5 font-mono text-[11px] text-ink-700">
                {step.tool}
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
