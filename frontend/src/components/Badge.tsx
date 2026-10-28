import clsx from "clsx";
import type { CaseStatus, PriorAuthOutcome } from "../types/case";

const STATUS_STYLES: Record<CaseStatus, string> = {
  OPEN: "bg-ink-100 text-ink-700",
  APPROVED: "bg-gradient-to-b from-brand-50 to-brand-100 text-brand-800",
  DENIED: "bg-gradient-to-b from-rose-50 to-rose-100 text-rose-700",
  AWAITING_DOCUMENTS: "bg-gradient-to-b from-amber-50 to-amber-100 text-amber-800",
  AWAITING_INSURANCE_DOCS: "bg-gradient-to-b from-amber-50 to-amber-100 text-amber-800",
  AWAITING_VOICE_NOTE: "bg-gradient-to-b from-amber-50 to-amber-100 text-amber-800",
  AWAITING_PAYER: "bg-gradient-to-b from-violet-50 to-violet-100 text-violet-800",
  PENDING_DOCTOR_APPROVAL: "bg-gradient-to-b from-sky-50 to-sky-100 text-sky-800",
  SCHEDULED: "bg-gradient-to-b from-brand-50 to-brand-100 text-brand-800",
};

const OUTCOME_STYLES: Record<PriorAuthOutcome, string> = {
  PRIOR_AUTH_REQUIRED: "bg-gradient-to-b from-amber-50 to-amber-100 text-amber-800",
  NOT_REQUIRED: "bg-gradient-to-b from-brand-50 to-brand-100 text-brand-800",
  INCOMPLETE_INFO: "bg-gradient-to-b from-orange-50 to-orange-100 text-orange-800",
  NO_MATCHING_RULE: "bg-gradient-to-b from-rose-50 to-rose-100 text-rose-700",
};

const OUTCOME_LABELS: Record<PriorAuthOutcome, string> = {
  PRIOR_AUTH_REQUIRED: "Prior auth required",
  NOT_REQUIRED: "No auth needed",
  INCOMPLETE_INFO: "Missing documents",
  NO_MATCHING_RULE: "No matching rule",
};

export function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span
      className={clsx(
        "pill-3d inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold",
        STATUS_STYLES[status]
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function OutcomeBadge({ outcome }: { outcome: PriorAuthOutcome }) {
  return (
    <span
      className={clsx(
        "pill-3d inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        OUTCOME_STYLES[outcome]
      )}
    >
      {OUTCOME_LABELS[outcome]}
    </span>
  );
}

export function ChannelPill({ channel }: { channel: string }) {
  const labels: Record<string, string> = { whatsapp: "WhatsApp", rcs: "RCS", sms: "SMS" };
  return (
    <span className="pill-3d inline-flex items-center rounded-md bg-gradient-to-b from-white to-ink-50 px-2 py-0.5 text-[11px] font-medium text-ink-600">
      {labels[channel] ?? channel}
    </span>
  );
}
