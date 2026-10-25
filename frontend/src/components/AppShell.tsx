import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import clsx from "clsx";
import { getDataMode } from "../lib/api";
import { getSession, signOut } from "../lib/auth";
import { BrandMark } from "./BrandMark";
import { SettingsPanel } from "./SettingsPanel";

const NAV_ITEMS = [
  { to: "/analytics", label: "Analytics", icon: ChartIcon },
  { to: "/queue", label: "Intake Queue", icon: QueueIcon },
  { to: "/rules", label: "Rule Explorer", icon: RuleIcon },
];

export function AppShell() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [, forceRerender] = useState(0);
  const mode = getDataMode();
  const session = getSession();
  const navigate = useNavigate();

  function handleSignOut() {
    signOut();
    navigate("/login", { replace: true });
  }

  return (
    <div className="relative flex h-screen overflow-hidden">
      {/* Floating decorative orbs - purely cosmetic depth cues that sit
          behind the glass sidebar, visible through its blur/translucency. */}
      <div
        className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 animate-float rounded-full bg-brand-300/40 blur-3xl"
        style={{ "--tilt": "3deg" } as React.CSSProperties}
      />
      <div
        className="pointer-events-none absolute bottom-[-6rem] left-40 h-64 w-64 animate-float rounded-full bg-brand-200/30 blur-3xl"
        style={{ "--tilt": "-2deg", animationDelay: "1.5s" } as React.CSSProperties}
      />

      <aside className="glass-panel-strong relative z-10 flex w-64 flex-none flex-col rounded-r-3xl">
        <div className="flex items-center gap-3 px-5 py-6">
          <div className="surface-3d flex h-10 w-10 flex-none items-center justify-center rounded-xl">
            <BrandMark size={28} />
          </div>
          <div className="min-w-0">
            <div className="font-serif text-[16px] font-semibold leading-tight text-ink-900">CareRelay</div>
            <div className="truncate text-[11px] leading-tight text-ink-500">
              {session?.hospital_name ?? "Clinic Command Console"}
            </div>
          </div>
        </div>

        <nav className="mt-2 flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all",
                  isActive
                    ? "glass-tint-brand text-brand-800 shadow-raised"
                    : "text-ink-600 hover:bg-white/50 hover:text-ink-900"
                )
              }
            >
              <Icon className="h-[18px] w-[18px]" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="surface-3d mx-3 mb-3 rounded-2xl p-3.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-ink-500">Data source</span>
            <span
              className={clsx(
                "pill-3d inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                mode === "live" ? "bg-brand-50 text-brand-700" : "bg-ink-100 text-ink-600"
              )}
            >
              <span
                className={clsx(
                  "h-1.5 w-1.5 rounded-full",
                  mode === "live" ? "animate-pulse-ring bg-brand-500" : "bg-ink-400"
                )}
              />
              {mode === "live" ? "Live API" : "Mock demo"}
            </span>
          </div>
          <button
            onClick={() => setSettingsOpen(true)}
            className="mt-2.5 w-full rounded-lg border border-ink-200 bg-white/80 px-3 py-1.5 text-xs font-medium text-ink-700 shadow-xs transition hover:bg-white"
          >
            Configure endpoint
          </button>
        </div>

        <div className="border-t border-white/50 px-5 py-3">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-xs font-semibold text-ink-700">
                {session?.display_name ?? "Clinic Staff"}
              </div>
              <div className="truncate text-[10px] leading-tight text-ink-400">
                {session?.role ?? "Strands on Amazon Bedrock AgentCore"}
              </div>
            </div>
            <button
              onClick={handleSignOut}
              className="flex-none rounded-lg border border-ink-200 bg-white/70 px-2.5 py-1.5 text-[11px] font-medium text-ink-600 transition hover:bg-white hover:text-ink-900"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      <main className="relative z-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>

      {settingsOpen && (
        <SettingsPanel
          onClose={() => {
            setSettingsOpen(false);
            forceRerender((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}

function QueueIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M4 6h16M4 12h16M4 18h10"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RuleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M9 3h6l1 4H8l1-4ZM6 7h12l1 13H5L6 7Zm3 4h6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChartIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M4 20V10M11 20V4M18 20v-7"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
