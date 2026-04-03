// FaultRay Chrome Extension — Background Service Worker (Manifest V3)
// Manages auth state, relays API calls, and handles cross-tab messaging.

import {
  getSession,
  setSession,
  clearSession,
  getSetupState,
  setSetupState,
  clearSetupState,
  getConnectedCredentials,
  addConnectedCredential,
  clearTempAwsKeys,
} from "../lib/storage";
import { submitCloudCredentials } from "../lib/api";
import type {
  Message,
  MessageResponse,
  StoredCredentials,
} from "../lib/types";

// ── Message Router ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (
    message: Message,
    _sender: chrome.runtime.MessageSender,
    sendResponse: (response: MessageResponse) => void
  ) => {
    handleMessage(message)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : String(err);
        sendResponse({ ok: false, error: msg });
      });

    // Return true to indicate we'll respond asynchronously
    return true;
  }
);

async function handleMessage(msg: Message): Promise<unknown> {
  switch (msg.type) {
    case "GET_STATE": {
      const [session, credentials, setupState] = await Promise.all([
        getSession(),
        getConnectedCredentials(),
        getSetupState(),
      ]);
      return { session, credentials, setupState };
    }

    case "SET_SESSION": {
      await setSession(msg.payload);
      return null;
    }

    case "CLEAR_SESSION": {
      await clearSession();
      return null;
    }

    case "START_SETUP": {
      const state = {
        provider: msg.payload.provider,
        currentStep: 1,
        completedSteps: [] as number[],
        startedAt: Date.now(),
      };
      await setSetupState(state);
      return state;
    }

    case "STEP_COMPLETED": {
      const current = await getSetupState();
      if (!current) throw new Error("No active setup state");
      const updated = {
        ...current,
        currentStep: msg.payload.step + 1,
        completedSteps: [...current.completedSteps, msg.payload.step],
      };
      await setSetupState(updated);
      return updated;
    }

    case "SUBMIT_KEYS": {
      const session = await getSession();
      if (!session) throw new Error("Not authenticated");

      const setupState = await getSetupState();
      const provider = setupState?.provider ?? "aws";

      const response = await submitCloudCredentials(session, {
        provider,
        access_key_id: msg.payload.keys.accessKeyId,
        secret_access_key: msg.payload.keys.secretAccessKey,
        region: msg.payload.region,
        label: msg.payload.label,
      });

      // Keys submitted — immediately wipe from session storage
      await clearTempAwsKeys();
      await clearSetupState();

      const cred: StoredCredentials = {
        provider,
        region: msg.payload.region,
        label: msg.payload.label,
        connectedAt: Date.now(),
      };
      await addConnectedCredential(cred);

      return { scanUrl: response.scan_url };
    }

    case "OPEN_AWS_CONSOLE": {
      await chrome.tabs.create({ url: msg.payload.url });
      return null;
    }

    case "GET_SETUP_STATE": {
      return getSetupState();
    }

    default:
      throw new Error(`Unknown message type: ${(msg as Message).type}`);
  }
}

// ── Installation ─────────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === "install") {
    // Open the FaultRay website on first install so users can log in
    chrome.tabs.create({ url: "https://faultray.com" });
  }
});

// ── Keep service worker alive during async operations ────────────────────────
// MV3 service workers can be terminated at any time.
// We use chrome.alarms to periodically wake the worker.
chrome.alarms.create("keepalive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((_alarm) => {
  // No-op — just prevents the worker from being garbage collected mid-flow
});
