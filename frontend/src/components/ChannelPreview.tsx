import { useEffect, useRef } from "react";
import type { DraftedMessages, PayerEmail, TranscriptMessage } from "../types/case";

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Double blue tick (read receipt) shown on outbound bubbles. */
function ReadTicks() {
  return (
    <svg viewBox="0 0 18 12" className="ml-0.5 inline-block h-3 w-4 align-[-1px]" fill="none" aria-label="Read">
      <path d="M1 6.5l3 3L10.5 3" stroke="#53bdeb" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M6.5 9.5L13 3" stroke="#53bdeb" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function VoiceBubble() {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="h-4 w-4 flex-none text-emerald-300" fill="currentColor">
        <path d="M12 14a3 3 0 003-3V5a3 3 0 10-6 0v6a3 3 0 003 3z" />
        <path d="M19 11a7 7 0 01-14 0H3a9 9 0 008 8.94V23h2v-3.06A9 9 0 0021 11h-2z" />
      </svg>
      <div className="flex flex-1 items-center gap-[3px]">
        {[6, 11, 8, 14, 9, 5, 12, 7, 10, 6].map((h, i) => (
          <span key={i} className="w-[2px] rounded-full bg-emerald-300/70" style={{ height: `${h}px` }} />
        ))}
      </div>
      <span className="text-[10px] text-slate-400">0:12</span>
    </div>
  );
}

function ImageBubble({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2">
      <svg viewBox="0 0 24 24" className="h-4 w-4 flex-none text-emerald-300" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <circle cx="8.5" cy="9.5" r="1.5" />
        <path d="M21 16l-5-5L5 20" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span>{label}</span>
    </div>
  );
}

function Bubble({ msg }: { msg: TranscriptMessage }) {
  const outbound = msg.direction === "outbound";
  return (
    <div className={outbound ? "flex justify-end" : "flex justify-start"}>
      <div
        className={
          "max-w-[82%] rounded-lg px-2.5 py-1.5 text-[12.5px] leading-relaxed shadow " +
          (outbound
            ? "rounded-tr-none bg-[#005c4b] text-slate-50"
            : "rounded-tl-none bg-[#1f2c34] text-slate-100")
        }
      >
        {msg.kind === "audio" ? (
          <VoiceBubble />
        ) : msg.kind === "image" ? (
          <ImageBubble label={msg.body || "Photo"} />
        ) : (
          <span className="whitespace-pre-wrap">{msg.body}</span>
        )}
        <div className="mt-0.5 flex items-center justify-end gap-0.5 text-[9.5px] text-slate-300/70">
          {formatTime(msg.timestamp)}
          {outbound && <ReadTicks />}
        </div>
      </div>
    </div>
  );
}

/**
 * Realtime, chat-style view of the actual WhatsApp conversation with the
 * patient, backed by the case `transcript` (inbound + outbound bubbles
 * persisted by the backend). Falls back to the single agent-drafted
 * message when no transcript exists yet (e.g. a legacy seeded case). The
 * parent (CaseDetailView) refetches on an interval, so new messages appear
 * without a manual reload.
 */
