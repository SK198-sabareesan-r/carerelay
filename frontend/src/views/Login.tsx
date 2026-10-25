import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { setSession } from "../lib/auth";
import { BrandMark } from "../components/BrandMark";

export function Login() {
  const navigate = useNavigate();
  const [hospitalId, setHospitalId] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { profile } = await api.login({
        username: username.trim(),
        password,
        hospital_id: hospitalId.trim(),
      });
      setSession(profile);
      navigate("/analytics", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 animate-float rounded-full bg-brand-400/35 blur-3xl" />
      <div
        className="pointer-events-none absolute -right-24 top-1/3 h-80 w-80 animate-float rounded-full bg-brand-300/30 blur-3xl"
        style={{ animationDelay: "1.2s" }}
      />

      <div className="relative z-10 w-full max-w-sm">
        <div className="mb-7 flex items-center justify-center gap-2.5">
          <BrandMark size={34} />
          <span className="font-serif text-lg font-semibold text-ink-900">CareRelay</span>
        </div>

        <div className="glass-panel-strong rounded-3xl p-8">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-ink-900">Sign in</h1>
          <p className="mt-1.5 text-sm text-ink-500">Clinic Command Console</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Hospital ID
              </label>
              <input
                autoFocus
                value={hospitalId}
                onChange={(e) => setHospitalId(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, ""))}
                placeholder="e.g. sunrisegeneralhospital"
                autoComplete="organization"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
              <p className="mt-1 text-[11px] text-ink-400">
                Letters and numbers only. Sent to your hospital's email when the account was created.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Username
              </label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. pnair"
                autoComplete="username"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !hospitalId || !username || !password}
              className="w-full rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-3 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 active:translate-y-px disabled:cursor-not-allowed disabled:from-ink-300 disabled:to-ink-300 disabled:shadow-none disabled:opacity-70"
            >
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-ink-500">
            New to CareRelay?{" "}
            <Link to="/signup" className="font-semibold text-brand-700 hover:underline">
              Create a staff account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
