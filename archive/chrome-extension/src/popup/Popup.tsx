// FaultRay Chrome Extension — Main Popup UI
// React 18 + inline Tailwind-inspired styles (no Tailwind build required).
// Dark theme matching FaultRay's #0a0e1a design system.

import { useEffect, useState, useCallback } from "react";
import type { FaultRaySession, StoredCredentials, SetupState, CloudProvider } from "../lib/types";

// ── Types ────────────────────────────────────────────────────────────────────

interface AppState {
  session: FaultRaySession | null;
  credentials: StoredCredentials[];
  setupState: SetupState | null;
  loading: boolean;
  error: string | null;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(ts: number): string {
  return new Date(ts).toLocaleDateString("ja-JP", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function providerLabel(p: CloudProvider): string {
  return { aws: "🟠 AWS", gcp: "🔵 GCP", azure: "⬜ Azure" }[p];
}

async function sendMsg(msg: Record<string, unknown>): Promise<{ ok: boolean; data?: unknown; error?: string }> {
  return chrome.runtime.sendMessage(msg) as Promise<{ ok: boolean; data?: unknown; error?: string }>;
}

// ── Styles (design tokens matching FaultRay) ─────────────────────────────────

const css = {
  container: {
    background: "#0a0e1a",
    color: "#e2e8f0",
    width: "360px",
    minHeight: "200px",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  } satisfies React.CSSProperties,
  header: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "14px 16px",
    borderBottom: "1px solid #1e293b",
    background: "#0d1220",
  } satisfies React.CSSProperties,
  title: {
    fontSize: "14px",
    fontWeight: 600 as const,
    color: "#e2e8f0",
  } satisfies React.CSSProperties,
  subtitle: {
    fontSize: "11px",
    color: "#64748b",
  } satisfies React.CSSProperties,
  body: {
    padding: "16px",
  } satisfies React.CSSProperties,
  divider: {
    height: "1px",
    background: "#1e293b",
    margin: "12px 0",
  } satisfies React.CSSProperties,
  label: {
    fontSize: "11px",
    color: "#64748b",
    textTransform: "uppercase" as const,
    letterSpacing: "0.05em",
    marginBottom: "8px",
  } satisfies React.CSSProperties,
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 12px",
    background: "#0d1220",
    borderRadius: "8px",
    border: "1px solid #1e293b",
    marginBottom: "12px",
  } satisfies React.CSSProperties,
  dot: (connected: boolean): React.CSSProperties => ({
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: connected ? "#4ade80" : "#475569",
    flexShrink: 0,
  }),
  primaryBtn: {
    width: "100%",
    background: "#FFD700",
    color: "#0a0e1a",
    border: "none",
    borderRadius: "8px",
    padding: "11px 16px",
    fontSize: "13px",
    fontWeight: 700 as const,
    cursor: "pointer",
    transition: "background 0.15s",
    marginBottom: "8px",
  } satisfies React.CSSProperties,
  secondaryBtn: {
    width: "100%",
    background: "transparent",
    color: "#94a3b8",
    border: "1px solid #1e293b",
    borderRadius: "8px",
    padding: "10px 16px",
    fontSize: "13px",
    cursor: "pointer",
    transition: "border-color 0.15s, color 0.15s",
    marginBottom: "8px",
    textAlign: "left" as const,
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } satisfies React.CSSProperties,
  credBadge: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 12px",
    background: "#0d1220",
    borderRadius: "6px",
    border: "1px solid #1e293b",
    marginBottom: "6px",
    fontSize: "12px",
  } satisfies React.CSSProperties,
  progressBar: (pct: number): React.CSSProperties => ({
    height: "3px",
    background: `linear-gradient(90deg, #FFD700 ${pct}%, #1e293b ${pct}%)`,
    borderRadius: "2px",
    marginBottom: "12px",
  }),
  stepRow: (active: boolean, done: boolean): React.CSSProperties => ({
    display: "flex",
    gap: "8px",
    alignItems: "flex-start",
    padding: "4px 0",
    color: active ? "#FFD700" : done ? "#4ade80" : "#475569",
    fontWeight: active ? 600 : 400,
    fontSize: "12px",
  }),
  errorBox: {
    background: "#1a0a0a",
    border: "1px solid #ff6b6b40",
    borderRadius: "8px",
    padding: "10px 12px",
    color: "#ff6b6b",
    fontSize: "12px",
    marginBottom: "12px",
  } satisfies React.CSSProperties,
  warningBox: {
    background: "#1a1200",
    border: "1px solid #fbbf2440",
    borderRadius: "8px",
    padding: "10px 12px",
    color: "#fbbf24",
    fontSize: "12px",
    marginBottom: "12px",
  } satisfies React.CSSProperties,
} as const;

// ── FaultRay SVG Logo (inline, no external asset needed in popup) ────────────

