import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import clsx from "clsx";
import { useCase, useUpdateCaseStatus } from "../hooks/useCases";
import { StatusBadge, OutcomeBadge, ChannelPill } from "../components/Badge";
import { AgentTrace } from "../components/AgentTrace";
import {
  WhatsAppPreview,
  RcsDoctorCardPreview,
  AuditEmailPreview,
  PayerEmailThread,
} from "../components/ChannelPreview";
import { ActivityLog } from "../components/ActivityLog";
import { StatusUpdateControl } from "../components/StatusUpdateControl";
import { MessageComposer } from "../components/MessageComposer";
import type { CaseStatus } from "../types/case";

type Tab = "conversations" | "payer" | "trace" | "evidence";

const TABS: { id: Tab; label: string }[] = [
  { id: "conversations", label: "Conversations" },
  { id: "payer", label: "Payer emails" },
  { id: "trace", label: "Processing log" },
  { id: "evidence", label: "Timeline & evidence" },
];

export function CaseDetailView() {
  const { caseId } = useParams<{ caseId: string }>();
  const { data, isLoading, isError, error } = useCase(caseId);
  const updateStatus = useUpdateCaseStatus();
  const [tab, setTab] = useState<Tab>("conversations");

  if (isLoading) return <div className="px-8 py-16 text-center text-sm text-ink-500">Loading case...</div>;
  if (isError || !data) {
    return (
      <div className="mx-auto max-w-2xl px-8 py-16 text-center">
        <p className="text-sm text-rose-600">{(error as Error)?.message ?? "Case not found."}</p>
        <Link to="/queue" className="mt-4 inline-block text-sm text-brand-700 hover:underline">
          &larr; Back to queue
        </Link>
      </div>
    );
  }

  const c = data.case;

  async function handleStatusChange(status: CaseStatus, note: string) {
    await updateStatus.mutateAsync({ caseId: c.case_id, status, note });
  }

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <Link to="/queue" className="inline-flex items-center gap-1.5 text-sm text-ink-600 hover:text-ink-800">
        <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
          <path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Intake queue
      </Link>

      <header className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink-900">{c.patient_name}</h1>
            <ChannelPill channel={c.channel} />
            {c.hospital_name && (
              <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-[11px] font-semibold text-brand-700 ring-1 ring-inset ring-brand-200">
                {c.hospital_name}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-ink-600">
            {c.procedure_name} <span className="text-ink-400">&middot;</span> CPT{" "}
            <span className="font-mono">{c.cpt_code}</span> <span className="text-ink-400">&middot;</span>{" "}
            {c.payer_id} <span className="text-ink-400">&middot;</span> {c.patient_phone_masked}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex items-center gap-2">
            {/* The coverage OUTCOME badge (e.g. "Missing documents") is only
                meaningful during verification. Once the case has advanced
                past the payer step, the live StatusBadge is the single source
                of truth - showing the stale INCOMPLETE_INFO outcome alongside
                an APPROVED status is contradictory, so hide it then. */}
            {c.verification?.outcome &&
              !["AWAITING_PAYER", "APPROVED", "PENDING_DOCTOR_APPROVAL", "SCHEDULED", "DENIED"].includes(c.status) && (
                <OutcomeBadge outcome={c.verification.outcome} />
              )}
            <StatusBadge status={c.status} />
          </div>
          <StatusUpdateControl
            currentStatus={c.status}
            onChange={handleStatusChange}
            isSaving={updateStatus.isPending}
          />
        </div>
      </header>

      {c.flow && c.appointment_datetime && (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-2xl border border-brand-100 bg-brand-50/60 px-4 py-3 text-sm">
          <span className="font-semibold text-brand-800">
            {c.has_insurance ? "Insured follow-up" : "Self-pay follow-up"}
          </span>
          <span className="text-ink-600">
            Appointment: <strong className="text-ink-900">{c.appointment_datetime}</strong>
          </span>
          {(() => {
            // ONE status chip, driven by the case's current status (the single
            // source of truth), so it moves through the lifecycle as staff /
            // the doctor act - never a stale "Withheld" after the card is out.
            const released = c.appointment_released || c.status === "SCHEDULED";
            const stage: Record<string, [string, string]> = {
              AWAITING_INSURANCE_DOCS: ["Awaiting patient documents", "bg-amber-100 text-amber-800"],
              AWAITING_VOICE_NOTE: ["Awaiting patient voice note", "bg-amber-100 text-amber-800"],
              AWAITING_PAYER: ["Awaiting payer confirmation", "bg-violet-100 text-violet-800"],
              PENDING_DOCTOR_APPROVAL: ["With doctor for approval", "bg-sky-100 text-sky-800"],
              SCHEDULED: ["Confirmed to patient", "bg-brand-100 text-brand-800"],
              APPROVED: ["Payer approved - with doctor", "bg-sky-100 text-sky-800"],
            };
            const [label, cls] = released
              ? ["Confirmed to patient", "bg-brand-100 text-brand-800"]
              : stage[c.status] || ["Withheld until cleared", "bg-amber-100 text-amber-800"];
            return <span className={"rounded-full px-2.5 py-0.5 text-[11px] font-semibold " + cls}>{label}</span>;
          })()}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-[1.3fr_1fr]">
        <div>
          <div className="glass-panel flex gap-1 overflow-x-auto rounded-2xl p-1.5">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={clsx(
                  "flex-none rounded-xl px-3.5 py-2 text-xs font-semibold transition-all",
                  tab === t.id
                    ? "bg-gradient-to-b from-brand-600 to-brand-700 text-white shadow-raised"
                    : "text-ink-600 hover:bg-white/70 hover:text-ink-800"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="surface-3d mt-4 rounded-2xl p-5">
            {tab === "conversations" && (
              <div className="space-y-6">
                <WhatsAppPreview
                  messages={c.messages}
                  transcript={c.transcript}
                  patientName={c.patient_name}
                  hospitalName={c.hospital_name}
                />
                <MessageComposer caseId={c.case_id} canMessage={c.can_message_patient} />
                {c.messages?.doctor_card_body && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                      Doctor approval card
                    </h4>
                    <RcsDoctorCardPreview messages={c.messages} />
                  </div>
                )}
              </div>
            )}
            {tab === "payer" && <PayerEmailThread emails={c.payer_emails} />}
            {tab === "trace" && <AgentTrace steps={c.agent_trace} />}
            {tab === "evidence" && (
              <div className="space-y-6">
                <EvidencePanel photoUrl={c.photo_url} audioUrl={c.audio_url} facts={c.perceived_facts} />
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Case timeline
                  </h4>
                  <ActivityLog entries={c.activity_log} />
                </div>
                {c.messages?.audit_headline && (
                  <div>
                    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                      Audit email
                    </h4>
                    <AuditEmailPreview messages={c.messages} />
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <RuleCitationCard
            matchedRuleId={c.verification?.matched_rule_id}
            rationale={c.verification?.rationale}
            missingDocs={c.verification?.missing_documents}
            status={c.status}
          />
          <ExtractedCardPanel card={c.extracted_card} />
          {c.verification?.outcome === "PRIOR_AUTH_REQUIRED" && (
            <PayerContactCard
              approvalCode={c.verification.approval_code}
              eligible={c.verification.payer_eligible}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function RuleCitationCard({
  matchedRuleId,
  rationale,
  missingDocs,
  status,
}: {
  matchedRuleId?: string | null;
  rationale?: string | null;
  missingDocs?: string[] | null;
  status?: string;
}) {
  const docs = missingDocs ?? [];
  const hasVerification = !!(rationale || matchedRuleId);
  // Once the case has moved past verification (payer confirmed / with the
  // doctor / scheduled), the "missing documents" pills are stale - the payer
  // handles those during their review. Only show them while we're still
  // verifying. This keeps a SINGLE, stage-accurate status, not a permanent
  // "missing documents" flag.
  const preClearance = !status || ["AWAITING_INSURANCE_DOCS", "AWAITING_VOICE_NOTE",
    "AWAITING_DOCUMENTS", "OPEN", "AWAITING_PAYER"].includes(status);
  const showDocs = docs.length > 0 && preClearance;
  const cleared = ["APPROVED", "PENDING_DOCTOR_APPROVAL", "SCHEDULED"].includes(status || "");
  return (
    <div className="relative overflow-hidden rounded-2xl shadow-raised">
      <div className="pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full bg-brand-300/30 blur-2xl" />
      <div className="relative flex items-center gap-2 bg-gradient-to-br from-brand-700 to-brand-800 px-4 py-3">
        <span className="pill-3d rounded-md bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-brand-800">
          Code decides
        </span>
        <span className="font-mono text-xs text-brand-50">{matchedRuleId ?? "no matching rule"}</span>
      </div>
      <div className="relative bg-white px-4 py-3.5">
        <p className="ledger-line text-ink-700">
          {hasVerification
            ? rationale
            : "Coverage not yet evaluated — waiting on the patient's insurance card and voice note."}
        </p>
        {showDocs && (
          <div className="mt-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
              Documents the payer will review
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {docs.map((d) => (
                <span
                  key={d}
                  className="pill-3d rounded-md bg-gradient-to-b from-orange-50 to-orange-100 px-2 py-0.5 text-[11px] font-medium text-orange-800"
                >
                  {d.replace(/_/g, " ")}
                </span>
              ))}
            </div>
          </div>
        )}
        {cleared && (
          <div className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-brand-50 px-2.5 py-1 text-[11px] font-semibold text-brand-700 ring-1 ring-inset ring-brand-200">
            Coverage confirmed by payer
          </div>
        )}
      </div>
    </div>
  );
}

function ExtractedCardPanel({ card }: { card: { payer_name?: string | null; member_id?: string | null; group_number?: string | null; confidence?: number | null } }) {
  const rows: [string, string | null | undefined][] = [
    ["Payer", card.payer_name],
    ["Member ID", card.member_id],
    ["Group number", card.group_number],
  ];
  return (
    <div className="surface-3d rounded-2xl p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink-800">Insurance card (Bedrock vision)</h3>
        {card.confidence != null && (
          <span className="pill-3d rounded-md bg-gradient-to-b from-white to-ink-100 px-2 py-0.5 text-[11px] font-semibold text-ink-600">
            {card.confidence}% confidence
          </span>
        )}
      </div>
      <dl className="mt-3 space-y-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between text-[13px]">
            <dt className="text-ink-500">{label}</dt>
            <dd className="font-mono text-ink-800">{value || "—"}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function PayerContactCard({ eligible, approvalCode }: { eligible?: boolean | null; approvalCode?: string | null }) {
  return (
    <div className="surface-3d rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-ink-800">Payer contact</h3>
        <span className="pill-3d rounded-md bg-gradient-to-b from-white to-ink-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink-600">
          Amazon SES
        </span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-600">
        CareRelay contacts the insurance payer by email only - a formal written prior-authorization
        request sent to the payer's intake inbox via Amazon SES. No IVR or phone call is placed.
      </p>
      {eligible != null && (
        <div className="mt-3 flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
          <span className="text-xs text-ink-600">Payer response</span>
          <span className={clsx("text-sm font-semibold", eligible ? "text-brand-700" : "text-rose-700")}>
            {eligible ? "Eligible" : "Pending / not eligible"}
          </span>
        </div>
      )}
      {approvalCode && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
          <span className="text-xs text-ink-600">Approval code</span>
          <span className="font-mono text-sm text-ink-800">{approvalCode}</span>
        </div>
      )}
    </div>
  );
}

function EvidencePanel({
  photoUrl,
  audioUrl,
  facts,
}: {
  photoUrl?: string | null;
  audioUrl?: string | null;
  facts: string[];
}) {
  return (
    <div className="space-y-4">
      {photoUrl && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Insurance card photo</h4>
          <img src={photoUrl} alt="Insurance card" className="rounded-lg border border-ink-200" />
        </div>
      )}
      {audioUrl && (
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">Symptom voice note</h4>
          <audio controls src={audioUrl} className="w-full" />
        </div>
      )}
      <div>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
          Captured details
        </h4>
        {facts.length === 0 ? (
          <p className="text-sm text-ink-500">No additional facts captured for this case.</p>
        ) : (
          <ul className="space-y-1.5">
            {facts.map((f, i) => (
              <li key={i} className="text-[13px] leading-relaxed text-ink-700">
                &bull; {f}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
