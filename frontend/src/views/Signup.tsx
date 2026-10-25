import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { setSession } from "../lib/auth";
import { BrandMark } from "../components/BrandMark";

const ROLES = ["Clinic Physician", "Billing Coordinator", "Front Desk", "Admin"];

export function Signup() {
  const navigate = useNavigate();
  const [hospitalName, setHospitalName] = useState("");
  const [hospitalAddress, setHospitalAddress] = useState("");
  const [hospitalEmail, setHospitalEmail] = useState("");
  const [hospitalPhone, setHospitalPhone] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState(ROLES[0]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    !!hospitalName &&
    hospitalAddress.trim().length >= 5 &&
    !!hospitalEmail &&
    !!hospitalPhone &&
    !!displayName &&
    !!username &&
    password.length >= 8;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { profile } = await api.signup({
        username: username.trim(),
        password,
        display_name: displayName.trim(),
        hospital_name: hospitalName.trim(),
        hospital_address: hospitalAddress.trim(),
        hospital_email: hospitalEmail.trim(),
        hospital_phone: hospitalPhone.trim(),
        role,
      });
      setSession(profile);
      navigate("/analytics", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="pointer-events-none absolute -left-32 -top-32 h-96 w-96 animate-float rounded-full bg-brand-400/35 blur-3xl" />
      <div
        className="pointer-events-none absolute -right-24 bottom-0 h-80 w-80 animate-float rounded-full bg-brand-300/30 blur-3xl"
        style={{ animationDelay: "1.2s" }}
      />

      <div className="relative z-10 w-full max-w-md">
        <div className="mb-7 flex items-center justify-center gap-2.5">
          <BrandMark size={34} />
          <span className="font-serif text-lg font-semibold text-ink-900">CareRelay</span>
        </div>

        <div className="glass-panel-strong rounded-3xl p-8">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-ink-900">Create account</h1>
          <p className="mt-1.5 text-sm text-ink-500">Register your hospital and your staff login to access the console.</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-5">
            <fieldset className="space-y-4">
              <legend className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">
                Hospital details
              </legend>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Hospital name
                </label>
                <input
                  autoFocus
                  value={hospitalName}
                  onChange={(e) => setHospitalName(e.target.value)}
                  placeholder="e.g. Sunrise General Hospital"
                  autoComplete="organization"
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                />
                <p className="mt-1 text-[11px] text-ink-400">
                  We'll generate an alphanumeric Hospital ID from this name (letters and numbers only) -
                  you'll use it to sign in later.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Hospital address
                </label>
                <input
                  value={hospitalAddress}
                  onChange={(e) => setHospitalAddress(e.target.value)}
                  placeholder="221 Marine Drive, Mumbai, MH 400002"
                  autoComplete="street-address"
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Hospital email
                  </label>
                  <input
                    type="email"
                    value={hospitalEmail}
                    onChange={(e) => setHospitalEmail(e.target.value)}
                    placeholder="contact@hospital.com"
                    autoComplete="email"
                    className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                    Hospital phone
                  </label>
                  <input
                    type="tel"
                    value={hospitalPhone}
                    onChange={(e) => setHospitalPhone(e.target.value)}
                    placeholder="+91 22 6655 0100"
                    autoComplete="tel"
                    className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                  />
                </div>
              </div>
              <p className="text-[11px] text-ink-400">
                We'll send an onboarding email with your Hospital ID to this address.
              </p>
            </fieldset>

            <fieldset className="space-y-4 border-t border-ink-100 pt-4">
              <legend className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">
                Your account
              </legend>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Full name
                </label>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Dr. Priya Nair"
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">Role</label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                >
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Username
                </label>
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value.toLowerCase())}
                  placeholder="e.g. pnair"
                  autoComplete="username"
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                />
                <p className="mt-1 text-[11px] text-ink-400">Lowercase letters, numbers, dot, underscore, or hyphen.</p>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  autoComplete="new-password"
                  className="mt-1.5 w-full rounded-xl border border-ink-200 bg-white px-3.5 py-2.5 text-sm text-ink-800 outline-none placeholder:text-ink-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/25"
                />
              </div>
            </fieldset>

            {error && (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={submitting || !canSubmit}
              className="w-full rounded-xl bg-gradient-to-b from-brand-600 to-brand-700 px-4 py-3 text-sm font-semibold text-white shadow-raised transition hover:from-brand-500 hover:to-brand-600 active:translate-y-px disabled:cursor-not-allowed disabled:from-ink-300 disabled:to-ink-300 disabled:shadow-none disabled:opacity-70"
            >
              {submitting ? "Creating account..." : "Create account"}
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-ink-500">
            Already have an account?{" "}
            <Link to="/login" className="font-semibold text-brand-700 hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