function FaultRayLogo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="100" height="100" rx="20" fill="#0a0e1a" />
      <g opacity="0.2">
        <line x1="25" y1="0" x2="25" y2="100" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="50" y1="0" x2="50" y2="100" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="75" y1="0" x2="75" y2="100" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="0" y1="25" x2="100" y2="25" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="0" y1="50" x2="100" y2="50" stroke="#e2e8f0" strokeWidth="2" />
        <line x1="0" y1="75" x2="100" y2="75" stroke="#e2e8f0" strokeWidth="2" />
      </g>
      <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" strokeWidth="12" opacity="0.15" strokeLinecap="round" />
      <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" strokeWidth="4" strokeLinecap="round" />
      <line x1="32" y1="32" x2="85" y2="15" stroke="#FFD700" strokeWidth="2" opacity="0.4" strokeLinecap="round" />
    </svg>
  );
}

// ── Screen: Not connected ────────────────────────────────────────────────────

function NotConnectedScreen({ onLogin }: { onLogin: () => void }) {
  return (
    <div style={css.body}>
      <div style={css.statusRow}>
        <span style={css.dot(false)} />
        <span style={{ fontSize: "13px", color: "#94a3b8" }}>未接続</span>
      </div>
      <p style={{ fontSize: "12px", color: "#64748b", marginBottom: "16px", lineHeight: 1.6 }}>
        FaultRayアカウントにログインして、AWSなどのクラウド環境の接続セットアップを開始してください。
      </p>
      <button style={css.primaryBtn} onClick={onLogin}>
        FaultRayにログイン →
      </button>
    </div>
  );
}

// ── Screen: Connected (dashboard) ────────────────────────────────────────────

interface ConnectedScreenProps {
  session: FaultRaySession;
  credentials: StoredCredentials[];
  onSetup: (provider: CloudProvider) => void;
  onLogout: () => void;
}

