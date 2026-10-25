import type { StaffProfile } from "../types/auth";

/**
 * Client-side session storage for the signed-in staff profile.
 *
 * The actual credential check happens server-side (dashboard_api
 * /auth/login, backed by StaffUsersTable with PBKDF2-hashed passwords - see
 * lambdas/dashboard_api/handler.py). This module only persists the
 * resulting profile in the browser for the duration of the session; it
 * does not issue or verify any token. A real deployment should replace
 * this with a proper session/JWT and a managed identity provider
 * (Cognito/SSO) - see docs/DASHBOARD.md.
 */
const LS_SESSION_KEY = "carerelay_session";

export interface Session extends StaffProfile {
  signedInAt: string;
}

export function getSession(): Session | null {
  const raw = localStorage.getItem(LS_SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export function isSignedIn(): boolean {
  return getSession() !== null;
}

export function setSession(profile: StaffProfile): void {
  const session: Session = { ...profile, signedInAt: new Date().toISOString() };
  localStorage.setItem(LS_SESSION_KEY, JSON.stringify(session));
}

export function signOut(): void {
  localStorage.removeItem(LS_SESSION_KEY);
}
