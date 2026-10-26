import { useState } from "react";
import { useSendMessage } from "../hooks/useCases";
import { ApiError } from "../lib/api";
import { getSession } from "../lib/auth";

/**
 * Lets staff send a free-text WhatsApp message directly to the patient,
 * bypassing the agent entirely - e.g. answering a question the automated
 * flow didn't anticipate. Only usable when the case has a real WhatsApp
 * thread behind it (can_message_patient - see dashboard_api.handler.
 * _handle_send_message and its patient_phone requirement).
 */
export function MessageComposer({ caseId, canMessage }: { caseId: string; canMessage: boolean }) {
  const sendMessage = useSendMessage();
  const session = getSession();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleSend() {
    if (!text.trim()) return;
    setError(null);
    try {
      await sendMessage.mutateAsync({ caseId, text: text.trim(), actor: session?.username });
      setText("");
      setSent(true);
      setTimeout(() => setSent(false), 2500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send the message. Please try again.");
    }
  }

  if (!canMessage) {
    return (
      <div className="mt-4 rounded-xl border border-dashed border-ink-300 bg-ink-50 px-4 py-3 text-xs text-ink-500">
        This case has no WhatsApp thread to reply to (it wasn't created from an inbound WhatsApp message).
      </div>
    );
  }

  return (
    <div className="mt-4 rounded-xl border border-ink-200 bg-white p-3">
      <label className="block text-[11px] font-semibold uppercase tracking-wide text-ink-500">
        Send a message to the patient
      </label>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSend();
          }
        }}
        placeholder="Type a WhatsApp message to send directly to the patient..."
        rows={2}
        maxLength={4096}
        className="mt-1.5 w-full resize-none rounded-lg border border-ink-200 px-3 py-2 text-sm text-ink-800 outline-none placeholder:text-ink-500 focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
      />
      {error && <p className="mt-1.5 text-[11px] text-rose-600">{error}</p>}
      {sent && <p className="mt-1.5 text-[11px] text-brand-700">Message sent.</p>}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[11px] text-ink-500">Sent verbatim - exactly as typed.</span>
        <button
          onClick={handleSend}
          disabled={!text.trim() || sendMessage.isPending}
          className="rounded-lg bg-brand-700 px-3.5 py-1.5 text-xs font-semibold text-white transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-ink-300"
        >
          {sendMessage.isPending ? "Sending..." : "Send"}
        </button>
      </div>
    </div>
  );
}
