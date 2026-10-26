import type { ActivityLogEntry, CaseDetail, CaseStatus, CaseSummary, PayerRule, Stats } from "../types/case";
import type { StaffProfile } from "../types/auth";
import { mockCases, mockPayerRules, mockStats, mockCaseDetail, mockStaffDirectory } from "./mockData";
import { evaluateMockRules } from "./mockRules";

/**
 * API base URL for the deployed dashboard_api Lambda. Defaults to the
 * REST API created directly via scripts/deploy_api_gateway.py (bypassing
 * `cdk deploy`, which is deferred - see that script's docstring). Override
 * via VITE_API_BASE_URL at build time, or at runtime in the Settings panel
 * (persisted to localStorage, takes priority over this default).
 */
const LIVE_API_BASE_DEFAULT = "https://b16m4614vd.execute-api.ap-south-1.amazonaws.com/prod";
const ENV_API_BASE = import.meta.env.VITE_API_BASE_URL || LIVE_API_BASE_DEFAULT;

const LS_KEY = "carerelay_api_base";
const LS_MODE_KEY = "carerelay_data_mode";
// Bumped once (v1 -> v2) when the default flipped from "mock" to "live"
// now that a real backend is deployed. Anyone with an OLD stored
// preference (saved back when mock was the only option, or chosen before
// a live API existed) gets reset to the new default once, rather than
// being stuck on a stale choice forever. Bump again if a future default
// change needs the same one-time reset.
const LS_MODE_VERSION_KEY = "carerelay_data_mode_version";
const CURRENT_MODE_VERSION = "2";

export type DataMode = "live" | "mock";

export function getApiBase(): string {
  return (localStorage.getItem(LS_KEY) ?? ENV_API_BASE ?? "").replace(/\/$/, "");
}

export function setApiBase(url: string) {
  localStorage.setItem(LS_KEY, url.trim().replace(/\/$/, ""));
}

export function getDataMode(): DataMode {
  const storedVersion = localStorage.getItem(LS_MODE_VERSION_KEY);
  if (storedVersion !== CURRENT_MODE_VERSION) {
    // Stale or missing preference from before the live API existed -
    // clear it and fall through to the current default below.
    localStorage.removeItem(LS_MODE_KEY);
    localStorage.setItem(LS_MODE_VERSION_KEY, CURRENT_MODE_VERSION);
  } else {
    const stored = localStorage.getItem(LS_MODE_KEY) as DataMode | null;
    if (stored) return stored;
  }
  // Defaults to "live" since LIVE_API_BASE_DEFAULT above always resolves to
  // a real API base URL. Only falls back to mock if that default is ever
  // cleared (e.g. VITE_API_BASE_URL explicitly set to an empty string).
  return getApiBase() ? "live" : "mock";
}

export function setDataMode(mode: DataMode) {
  localStorage.setItem(LS_MODE_KEY, mode);
  localStorage.setItem(LS_MODE_VERSION_KEY, CURRENT_MODE_VERSION);
}

export class ApiError extends Error {
  constructor(message: string, public status?: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase();
  if (!base) {
    throw new ApiError("No API base URL configured. Open Settings to set one, or switch to Mock mode.");
  }
  const res = await fetch(`${base}${path}`, { cache: "no-store", ...init });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(body?.error || `Request failed: ${res.status} ${res.statusText}`, res.status);
  }
  return body as T;
}

function delay<T>(value: T, ms = 220): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}

/**
 * Mirrors _hospital_id() in lambdas/dashboard_api/handler.py: lowercase,
 * all non-alphanumeric characters stripped (no hyphens/spaces). Used in
 * mock mode so hospital scoping behaves identically to the live Lambda.
 */
function slugifyHospital(name: string): string {
  const alnum = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
  return alnum || "defaulthospital";
}

// Session-only store for cases created/updated in mock mode (status
// changes, manually-logged cases) - mockCaseDetail() itself is a pure
// function derived from the static mockData.ts fixtures, so anything
// mutated at runtime is tracked here instead and checked first.
const mockCaseDetailOverrides = new Map<string, CaseDetail>();