export function WhatsAppPreview({
  messages,
  transcript,
  patientName,
}: {
  messages: DraftedMessages;
  transcript?: TranscriptMessage[];
  patientName?: string;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const thread: TranscriptMessage[] =
    transcript && transcript.length > 0
      ? transcript
      : messages.patient_message_body
      ? [
          {
            direction: "outbound",
            kind: "text",
            body: messages.patient_message_body,
            actor: "agent",
            timestamp: new Date().toISOString(),
          },
        ]
      : [];

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread.length]);

  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
        Live conversation &middot; updates in realtime
      </div>
      <div className="mx-auto max-w-[320px] rounded-[30px] bg-[#0b141a] p-2 shadow-popover ring-1 ring-black/50">
        <div className="overflow-hidden rounded-[22px] border border-black/40 bg-[#0b141a]">
          {/* WhatsApp header chrome - solid opaque dark teal so it never
              washes out against the light console behind the phone frame. */}
          <div className="flex items-center gap-2.5 bg-[#202c33] px-3.5 py-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-emerald-400 to-emerald-600 text-xs font-bold text-white shadow-md">
              CR
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-1 text-[13px] font-semibold text-white">
                CareRelay
                <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-[#53bdeb]" fill="currentColor" aria-label="Verified business">
                  <path d="M12 2l2.4 1.8 3 .2.9 2.9 2.2 2-1 2.9 1 2.9-2.2 2-.9 2.9-3 .2L12 22l-2.4-1.8-3-.2-.9-2.9-2.2-2 1-2.9-1-2.9 2.2-2 .9-2.9 3-.2L12 2z" />
                  <path d="M10.5 14.2l-2-2-1.2 1.2 3.2 3.2 5.4-5.4-1.2-1.2-4.2 4.2z" fill="#0b141a" />
                </svg>
              </div>
              <div className="text-[10.5px] text-emerald-300">{patientName || "Patient"} &middot; online</div>
            </div>
            <svg viewBox="0 0 24 24" className="h-4 w-4 text-slate-300" fill="currentColor">
              <path d="M12 8a2 2 0 100-4 2 2 0 000 4zm0 2a2 2 0 100 4 2 2 0 000-4zm0 6a2 2 0 100 4 2 2 0 000-4z" />
            </svg>
          </div>
          {/* Message thread */}
          <div
            ref={scrollRef}
            className="max-h-[420px] min-h-[260px] space-y-1.5 overflow-y-auto bg-[#0b141a] bg-[radial-gradient(circle_at_center,#13232c_0%,#0b141a_100%)] px-3 py-3"
          >
            {thread.length === 0 ? (
              <div className="flex h-[220px] items-center justify-center px-6 text-center text-[12px] text-slate-500">
                No messages yet. The conversation will appear here once the patient is contacted.
              </div>
            ) : (
              thread.map((m, i) => <Bubble key={i} msg={m} />)
            )}

            {/* Agent-drafted quick-reply buttons attached to the latest outbound message */}
            {transcript && transcript.length > 0 && messages.patient_message_buttons.length > 0 && (
              <div className="flex justify-end">
                <div className="mt-0.5 w-[82%] space-y-[3px]">
                  {messages.patient_message_buttons.map((b) => (
                    <div
                      key={b.id}
                      className="rounded-lg bg-[#1f2c34] px-3 py-2 text-center text-[12.5px] font-medium text-[#53bdeb] shadow"
                    >
                      {b.title}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
          {/* Composer chrome (non-interactive, for realism) */}
          <div className="flex items-center gap-2 bg-[#202c33] px-3 py-2">
            <div className="flex-1 rounded-full bg-[#2a3942] px-3 py-1.5 text-[11.5px] text-slate-400">
              Message
            </div>
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-emerald-600 text-white">
              <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="currentColor">
                <path d="M2 21l21-9L2 3v7l15 2-15 2v7z" />
              </svg>
            </div>
          </div>
        </div>
      </div>
      <p className="mt-2 text-center text-[10.5px] text-ink-400">
        Delivered via AWS End User Messaging Social (WhatsApp Business)
      </p>
    </div>
  );
}

export function RcsDoctorCardPreview({ messages }: { messages: DraftedMessages }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-ink-200 bg-ink-25">
      <div className="flex items-center gap-2.5 border-b border-ink-200 bg-white px-3.5 py-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-700 text-xs font-bold text-white">
          Dr
        </div>
        <div>
          <div className="text-[13px] font-semibold text-ink-900">Clinic Approval Card</div>
          <div className="text-[11px] text-ink-500">
            RCS where supported &middot; WhatsApp buttons for +91 (India)
          </div>
        </div>
      </div>
      <div className="px-4 py-4">
        <div className="surface-3d rounded-xl p-3.5">
          <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-ink-800">
            {messages.doctor_card_body}
          </pre>
          <div className="mt-3 grid gap-2">
            {messages.doctor_card_buttons.map((b) => (
              <button
                key={b.id}
                disabled
                className="rounded-lg border border-brand-300 bg-brand-50 px-3 py-2 text-[13px] font-semibold text-brand-700"
              >
                {b.title}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * The full prior-authorization email correspondence between the hospital
 * and the insurance payer, shown as a threaded inbox with direction,
 * sender/recipient, subject, and timestamp on each message. Outbound =
 * clinic -> payer request; inbound = payer -> clinic determination.
 */
export function PayerEmailThread({ emails }: { emails?: PayerEmail[] }) {
  if (!emails || emails.length === 0) {
    return (
      <div className="flex min-h-[180px] items-center justify-center rounded-2xl border border-dashed border-ink-200 px-6 text-center text-sm text-ink-500">
        No payer correspondence yet. When prior authorization is required, the request and the
        payer's response will appear here.
      </div>
    );
  }
  const sorted = [...emails].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
        Hospital &harr; Payer correspondence &middot; Amazon SES
      </div>
      {sorted.map((e, i) => {
        const outbound = e.direction === "outbound";
        return (
          <div
            key={i}
            className={
              "overflow-hidden rounded-2xl border shadow-xs " +
              (outbound ? "border-brand-100 bg-white" : "border-sky-100 bg-sky-50/40")
            }
          >
            <div
              className={
                "flex items-center justify-between gap-2 border-b px-4 py-2 " +
                (outbound ? "border-brand-50 bg-brand-50/50" : "border-sky-100 bg-sky-50")
              }
            >
              <span
                className={
                  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide " +
                  (outbound ? "bg-brand-100 text-brand-800" : "bg-sky-100 text-sky-800")
                }
              >
                <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.2">
                  {outbound ? (
                    <path d="M4 12l16-8-6 16-3-7-7-1z" strokeLinejoin="round" />
                  ) : (
                    <path d="M4 6l8 7 8-7M4 6v12h16V6M4 6h16" strokeLinejoin="round" />
                  )}
                </svg>
                {outbound ? "Sent to payer" : "Reply from payer"}
              </span>
              <time className="text-[11px] text-ink-500">{formatDateTime(e.timestamp)}</time>
            </div>
            <div className="px-4 py-3">
              <div className="text-[13px] font-semibold text-ink-900">{e.subject}</div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[11px] text-ink-500">
                <span>
                  From <span className="font-medium text-ink-700">{e.from_label}</span>{" "}
                  <span className="font-mono">&lt;{e.from_addr}&gt;</span>
                </span>
                <span>
                  To <span className="font-medium text-ink-700">{e.to_label}</span>{" "}
                  <span className="font-mono">&lt;{e.to_addr}&gt;</span>
                </span>
              </div>
              <p className="mt-2.5 whitespace-pre-wrap text-[13px] leading-relaxed text-ink-700">{e.body}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function AuditEmailPreview({ messages }: { messages: DraftedMessages }) {
  return (
    <div className="surface-3d overflow-hidden rounded-2xl text-ink-900">
      <div className="border-b border-ink-200 bg-ink-25 px-4 py-2.5">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
          Amazon SES &middot; Case audit report
        </div>
        <div className="mt-0.5 font-serif text-[15px] font-semibold">{messages.audit_headline}</div>
      </div>
      <div className="px-4 py-3">
        <ul className="space-y-1.5">
          {messages.audit_detail_lines.map((line, i) => (
            <li key={i} className="ledger-line text-ink-700">
              {line}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
