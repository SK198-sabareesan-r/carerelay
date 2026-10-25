import type { CaseDetail, CaseSummary, PayerRule, Stats } from "../types/case";
import type { StaffProfile } from "../types/auth";
import { mockCases, mockPayerRules, mockStats, mockCaseDetail, mockStaffDirectory } from "./mockData";

/**
 * API base URL for the deployed dashboard_api Lambda (the IncidentsApiUrl /
 * DashboardApiUrl CDK output, e.g. https://xxxx.execute-api.<region>.amazonaws.com/prod).
 * Set via VITE_API_BASE_URL at build time, or configure at runtime in the
 * Settings panel (persisted to localStorage) - see useApiBase().
 */
const ENV_API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const LS_KEY = "carerelay_api_base";
const LS_MODE_KEY = "carerelay_data_mode";

export type DataMode = "live" | "mock";

export function getApiBase(): string {
  return (localStorage.getItem(LS_KEY) ?? ENV_API_BASE ?? "").replace(/\/$/, "");
}

export function setApiBase(url: string) {
  localStorage.setItem(LS_KEY, url.trim().replace(/\/$/, ""));
}

export function getDataMode(): DataMode {
  const stored = localStorage.getItem(LS_MODE_KEY) as DataMode | null;
  if (stored) return stored;
  // Default to mock mode if no API base is configured, so the app is
  // demo-able with zero setup.
  return getApiBase() ? "live" : "mock";
}

export function setDataMode(mode: DataMode) {
  localStorage.setItem(LS_MODE_KEY, mode);
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

export const api = {
  async listCases(): Promise<{ cases: CaseSummary[]; count: number }> {
    if (getDataMode() === "mock") return delay({ cases: mockCases, count: mockCases.length });
    return request("/cases");
  },

  async getCase(caseId: string): Promise<{ case: CaseDetail }> {
    if (getDataMode() === "mock") {
      const detail = mockCaseDetail(caseId);
      if (!detail) throw new ApiError("Case not found", 404);
      return delay({ case: detail });
    }
    return request(`/cases/${encodeURIComponent(caseId)}`);
  },

  async listPayerRules(): Promise<{ rules: PayerRule[] }> {
    if (getDataMode() === "mock") return delay({ rules: mockPayerRules });
    return request("/payer-rules");
  },

  async getStats(): Promise<Stats> {
    if (getDataMode() === "mock") return delay(mockStats);
    return request("/stats");
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
