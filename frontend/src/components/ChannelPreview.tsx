import type { DraftedMessages } from "../types/case";

export function WhatsAppPreview({ messages }: { messages: DraftedMessages }) {
  return (
    <div>
      <div className="mb-2.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        Live device preview &middot; Patient handset
      </div>
      {/* "Phone frame" mockup, deliberately dark (real WhatsApp chrome) and
          deliberately framed with a bezel + ambient shadow, so it reads as
          an intentional device mockup rather than a stray dark box inside
          the light console theme. */}
      <div className="mx-auto max-w-[300px] rounded-[28px] bg-gradient-to-b from-ink-700 to-ink-900 p-2 shadow-popover">
        <div className="overflow-hidden rounded-[20px] border border-black/40 bg-[#0b141a]">
          <div className="flex items-center gap-2.5 bg-[#1f2c34] px-3.5 py-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-emerald-500 to-emerald-700 text-xs font-bold text-white shadow-md">
              CR
            </div>
            <div>
              <div className="text-[13px] font-semibold text-slate-100">CareRelay</div>
              <div className="text-[10.5px] text-slate-400">via AWS End User Messaging Social</div>
            </div>
          </div>
          <div className="min-h-[220px] bg-[repeating-linear-gradient(135deg,#0b141a,#0b141a_10px,#0e1a21_10px,#0e1a21_20px)] px-3.5 py-4">
            <div className="max-w-[88%] rounded-lg rounded-tl-none bg-[#1f2c34] px-3 py-2 text-[13px] leading-relaxed text-slate-100 shadow-lg">
              {messages.patient_message_body}
              <div className="mt-1 text-right text-[10px] text-slate-500">
                {new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              </div>
            </div>
            {messages.patient_message_buttons.length > 0 && (
              <div className="mt-1.5 max-w-[88%] divide-y divide-slate-700/60 overflow-hidden rounded-lg bg-[#1f2c34] shadow-lg">
                {messages.patient_message_buttons.map((b) => (
                  <div key={b.id} className="px-3 py-2 text-center text-[13px] font-medium text-emerald-400">
                    {b.title}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function RcsDoctorCardPreview({ messages }: { messages: DraftedMessages }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-ink-200 bg-ink-25">
      <div className="flex items-center gap-2.5 border-b border-ink-200 bg-white px-3.5 py-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-700 text-xs font-bold text-white">
          RCS
        </div>
        <div>
          <div className="text-[13px] font-semibold text-ink-900">Clinic Approval Card</div>
          <div className="text-[11px] text-ink-500">via AWS End User Messaging (RCS)</div>
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

export function AuditEmailPreview({ messages }: { messages: DraftedMessages }) {
  return (
    <div className="surface-3d overflow-hidden rounded-2xl text-ink-900">
      <div className="border-b border-ink-200 bg-ink-25 px-4 py-2.5">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
          Amazon SES &middot; KMS-signed audit report
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
