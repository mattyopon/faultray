// FaultRay Chrome Extension — Chrome Storage Manager
// Wraps chrome.storage.local (persistent) and chrome.storage.session (transient)

import type {
  AppStorage,
  FaultRaySession,
  StoredCredentials,
  SetupState,
  TemporaryAWSKeys,
} from "./types";

const STORAGE_KEYS = {
  SESSION: "faultray_session",
  CONNECTED_CREDENTIALS: "faultray_credentials",
  SETUP_STATE: "faultray_setup_state",
  // Session-only — cleared when browser closes
  TEMP_AWS_KEYS: "faultray_temp_aws_keys",
} as const;

// ── Session (FaultRay auth) ─────────────────────────────────────────────────

export async function getSession(): Promise<FaultRaySession | null> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.SESSION);
  const session = result[STORAGE_KEYS.SESSION] as FaultRaySession | undefined;
  if (!session) return null;
  // Treat expired sessions as absent
  if (session.expiresAt < Date.now()) {
    await clearSession();
    return null;
  }
  return session;
}

export async function setSession(session: FaultRaySession): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.SESSION]: session });
}

export async function clearSession(): Promise<void> {
  await chrome.storage.local.remove(STORAGE_KEYS.SESSION);
}

// ── Connected Credentials ───────────────────────────────────────────────────

export async function getConnectedCredentials(): Promise<StoredCredentials[]> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.CONNECTED_CREDENTIALS);
  return (result[STORAGE_KEYS.CONNECTED_CREDENTIALS] as StoredCredentials[]) ?? [];
}

export async function addConnectedCredential(cred: StoredCredentials): Promise<void> {
  const existing = await getConnectedCredentials();
  // Replace if same provider+label already exists
  const filtered = existing.filter(
    (c) => !(c.provider === cred.provider && c.label === cred.label)
  );
  await chrome.storage.local.set({
    [STORAGE_KEYS.CONNECTED_CREDENTIALS]: [...filtered, cred],
  });
}

// ── Setup State ─────────────────────────────────────────────────────────────

export async function getSetupState(): Promise<SetupState | null> {
  const result = await chrome.storage.local.get(STORAGE_KEYS.SETUP_STATE);
  return (result[STORAGE_KEYS.SETUP_STATE] as SetupState | undefined) ?? null;
}

export async function setSetupState(state: SetupState): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEYS.SETUP_STATE]: state });
}

export async function clearSetupState(): Promise<void> {
  await chrome.storage.local.remove(STORAGE_KEYS.SETUP_STATE);
}

// ── Temporary AWS Keys (session-scoped) ─────────────────────────────────────
// Uses chrome.storage.session so keys are wiped when browser is closed.

export async function storeTempAwsKeys(keys: TemporaryAWSKeys): Promise<void> {
  await chrome.storage.session.set({ [STORAGE_KEYS.TEMP_AWS_KEYS]: keys });
}

export async function getTempAwsKeys(): Promise<TemporaryAWSKeys | null> {
  const result = await chrome.storage.session.get(STORAGE_KEYS.TEMP_AWS_KEYS);
  return (result[STORAGE_KEYS.TEMP_AWS_KEYS] as TemporaryAWSKeys | undefined) ?? null;
}

export async function clearTempAwsKeys(): Promise<void> {
  await chrome.storage.session.remove(STORAGE_KEYS.TEMP_AWS_KEYS);
}

// ── Full state snapshot ─────────────────────────────────────────────────────

export async function getAppStorage(): Promise<AppStorage> {
  const [session, connectedCredentials, setupState] = await Promise.all([
    getSession(),
    getConnectedCredentials(),
    getSetupState(),
  ]);
  return { session, connectedCredentials, setupState };
}
