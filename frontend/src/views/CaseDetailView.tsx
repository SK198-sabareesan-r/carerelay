import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import clsx from "clsx";
import { useCase } from "../hooks/useCases";
import { StatusBadge, OutcomeBadge, ChannelPill } from "../components/Badge";
import { AgentTrace } from "../components/AgentTrace";
import { WhatsAppPreview, RcsDoctorCardPreview, AuditEmailPreview } from "../components/ChannelPreview";

type Tab = "trace" | "whatsapp" | "rcs" | "audit" | "evidence";

const TABS: { id: Tab; label: string }[] = [
  { id: "trace", label: "Agent trace" },
  { id: "whatsapp", label: "Patient (WhatsApp)" },
  { id: "rcs", label: "Doctor (RCS)" },
  { id: "audit", label: "Audit email" },
  { id: "evidence", label: "Evidence" },
];

export function CaseDetailView() {
  const { caseId } = useParams<{ caseId: string }>();
  const { data, isLoading, isError, error } = useCase(caseId);
  const [tab, setTab] = useState<Tab>("trace");

  if (isLoading) return <div className="px-8 py-16 text-center text-sm text-ink-400">Loading case...</div>;
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

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <Link to="/queue" className="inline-flex items-center gap-1.5 text-sm text-ink-500 hover:text-ink-800">
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
          </div>
          <p className="mt-1 text-sm text-ink-500">
            {c.procedure_name} <span className="text-ink-300">&middot;</span> CPT{" "}
            <span className="font-mono">{c.cpt_code}</span> <span className="text-ink-300">&middot;</span>{" "}
            {c.payer_id} <span className="text-ink-300">&middot;</span> {c.patient_phone_masked}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <OutcomeBadge outcome={c.verification.outcome} />
          <StatusBadge status={c.status} />
        </div>
      </header>

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
                    : "text-ink-500 hover:bg-white/70 hover:text-ink-800"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="surface-3d mt-4 rounded-2xl p-5">
            {tab === "trace" && <AgentTrace steps={c.agent_trace} />}
            {tab === "whatsapp" && <WhatsAppPreview messages={c.messages} />}
            {tab === "rcs" && <RcsDoctorCardPreview messages={c.messages} />}
            {tab === "audit" && <AuditEmailPreview messages={c.messages} />}
            {tab === "evidence" && <EvidencePanel photoUrl={c.photo_url} audioUrl={c.audio_url} facts={c.perceived_facts} />}
          </div>
        </div>

        <div className="space-y-4">
          <RuleCitationCard
            matchedRuleId={c.verification.matched_rule_id}
            rationale={c.verification.rationale}
            missingDocs={c.verification.missing_documents}
          />
          <ExtractedCardPanel card={c.extracted_card} />
          {c.verification.payer_simulated && (
            <PayerSimulationCard
              eligible={c.verification.payer_eligible}
              approvalCode={c.verification.approval_code}
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
}: {
  matchedRuleId?: string | null;
  rationale: string;
  missingDocs: string[];
}) {
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
        <p className="ledger-line text-ink-700">{rationale}</p>
        {missingDocs.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {missingDocs.map((d) => (
              <span
                key={d}
                className="pill-3d rounded-md bg-gradient-to-b from-orange-50 to-orange-100 px-2 py-0.5 text-[11px] font-medium text-orange-800"
              >
                {d.replace(/_/g, " ")}
              </span>
            ))}
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

function PayerSimulationCard({ eligible, approvalCode }: { eligible?: boolean | null; approvalCode?: string | null }) {
  return (
    <div className="surface-3d rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-ink-800">Payer IVR verification</h3>
        <span className="pill-3d rounded-md bg-gradient-to-b from-white to-ink-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-ink-600">
          Simulated
        </span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink-500">
        Stands in for an outbound Amazon Connect call to the payer's IVR line. Deterministic per
        case for a reproducible demo - see docs/ARCHITECTURE.md.
      </p>
      <div className="mt-3 flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
        <span className="text-xs text-ink-500">Eligible</span>
        <span className={clsx("text-sm font-semibold", eligible ? "text-brand-700" : "text-rose-700")}>
          {eligible ? "Yes" : "No"}
        </span>
      </div>
      {approvalCode && (
        <div className="mt-2 flex items-center justify-between rounded-lg bg-ink-50 px-3 py-2">
          <span className="text-xs text-ink-500">Approval code</span>
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
          Perceived facts (Intake agent)
        </h4>
        {facts.length === 0 ? (
          <p className="text-sm text-ink-400">No additional facts captured for this case.</p>
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
