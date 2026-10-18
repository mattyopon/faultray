// FaultRay Chrome Extension — FaultRay API Client
// NOTE: The /api/cloud-credentials endpoint does not yet exist on the backend.
// This client is ready to call it once the backend implements it.

import type {
  ConnectCredentialsRequest,
  ConnectCredentialsResponse,
  FaultRaySession,
} from "./types";

const FAULTRAY_BASE = "https://faultray.com";
const LOGIN_URL = `${FAULTRAY_BASE}/auth/signin`;

// ── Auth ────────────────────────────────────────────────────────────────────

/**
 * Opens the FaultRay login page in a new tab.
 * The content script on faultray.com will capture the session token after login
 * and relay it to the service worker via a message.
 */
export function openLoginPage(): void {
  chrome.tabs.create({ url: LOGIN_URL });
}

// ── Cloud Credentials ───────────────────────────────────────────────────────

/**
 * POST /api/cloud-credentials
 * Sends cloud credentials to FaultRay.
 * Throws on network error or non-2xx response.
 */
export async function submitCloudCredentials(
  session: FaultRaySession,
  body: ConnectCredentialsRequest
): Promise<ConnectCredentialsResponse> {
  const res = await fetch(`${FAULTRAY_BASE}/api/cloud-credentials`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.token}`,
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`FaultRay API error ${res.status}: ${text}`);
  }

  return res.json() as Promise<ConnectCredentialsResponse>;
}

// ── Session capture helper ───────────────────────────────────────────────────

/**
 * Parses a FaultRay session from cookies available to the extension.
 * Returns null if no valid session is found.
 * This is called from the content script on faultray.com.
 */
export function parseFaultRaySessionFromCookie(
  cookieHeader: string
): Pick<FaultRaySession, "token"> | null {
  const match = cookieHeader.match(/faultray_token=([^;]+)/);
  if (!match?.[1]) return null;
  return { token: match[1] };
}
