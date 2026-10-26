import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getApiBase, getDataMode, setApiBase, setDataMode, type DataMode } from "../lib/api";

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState(getApiBase());
  const [mode, setMode] = useState<DataMode>(getDataMode());
  const queryClient = useQueryClient();

  function save() {
    setApiBase(url);
    setDataMode(mode);
    queryClient.invalidateQueries();
    onClose();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 px-4 backdrop-blur-md">
      <div className="glass-panel-strong w-full max-w-lg rounded-3xl p-6 shadow-popover animate-fade-in">
        <h2 className="font-serif text-lg font-semibold text-ink-900">Data source</h2>
        <p className="mt-1 text-sm text-ink-600">
          <strong className="text-ink-800">Live API</strong> is connected to the real deployed{" "}
          <code className="rounded bg-ink-100 px-1 py-0.5 text-xs text-ink-700">dashboard_api</code> endpoint by
          default - cases, rules, and stats come from DynamoDB. Switch to{" "}
          <strong className="text-ink-800">Mock demo data</strong> to browse a self-contained sample
          dataset with zero AWS setup (e.g. for an offline demo).
        </p>

        <div className="mt-5 flex gap-1 rounded-lg bg-ink-100 p-1">
          {(["mock", "live"] as DataMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={
                "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition " +
                (mode === m ? "bg-white text-brand-700 shadow-card" : "text-ink-600 hover:text-ink-800")
              }
            >
              {m === "mock" ? "Mock demo data" : "Live API"}
            </button>
          ))}
        </div>

        <div className="mt-4">
          <label className="block text-xs font-medium uppercase tracking-wide text-ink-500">
            API base URL
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={mode === "mock"}
            placeholder="https://xxxx.execute-api.ap-south-1.amazonaws.com/prod"
            className="mt-1.5 w-full rounded-lg border border-ink-200 bg-white px-3 py-2 font-mono text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-1 focus:ring-brand-500 disabled:bg-ink-50 disabled:text-ink-500"
          />
          <p className="mt-1.5 text-xs text-ink-600">
            Pre-filled with the live endpoint. Only change this if you've redeployed
            <span className="font-mono"> dashboard_api</span> (see{" "}
            <span className="font-mono">scripts/deploy_api_gateway.py</span>) and have a different
            API Gateway URL to point at.
          </p>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm font-medium text-ink-600 hover:text-ink-800"
          >
            Cancel
          </button>
          <button
            onClick={save}
            className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-800"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
