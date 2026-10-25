import clsx from "clsx";

export function StatTile({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: "default" | "amber" | "brand" | "rose";
}) {
  const accentClass: Record<string, string> = {
    default: "text-ink-800",
    amber: "text-amber-700",
    brand: "text-brand-700",
    rose: "text-rose-700",
  };
  const glowClass: Record<string, string> = {
    default: "from-ink-100/60",
    amber: "from-amber-200/50",
    brand: "from-brand-200/60",
    rose: "from-rose-200/50",
  };
  return (
    <div className="surface-3d relative overflow-hidden rounded-2xl px-4 py-4">
      <div
        className={clsx(
          "pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full bg-gradient-to-br to-transparent blur-xl",
          glowClass[accent ?? "default"]
        )}
      />
      <div className={clsx("relative font-serif text-[28px] font-semibold leading-none tabular-nums", accentClass[accent ?? "default"])}>
        {value}
      </div>
      <div className="relative mt-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-500">{label}</div>
    </div>
  );
}