function ConnectedScreen({ session, credentials, onSetup, onLogout }: ConnectedScreenProps) {
  const providers: Array<{ id: CloudProvider; label: string; available: boolean }> = [
    { id: "aws", label: "🟠 AWS セットアップ開始", available: true },
    { id: "gcp", label: "🔵 GCP セットアップ開始", available: false },
    { id: "azure", label: "⬜ Azure セットアップ開始", available: false },
  ];

  return (
    <div style={css.body}>
      {/* Status */}
      <div style={css.statusRow}>
        <span style={css.dot(true)} />
        <span style={{ fontSize: "13px", color: "#e2e8f0", flexGrow: 1 }}>
          {session.email}
        </span>
        <button
          onClick={onLogout}
          style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: "12px" }}
        >
          ログアウト
        </button>
      </div>

      {/* Cloud setup */}
      <div style={css.label}>クラウドセットアップ</div>
      {providers.map((p) => (
        <button
          key={p.id}
          style={{
            ...css.secondaryBtn,
            opacity: p.available ? 1 : 0.4,
            cursor: p.available ? "pointer" : "not-allowed",
          }}
          onClick={() => p.available && onSetup(p.id)}
          disabled={!p.available}
          title={p.available ? undefined : "近日公開予定"}
        >
          {p.label}
          {!p.available && <span style={{ fontSize: "10px", color: "#475569" }}> (近日公開)</span>}
        </button>
      ))}

      {/* Connected credentials */}
      {credentials.length > 0 && (
        <>
          <div style={{ ...css.divider }} />
          <div style={css.label}>接続済み</div>
          {credentials.map((c, i) => (
            <div key={i} style={css.credBadge}>
              <span style={{ color: "#4ade80" }}>✅</span>
              <span style={{ color: "#e2e8f0", flexGrow: 1 }}>
                {providerLabel(c.provider)} — {c.region}
              </span>
              <span style={{ color: "#64748b", fontSize: "11px" }}>{formatDate(c.connectedAt)}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Screen: AWS Setup in progress ────────────────────────────────────────────

const AWS_STEP_TITLES = [
  "IAMダッシュボードに移動",
  "ユーザーを作成",
  "ReadOnlyAccessポリシーを付与",
  "アクセスキーを作成",
  "キーをFaultRayに送信",
];
const TOTAL_STEPS = AWS_STEP_TITLES.length;

interface SetupScreenProps {
  setupState: SetupState;
  onOpenConsole: (url: string) => void;
  onCancel: () => void;
}

const AWS_STEP_URLS: Record<number, string> = {
  1: "https://console.aws.amazon.com/iam/",
  2: "https://console.aws.amazon.com/iam/home#/users/create",
};

function SetupScreen({ setupState, onOpenConsole, onCancel }: SetupScreenProps) {
  const { currentStep, completedSteps } = setupState;
  const pct = Math.round(((currentStep - 1) / TOTAL_STEPS) * 100);
  const currentUrl = AWS_STEP_URLS[currentStep];

  return (
    <div style={css.body}>
      <div style={{ fontSize: "13px", color: "#64748b", marginBottom: "4px" }}>
        AWS セットアップ
      </div>
      <div style={{ fontSize: "15px", fontWeight: 600, color: "#FFD700", marginBottom: "12px" }}>
        Step {currentStep} / {TOTAL_STEPS}
      </div>

      {/* Progress */}
      <div style={css.progressBar(pct)} />

      {/* Step list */}
      <div
        style={{
          border: "1px solid #1e293b",
          borderRadius: "8px",
          padding: "12px",
          marginBottom: "16px",
        }}
      >
        {AWS_STEP_TITLES.map((title, i) => {
          const stepNum = i + 1;
          const done = completedSteps.includes(stepNum);
          const active = stepNum === currentStep;
          const icon = done ? "✅" : active ? "→" : "⬜";
          return (
            <div key={stepNum} style={css.stepRow(active, done)}>
              <span style={{ flexShrink: 0 }}>{icon}</span>
              <span>Step {stepNum}: {title}</span>
            </div>
          );
        })}
      </div>

      <div style={css.warningBox}>
        ⚠️ ReadOnlyAccessポリシーのみを推奨します。書き込み権限を付与しないでください。
      </div>

      {currentUrl && (
        <button style={css.primaryBtn} onClick={() => onOpenConsole(currentUrl)}>
          AWSコンソールを開く →
        </button>
      )}

      <p style={{ fontSize: "11px", color: "#64748b", lineHeight: 1.6, marginBottom: "12px" }}>
        AWSコンソールのページでガイドパネルが自動表示されます。パネルの指示に従ってセットアップを完了してください。
      </p>

      <button
        style={{ ...css.secondaryBtn, justifyContent: "center", marginBottom: 0 }}
        onClick={onCancel}
      >
        キャンセル
      </button>
    </div>
  );
}

// ── Main Popup Component ──────────────────────────────────────────────────────

export function Popup() {
  const [state, setState] = useState<AppState>({
    session: null,
    credentials: [],
    setupState: null,
    loading: true,
    error: null,
  });

  const loadState = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    const res = await sendMsg({ type: "GET_STATE" });
    if (!res.ok) {
      setState((prev) => ({ ...prev, loading: false, error: res.error ?? "不明なエラー" }));
      return;
    }
    const data = res.data as {
      session: FaultRaySession | null;
      credentials: StoredCredentials[];
      setupState: SetupState | null;
    };
    setState({
      session: data.session,
      credentials: data.credentials ?? [],
      setupState: data.setupState,
      loading: false,
      error: null,
    });
  }, []);

  useEffect(() => {
    void loadState();
  }, [loadState]);

  const handleLogin = useCallback(() => {
    chrome.tabs.create({ url: "https://faultray.com/auth/signin" });
    window.close();
  }, []);

  const handleLogout = useCallback(async () => {
    await sendMsg({ type: "CLEAR_SESSION" });
    await loadState();
  }, [loadState]);

  const handleStartSetup = useCallback(
    async (provider: CloudProvider) => {
      const res = await sendMsg({ type: "START_SETUP", payload: { provider } });
      if (!res.ok) {
        setState((prev) => ({ ...prev, error: res.error ?? "セットアップ開始に失敗しました" }));
        return;
      }
      await loadState();
    },
    [loadState]
  );

  const handleOpenConsole = useCallback((url: string) => {
    chrome.tabs.create({ url });
  }, []);

  const handleCancelSetup = useCallback(async () => {
    await chrome.storage.local.remove("faultray_setup_state");
    await loadState();
  }, [loadState]);

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div style={css.container}>
      {/* Header */}
      <div style={css.header}>
        <FaultRayLogo size={28} />
        <div>
          <div style={css.title}>FaultRay Cloud Assistant</div>
          <div style={css.subtitle}>Cloud setup guide</div>
        </div>
      </div>

      {/* Body */}
      {state.loading ? (
        <div
          style={{
            padding: "32px 16px",
            textAlign: "center",
            color: "#64748b",
            fontSize: "13px",
          }}
        >
          読み込み中...
        </div>
      ) : state.error ? (
        <div style={css.body}>
          <div style={css.errorBox}>{state.error}</div>
          <button style={css.primaryBtn} onClick={() => void loadState()}>
            再試行
          </button>
        </div>
      ) : state.setupState && state.session ? (
        <SetupScreen
          setupState={state.setupState}
          onOpenConsole={handleOpenConsole}
          onCancel={() => void handleCancelSetup()}
        />
      ) : state.session ? (
        <ConnectedScreen
          session={state.session}
          credentials={state.credentials}
          onSetup={(p) => void handleStartSetup(p)}
          onLogout={() => void handleLogout()}
        />
      ) : (
        <NotConnectedScreen onLogin={handleLogin} />
      )}

      {/* Footer */}
      <div
        style={{
          borderTop: "1px solid #1e293b",
          padding: "8px 16px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontSize: "10px", color: "#334155" }}>v1.0.0</span>
        <a
          href="https://faultray.com"
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: "10px", color: "#475569", textDecoration: "none" }}
        >
          faultray.com
        </a>
      </div>
    </div>
  );
}
