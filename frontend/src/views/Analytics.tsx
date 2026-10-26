import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Label,
  LabelList,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useStats } from "../hooks/useCases";
import { StatTile } from "../components/StatTile";

// Richer, more saturated palette than the muted UI accent colors - charts
// need stronger hue separation than chrome does to stay legible at a glance.
const OUTCOME_COLORS: Record<string, [string, string]> = {
  PRIOR_AUTH_REQUIRED: ["#fbbf24", "#b45309"],
  NOT_REQUIRED: ["#34d399", "#0f766e"],
  INCOMPLETE_INFO: ["#fb923c", "#9a3412"],
  NO_MATCHING_RULE: ["#fb7185", "#9f1239"],
};

const OUTCOME_LABELS: Record<string, string> = {
  PRIOR_AUTH_REQUIRED: "Prior auth required",
  NOT_REQUIRED: "No auth needed",
  INCOMPLETE_INFO: "Missing documents",
  NO_MATCHING_RULE: "No matching rule",
};

// Same lifecycle grouping the Intake Queue uses, so the two views agree on
// what each stage means and how cases roll up into it.
const STATUS_STAGES: { label: string; statuses: string[]; color: [string, string] }[] = [
  {
    label: "Awaiting patient",
    statuses: ["AWAITING_INSURANCE_DOCS", "AWAITING_VOICE_NOTE", "AWAITING_DOCUMENTS", "OPEN"],
    color: ["#fbbf24", "#b45309"],
  },
  { label: "Pending approval", statuses: ["PENDING_DOCTOR_APPROVAL"], color: ["#38bdf8", "#0369a1"] },
  { label: "Scheduled", statuses: ["SCHEDULED", "APPROVED"], color: ["#34d399", "#0f766e"] },
  { label: "Denied", statuses: ["DENIED"], color: ["#fb7185", "#9f1239"] },
];

const TOOLTIP_STYLE = {
  background: "rgba(255,255,255,0.96)",
  border: "1px solid #c7e6e0",
  borderRadius: 12,
  boxShadow: "0 12px 24px -8px rgba(15,63,58,0.25)",
  padding: "8px 12px",
};
const TOOLTIP_LABEL_STYLE = { color: "#0f3f3a", fontWeight: 600, fontSize: 12 };
const TOOLTIP_ITEM_STYLE = { color: "#394149", fontSize: 12 };

