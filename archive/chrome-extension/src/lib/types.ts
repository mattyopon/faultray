// FaultRay Chrome Extension — Type Definitions
// All types are strictly typed for maximum safety

export type CloudProvider = "aws" | "gcp" | "azure";

export type SetupStep = {
  step: number;
  title: string;
  url?: string;
  instruction: string;
  highlight?: string;
  action?: "capture_keys" | "navigate";
};

export type SetupState = {
  provider: CloudProvider;
  currentStep: number;
  completedSteps: number[];
  startedAt: number;
};

export type FaultRaySession = {
  token: string;
  email: string;
  userId: string;
  expiresAt: number;
};

export type StoredCredentials = {
  provider: CloudProvider;
  region: string;
  label: string;
  connectedAt: number;
};

export type AppStorage = {
  session: FaultRaySession | null;
  connectedCredentials: StoredCredentials[];
  setupState: SetupState | null;
};

// Transient — session-only, never persisted to local storage
export type TemporaryAWSKeys = {
  accessKeyId: string;
  secretAccessKey: string;
};

export type ConnectCredentialsRequest = {
  provider: CloudProvider;
  access_key_id: string;
  secret_access_key: string;
  region: string;
  label: string;
};

export type ConnectCredentialsResponse = {
  status: "connected";
  scan_url: string;
};

// Messages between popup, content script, and service worker
export type Message =
  | { type: "GET_STATE" }
  | { type: "SET_SESSION"; payload: FaultRaySession }
  | { type: "CLEAR_SESSION" }
  | { type: "START_SETUP"; payload: { provider: CloudProvider } }
  | { type: "STEP_COMPLETED"; payload: { step: number } }
  | { type: "SUBMIT_KEYS"; payload: { keys: TemporaryAWSKeys; region: string; label: string } }
  | { type: "GET_SETUP_STATE" }
  | { type: "OPEN_AWS_CONSOLE"; payload: { url: string } }
  | { type: "KEYS_SUBMITTED_OK"; payload: { scanUrl: string } }
  | { type: "ERROR"; payload: { message: string } };

export type MessageResponse =
  | { ok: true; data?: unknown }
  | { ok: false; error: string };