function computeMockStats(cases: CaseSummary[]): Stats {
  const count = <T extends string>(key: (c: CaseSummary) => T) =>
    cases.reduce<Record<string, number>>((acc, c) => {
      const k = key(c);
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    }, {});

  const missingDocs: Record<string, number> = {};
  for (const c of cases) {
    for (const doc of c.verification.missing_documents) {
      missingDocs[doc] = (missingDocs[doc] ?? 0) + 1;
    }
  }

  const confidences = cases
    .map((c) => c.extracted_card.confidence)
    .filter((v): v is number => v != null);

  return {
    total_cases: cases.length,
    by_outcome: count((c) => c.verification.outcome),
    by_status: count((c) => c.status),
    by_channel: count((c) => c.channel),
    missing_documents: missingDocs,
    payer_simulated_calls: cases.filter((c) => c.verification.payer_simulated).length,
    payer_eligible_calls: cases.filter((c) => c.verification.payer_eligible).length,
    avg_card_extraction_confidence: confidences.length
      ? Math.round((confidences.reduce((s, v) => s + v, 0) / confidences.length) * 10) / 10
      : null,
  };
}

export interface DateRange {
  from?: string; // YYYY-MM-DD, inclusive
  to?: string; // YYYY-MM-DD, inclusive
}

function dateRangeQuery(range?: DateRange): string {
  if (!range || (!range.from && !range.to)) return "";
  const params = new URLSearchParams();
  if (range.from) params.set("from", range.from);
  if (range.to) params.set("to", range.to);
  return `?${params.toString()}`;
}

function inRange(createdAt: string, range?: DateRange): boolean {
  if (!range || (!range.from && !range.to)) return true;
  const lo = range.from ?? "0000-00-00";
  const hi = range.to ? `${range.to}T23:59:59.999999Z` : "9999-99-99";
  return createdAt >= lo && createdAt <= hi;
}

