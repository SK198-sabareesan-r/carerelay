import type { DateRange } from "./api";

export function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Default Intake Queue filter: past 7 days including today (UTC calendar days). */
export function defaultDateRange(): DateRange {
  const to = new Date();
  const from = new Date();
  from.setDate(to.getDate() - 6);
  return { from: toDateInput(from), to: toDateInput(to) };
}