export function Analytics() {
  const { data: stats, isLoading } = useStats();

  if (isLoading || !stats) {
    return <div className="px-8 py-16 text-center text-sm text-ink-500">Loading analytics...</div>;
  }

  const outcomeData = Object.entries(stats.by_outcome).map(([key, value]) => ({
    name: OUTCOME_LABELS[key] ?? key,
    key,
    value,
  }));
  const outcomeTotal = outcomeData.reduce((s, o) => s + o.value, 0);

  const missingDocsData = Object.entries(stats.missing_documents)
    .map(([doc, count]) => ({ doc: doc.replace(/_/g, " "), count }))
    .sort((a, b) => b.count - a.count);

  const channelData = Object.entries(stats.by_channel).map(([channel, count]) => ({
    channel: channel.toUpperCase(),
    count,
  }));

  const priorAuthRequired = stats.by_outcome?.PRIOR_AUTH_REQUIRED ?? 0;
  const scheduledCount = (stats.by_status?.SCHEDULED ?? 0) + (stats.by_status?.APPROVED ?? 0);

  return (
    <div className="mx-auto max-w-6xl px-8 py-8">
      <header className="mb-6">
        <h1 className="font-serif text-[28px] font-semibold tracking-tight text-ink-900">Analytics</h1>
        <p className="mt-1 text-sm text-ink-600">
          Aggregate view across all prior-authorization cases processed by the system.
        </p>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile label="Total cases" value={stats.total_cases} />
        <StatTile label="Prior auth required" value={priorAuthRequired} accent="amber" />
        <StatTile label="Scheduled / approved" value={scheduledCount} accent="brand" />
        <StatTile
          label="Avg. card extraction confidence"
          value={stats.avg_card_extraction_confidence != null ? `${stats.avg_card_extraction_confidence}%` : "—"}
          accent="default"
        />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Outcomes by prior-auth decision">
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <defs>
                {outcomeData.map((entry) => {
                  const [light, dark] = OUTCOME_COLORS[entry.key] ?? ["#cbd5e1", "#475569"];
                  return (
                    <linearGradient key={entry.key} id={`grad-${entry.key}`} x1="0" y1="0" x2="1" y2="1">
                      <stop offset="0%" stopColor={light} />
                      <stop offset="100%" stopColor={dark} />
                    </linearGradient>
                  );
                })}
                <filter id="pie-shadow" x="-30%" y="-30%" width="160%" height="160%">
                  <feDropShadow dx="0" dy="4" stdDeviation="6" floodColor="#0f3f3a" floodOpacity="0.25" />
                </filter>
              </defs>
              <Pie
                data={outcomeData}
                dataKey="value"
                nameKey="name"
                innerRadius={58}
                outerRadius={96}
                paddingAngle={4}
                cornerRadius={6}
                stroke="#ffffff"
                strokeWidth={2}
                filter="url(#pie-shadow)"
              >
                {outcomeData.map((entry) => (
                  <Cell key={entry.key} fill={`url(#grad-${entry.key})`} />
                ))}
                <Label
                  value={outcomeTotal}
                  position="center"
                  className="font-serif"
                  style={{ fontSize: 30, fontWeight: 700, fill: "#0f3f3a" }}
                />
              </Pie>
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelStyle={TOOLTIP_LABEL_STYLE}
                itemStyle={TOOLTIP_ITEM_STYLE}
                formatter={(value: number) => [`${value} case${value === 1 ? "" : "s"}`, ""]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-1 grid grid-cols-2 gap-2">
            {outcomeData.map((o) => {
              const [light, dark] = OUTCOME_COLORS[o.key] ?? ["#cbd5e1", "#475569"];
              const pct = outcomeTotal ? Math.round((o.value / outcomeTotal) * 100) : 0;
              return (
                <div key={o.key} className="flex items-center gap-2 rounded-lg bg-white/60 px-2 py-1.5">
                  <span
                    className="h-3 w-3 flex-none rounded-full shadow-sm"
                    style={{ background: `linear-gradient(135deg, ${light}, ${dark})` }}
                  />
                  <span className="truncate text-[11px] font-medium text-ink-600">{o.name}</span>
                  <span className="ml-auto flex-none text-[11px] font-bold text-ink-800">{pct}%</span>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel title="Most frequently missing documents">
          {missingDocsData.length === 0 ? (
            <EmptyState text="No missing-document cases yet." />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={missingDocsData} layout="vertical" margin={{ left: 24, right: 28 }}>
                <defs>
                  <linearGradient id="grad-missing" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#fdba74" />
                    <stop offset="100%" stopColor="#c2410c" />
                  </linearGradient>
                  <filter id="bar-shadow-h" x="-10%" y="-40%" width="120%" height="180%">
                    <feDropShadow dx="2" dy="3" stdDeviation="3" floodColor="#9a3412" floodOpacity="0.35" />
                  </filter>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#d9e8e4" horizontal={false} />
                <XAxis type="number" stroke="#717b86" fontSize={12} allowDecimals={false} />
                <YAxis type="category" dataKey="doc" stroke="#4f5861" fontSize={12} width={140} />
                <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} cursor={{ fill: "#e3f1ee" }} />
                <Bar dataKey="count" fill="url(#grad-missing)" radius={[0, 8, 8, 0]} filter="url(#bar-shadow-h)">
                  <LabelList dataKey="count" position="right" style={{ fill: "#0f3f3a", fontWeight: 700, fontSize: 12 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Cases by intake channel">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={channelData} margin={{ top: 24 }}>
              <defs>
                <linearGradient id="grad-channel" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#5eead4" />
                  <stop offset="100%" stopColor="#0f766e" />
                </linearGradient>
                <filter id="bar-shadow-v" x="-40%" y="-10%" width="180%" height="130%">
                  <feDropShadow dx="0" dy="4" stdDeviation="4" floodColor="#0f3f3a" floodOpacity="0.3" />
                </filter>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#d9e8e4" vertical={false} />
              <XAxis dataKey="channel" stroke="#4f5861" fontSize={12} />
              <YAxis stroke="#717b86" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={TOOLTIP_LABEL_STYLE} cursor={{ fill: "#e3f1ee" }} />
              <Bar dataKey="count" fill="url(#grad-channel)" radius={[8, 8, 0, 0]} filter="url(#bar-shadow-v)" maxBarSize={64}>
                <LabelList dataKey="count" position="top" style={{ fill: "#0f3f3a", fontWeight: 700, fontSize: 13 }} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Case lifecycle stage">
          <div className="space-y-4 py-2">
            {STATUS_STAGES.map((stage) => {
              const count = stage.statuses.reduce((sum, s) => sum + (stats.by_status?.[s] ?? 0), 0);
              const [light, dark] = stage.color;
              const pct = stats.total_cases ? (count / stats.total_cases) * 100 : 0;
              return (
                <div key={stage.label}>
                  <div className="flex justify-between text-xs">
                    <span className="font-semibold text-ink-700">{stage.label}</span>
                    <span className="font-bold text-ink-800">{count}</span>
                  </div>
                  <div className="mt-1.5 h-3 overflow-hidden rounded-full bg-ink-100 shadow-[inset_0_1px_2px_rgba(15,63,58,0.15)]">
                    <div
                      className="h-full rounded-full shadow-[0_1px_2px_rgba(0,0,0,0.25),inset_0_1px_0_rgba(255,255,255,0.4)] transition-all duration-500"
                      style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${light}, ${dark})` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="surface-3d rounded-2xl p-5">
      <h3 className="mb-3 text-sm font-semibold text-ink-800">{title}</h3>
      {children}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <div className="flex h-[200px] items-center justify-center text-sm text-ink-500">{text}</div>;
}