export const api = {
  async listCases(range?: DateRange): Promise<{ cases: CaseSummary[]; count: number }> {
    if (getDataMode() === "mock") {
      const filtered = mockCases.filter((c) => inRange(c.created_at, range));
      return delay({ cases: filtered, count: filtered.length });
    }
    return request(`/cases${dateRangeQuery(range)}`);
  },

  async getCase(caseId: string): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const detail = mockCaseDetailOverrides.get(caseId) ?? mockCaseDetail(caseId);
      if (!detail) throw new ApiError("Case not found", 404);
      return delay({ case: detail });
    }
    return request(`/cases/${encodeURIComponent(caseId)}`);
  },

  async createCase(input: {
    patient_name: string;
    cpt_code: string;
    procedure_name: string;
    payer_id: string;
    channel: "whatsapp" | "rcs" | "sms";
    patient_phone_masked?: string;
    actor?: string;
    hospital_id?: string | null;
    hospital_name?: string | null;
  }): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const verification = evaluateMockRules(input.payer_id, input.cpt_code);
      const status: CaseStatus = verification.missing_documents.length
        ? "AWAITING_DOCUMENTS"
        : !verification.requires_prior_auth
        ? "APPROVED"
        : "OPEN";
      const now = new Date().toISOString();
      const caseId = `case-${Math.random().toString(16).slice(2, 10)}`;
      const activityLog: ActivityLogEntry[] = [
        {
          timestamp: now,
          event: "CREATED",
          actor: `staff:${input.actor || "staff"}`,
          detail: `Case manually logged via console (${input.channel}).`,
        },
      ];
      const summary: CaseSummary = {
        case_id: caseId,
        created_at: now,
        status,
        channel: input.channel,
        hospital_id: input.hospital_id ?? null,
        hospital_name: input.hospital_name ?? null,
        patient_name: input.patient_name,
        patient_phone_masked: input.patient_phone_masked || "***0000",
        cpt_code: input.cpt_code,
        procedure_name: input.procedure_name,
        payer_id: input.payer_id,
        extracted_card: {},
        verification,
      };
      mockCases.unshift(summary);
      const detail: CaseDetail = {
        ...summary,
        messages: {
          patient_message_body: "",
          patient_message_buttons: [],
          doctor_card_body: "",
          doctor_card_buttons: [],
          audit_headline: "",
          audit_detail_lines: [],
        },
        perceived_facts: [],
        narration: null,
        photo_url: null,
        audio_url: null,
        agent_trace: [],
        activity_log: activityLog,
        // Manually-logged cases have no WhatsApp thread behind them unless
        // a real phone number was provided - mirrors the backend's
        // _handle_create_case (patient_phone is optional there too).
        can_message_patient: false,
      };
      mockCaseDetailOverrides.set(caseId, detail);
      return delay({ case: detail });
    }
    return request("/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },

  async startFollowup(input: {
    patient_name: string;
    patient_phone: string;
    procedure_name: string;
    appointment_datetime: string;
    has_insurance: boolean;
    cpt_code?: string;
    payer_id?: string;
    actor?: string;
    hospital_id?: string | null;
    hospital_name?: string | null;
  }): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const phoneDigits = input.patient_phone.replace(/[^0-9]/g, "");
      const status: CaseStatus = input.has_insurance ? "AWAITING_INSURANCE_DOCS" : "AWAITING_VOICE_NOTE";
      const now = new Date().toISOString();
      const caseId = `case-${Math.random().toString(16).slice(2, 10)}`;
      const summary: CaseSummary = {
        case_id: caseId,
        created_at: now,
        status,
        channel: "whatsapp",
        flow: input.has_insurance ? "followup_insured" : "followup_selfpay",
        has_insurance: input.has_insurance,
        appointment_datetime: input.appointment_datetime,
        appointment_released: false,
        hospital_id: input.hospital_id ?? null,
        hospital_name: input.hospital_name ?? null,
        patient_name: input.patient_name,
        patient_phone_masked: phoneDigits ? `***${phoneDigits.slice(-4)}` : "***0000",
        cpt_code: input.cpt_code ?? "",
        procedure_name: input.procedure_name,
        payer_id: input.payer_id ?? "",
        extracted_card: {},
        verification: {
          outcome: "NO_MATCHING_RULE",
          requires_prior_auth: false,
          missing_documents: [],
          matched_rule_id: null,
          rationale: "",
          payer_simulated: false,
          payer_eligible: null,
          approval_code: null,
        },
      };
      mockCases.unshift(summary);
      const detail: CaseDetail = {
        ...summary,
        messages: {
          patient_message_body: "", patient_message_buttons: [],
          doctor_card_body: "", doctor_card_buttons: [],
          audit_headline: "", audit_detail_lines: [],
        },
        perceived_facts: [],
        narration: null,
        photo_url: null,
        audio_url: null,
        agent_trace: [],
        activity_log: [{
          timestamp: now,
          event: "FOLLOWUP_INITIATED",
          actor: `staff:${input.actor || "staff"}`,
          detail: `Follow-up started for a ${input.has_insurance ? "insured" : "self-pay"} patient. Intended appointment ${input.appointment_datetime} (withheld).`,
        }],
        can_message_patient: true,
      };
      mockCaseDetailOverrides.set(caseId, detail);
      return delay({ case: detail });
    }
    return request("/followups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },

  async updateCaseStatus(
    caseId: string,
    input: { status: CaseStatus; actor?: string; note?: string }
  ): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const summary = mockCases.find((c) => c.case_id === caseId);
      if (!summary) throw new ApiError("Case not found", 404);
      const oldStatus = summary.status;
      summary.status = input.status;

      const existing = mockCaseDetailOverrides.get(caseId) ?? mockCaseDetail(caseId);
      const activityLog = [...(existing?.activity_log ?? [])];
      activityLog.push({
        timestamp: new Date().toISOString(),
        event: "STATUS_CHANGED",
        actor: `staff:${input.actor || "staff"}`,
        detail: `Status changed ${oldStatus} -> ${input.status}` + (input.note ? ` (${input.note})` : ""),
      });
      const updated: CaseDetail = { ...(existing as CaseDetail), ...summary, activity_log: activityLog };
      mockCaseDetailOverrides.set(caseId, updated);
      return delay({ case: updated });
    }
    return request(`/cases/${encodeURIComponent(caseId)}/status`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },

  async sendMessage(caseId: string, input: { text: string; actor?: string }): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const summary = mockCases.find((c) => c.case_id === caseId);
      if (!summary) throw new ApiError("Case not found", 404);

      const existing = mockCaseDetailOverrides.get(caseId) ?? mockCaseDetail(caseId);
      if (!existing?.can_message_patient && existing?.channel !== "whatsapp") {
        throw new ApiError("This case has no WhatsApp thread to reply to.", 400);
      }
      const activityLog = [...(existing?.activity_log ?? [])];
      activityLog.push({
        timestamp: new Date().toISOString(),
        event: "STAFF_MESSAGE_SENT",
        actor: `staff:${input.actor || "staff"}`,
        detail: `Sent a WhatsApp message to the patient: "${input.text.slice(0, 200)}"`,
      });
      const updated: CaseDetail = { ...(existing as CaseDetail), activity_log: activityLog };
      mockCaseDetailOverrides.set(caseId, updated);
      return delay({ case: updated });
    }
    return request(`/cases/${encodeURIComponent(caseId)}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },

  async listPayerRules(): Promise<{ rules: PayerRule[] }> {
    if (getDataMode() === "mock") return delay({ rules: mockPayerRules });
    return request("/payer-rules");
  },

  async createPayerRule(input: {
    payer_id: string;
    cpt_code: string;
    procedure_name: string;
    requires_prior_auth: boolean;
    required_documents: string[];
    rule_id: string;
    notes?: string;
  }): Promise<{ rule: PayerRule }> {
    if (getDataMode() === "mock") {
      const exists = mockPayerRules.some((r) => r.payer_id === input.payer_id && r.cpt_code === input.cpt_code);
      if (exists) throw new ApiError("A rule for this payer + CPT code already exists.", 409);
      const rule: PayerRule = {
        payer_id: input.payer_id,
        cpt_code: input.cpt_code,
        procedure_name: input.procedure_name,
        requires_prior_auth: input.requires_prior_auth,
        required_documents: input.required_documents,
        rule_id: input.rule_id,
        notes: input.notes || "",
      };
      mockPayerRules.push(rule);
      return delay({ rule });
    }
    return request("/payer-rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
  },

  async getStats(range?: DateRange): Promise<Stats> {
    if (getDataMode() === "mock") {
      const filtered = mockCases.filter((c) => inRange(c.created_at, range));
      if (!range || (!range.from && !range.to)) return delay(mockStats);
      return delay(computeMockStats(filtered));
    }
    return request(`/stats${dateRangeQuery(range)}`);
  },

  async signup(input: {
    username: string;
    password: string;
    display_name: string;
    hospital_name: string;
    hospital_address: string;
    hospital_email: string;
    hospital_phone: string;
    role?: string;
  }): Promise<{ profile: StaffProfile }> {
    if (getDataMode() === "mock") {
      const hospitalId = slugifyHospital(input.hospital_name);
      const exists = mockStaffDirectory.some(
        (u) => u.hospital_id === hospitalId && u.username === input.username.toLowerCase()
      );
      if (exists) throw new ApiError("That username is already registered at this hospital.", 409);
      if (input.password.length < 8) throw new ApiError("Password must be at least 8 characters.", 400);
      const entry = {
        username: input.username.toLowerCase(),
        password: input.password,
        display_name: input.display_name,
        role: input.role || "Clinic Staff",
        hospital_id: hospitalId,
        hospital_name: input.hospital_name.trim(),
        hospital_address: input.hospital_address.trim(),
        hospital_email: input.hospital_email.trim().toLowerCase(),
        hospital_phone: input.hospital_phone.trim(),
      };
      mockStaffDirectory.push(entry);
      return delay({
        profile: {
          username: entry.username,
          display_name: entry.display_name,
          role: entry.role,
          hospital_id: entry.hospital_id,
          hospital_name: entry.hospital_name,
          hospital_address: entry.hospital_address,
          hospital_email: entry.hospital_email,
          hospital_phone: entry.hospital_phone,
        },
      });
    }
    return request("/auth/signup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
  },

  async login(input: { username: string; password: string; hospital_id: string }): Promise<{ profile: StaffProfile }> {
    if (getDataMode() === "mock") {
      const hospitalId = input.hospital_id.trim().toLowerCase();
      const match = mockStaffDirectory.find(
        (u) =>
          u.hospital_id === hospitalId &&
          u.username === input.username.trim().toLowerCase() &&
          u.password === input.password
      );
      if (!match) throw new ApiError("Invalid hospital ID, username, or password.", 401);
      return delay({
        profile: {
          username: match.username,
          display_name: match.display_name,
          role: match.role,
          hospital_id: match.hospital_id,
          hospital_name: match.hospital_name,
          hospital_address: match.hospital_address,
          hospital_email: match.hospital_email,
          hospital_phone: match.hospital_phone,
        },
      });
    }
    return request("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
  },
};
