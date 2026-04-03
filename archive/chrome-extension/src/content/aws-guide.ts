// FaultRay Chrome Extension — AWS Console Content Script
// Injects a guided setup overlay onto AWS IAM console pages.

import type { SetupState } from "../lib/types";

// ── Step definitions ─────────────────────────────────────────────────────────

interface AwsStep {
  step: number;
  title: string;
  url?: string;
  instruction: string;
  highlight?: string;
  action?: "capture_keys" | "navigate";
}

const AWS_STEPS: AwsStep[] = [
  {
    step: 1,
    title: "IAMダッシュボードに移動",
    url: "https://console.aws.amazon.com/iam/",
    instruction: "左メニューの「ユーザー」をクリックしてください",
    highlight: "a[href*='users']",
  },
  {
    step: 2,
    title: "ユーザーを作成",
    url: "https://console.aws.amazon.com/iam/home#/users/create",
    instruction: "「ユーザーの作成」ボタンをクリックし、ユーザー名に「faultray-readonly」と入力してください",
  },
  {
    step: 3,
    title: "ReadOnlyAccessポリシーを付与",
    instruction: "「ポリシーを直接アタッチする」を選択し、「ReadOnlyAccess」を検索してチェックを入れてください",
  },
  {
    step: 4,
    title: "アクセスキーを作成",
    instruction:
      "ユーザー詳細画面の「セキュリティ認証情報」タブを開き、「アクセスキーを作成」をクリックしてください",
  },
  {
    step: 5,
    title: "キーをFaultRayに送信",
    instruction:
      "アクセスキーIDとシークレットアクセスキーが表示されています。下のフォームに入力して「FaultRayに送信」を押してください",
    action: "capture_keys",
  },
];

const TOTAL_STEPS = AWS_STEPS.length;

// ── State ────────────────────────────────────────────────────────────────────

let currentStep = 1;
let panelEl: HTMLElement | null = null;
let isDragging = false;
let dragOffsetX = 0;
let dragOffsetY = 0;

// ── Initialization ───────────────────────────────────────────────────────────

async function init(): Promise<void> {
  const response = await chrome.runtime.sendMessage({ type: "GET_SETUP_STATE" });
  if (!response?.ok) return;

  const state = response.data as SetupState | null;
  if (!state || state.provider !== "aws") return;

  currentStep = state.currentStep;
  injectPanel();
}

// ── Panel injection ──────────────────────────────────────────────────────────

function injectPanel(): void {
  if (panelEl) panelEl.remove();

  const step = AWS_STEPS.find((s) => s.step === currentStep);
  if (!step) {
    showCompletionToast();
    return;
  }

  panelEl = document.createElement("div");
  panelEl.id = "faultray-guide-panel";
  panelEl.innerHTML = buildPanelHTML(step);
  panelEl.style.cssText = [
    "position: fixed",
    "bottom: 24px",
    "right: 24px",
    "z-index: 999999",
    "width: 340px",
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  ].join(";");

  document.body.appendChild(panelEl);

  // Drag behaviour
  const header = panelEl.querySelector<HTMLElement>(".fr-panel-header");
  if (header) {
    header.addEventListener("mousedown", startDrag);
  }

  // Button actions
  panelEl.querySelector("#fr-next-btn")?.addEventListener("click", () => void onNextStep(step));
  panelEl.querySelector("#fr-close-btn")?.addEventListener("click", closePanel);
  panelEl.querySelector("#fr-submit-btn")?.addEventListener("click", () => void onSubmitKeys());

  // Highlight target element
  if (step.highlight) highlightElement(step.highlight);
}

function buildPanelHTML(step: AwsStep): string {
  const progressPct = Math.round(((currentStep - 1) / TOTAL_STEPS) * 100);

  const stepsHTML = AWS_STEPS.map((s) => {
    let icon = "⬜";
    if (s.step < currentStep) icon = "✅";
    else if (s.step === currentStep) icon = "→";
    const active = s.step === currentStep ? "font-weight:600;color:#FFD700;" : "color:#64748b;";
    return `<div style="display:flex;gap:8px;align-items:flex-start;padding:4px 0;${active}">
      <span style="flex-shrink:0;font-size:12px;">${icon}</span>
      <span style="font-size:12px;">Step ${s.step}: ${s.title}</span>
    </div>`;
  }).join("");

  const captureForm =
    step.action === "capture_keys"
      ? `<div style="margin-top:12px;display:flex;flex-direction:column;gap:8px;">
          <label style="font-size:11px;color:#94a3b8;">アクセスキーID</label>
          <input id="fr-access-key" type="text" placeholder="AKIA..." style="${inputStyle()}" />
          <label style="font-size:11px;color:#94a3b8;">シークレットアクセスキー</label>
          <input id="fr-secret-key" type="password" placeholder="Secret..." style="${inputStyle()}" />
          <label style="font-size:11px;color:#94a3b8;">リージョン</label>
          <select id="fr-region" style="${inputStyle()}">
            <option value="ap-northeast-1">ap-northeast-1 (東京)</option>
            <option value="ap-northeast-3">ap-northeast-3 (大阪)</option>
            <option value="us-east-1">us-east-1 (バージニア北部)</option>
            <option value="us-west-2">us-west-2 (オレゴン)</option>
            <option value="eu-west-1">eu-west-1 (アイルランド)</option>
          </select>
          <label style="font-size:11px;color:#94a3b8;">ラベル（任意）</label>
          <input id="fr-label" type="text" placeholder="Production AWS" value="Production AWS" style="${inputStyle()}" />
          <div style="background:#ff6b0020;border:1px solid #ff6b0040;border-radius:6px;padding:8px;font-size:11px;color:#fbbf24;">
            ⚠️ このキーはHTTPS経由でFaultRayにのみ送信され、送信後即時削除されます
          </div>
          <button id="fr-submit-btn" style="${primaryBtnStyle()}">FaultRayに送信 →</button>
        </div>`
      : "";

  const nextBtn =
    step.action !== "capture_keys"
      ? `<button id="fr-next-btn" style="${primaryBtnStyle()}">次へ →</button>`
      : "";

  return `
    <div style="background:#0a0e1a;border:1px solid #1e293b;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.6);overflow:hidden;">
      <!-- Header (drag handle) -->
      <div class="fr-panel-header" style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#0d1220;border-bottom:1px solid #1e293b;cursor:move;user-select:none;">
        <div style="display:flex;align-items:center;gap:8px;">
          <svg width="20" height="20" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="100" height="100" rx="20" fill="#0a0e1a"/>
            <g opacity="0.2"><line x1="25" y1="0" x2="25" y2="100" stroke="#e2e8f0" stroke-width="2"/><line x1="50" y1="0" x2="50" y2="100" stroke="#e2e8f0" stroke-width="2"/><line x1="75" y1="0" x2="75" y2="100" stroke="#e2e8f0" stroke-width="2"/><line x1="0" y1="25" x2="100" y2="25" stroke="#e2e8f0" stroke-width="2"/><line x1="0" y1="50" x2="100" y2="50" stroke="#e2e8f0" stroke-width="2"/><line x1="0" y1="75" x2="100" y2="75" stroke="#e2e8f0" stroke-width="2"/></g>
            <line x1="0" y1="65" x2="65" y2="0" stroke="#FFD700" stroke-width="4" stroke-linecap="round"/>
          </svg>
          <span style="color:#e2e8f0;font-size:13px;font-weight:600;">FaultRay セットアップ</span>
        </div>
        <button id="fr-close-btn" style="background:none;border:none;color:#64748b;cursor:pointer;font-size:18px;line-height:1;padding:0 4px;">✕</button>
      </div>

      <!-- Progress bar -->
      <div style="height:3px;background:#1e293b;">
        <div style="height:100%;width:${progressPct}%;background:linear-gradient(90deg,#FFD700,#ffe44d);transition:width 0.3s ease;"></div>
      </div>

      <!-- Content -->
      <div style="padding:16px;">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Step ${currentStep} / ${TOTAL_STEPS}</div>
        <div style="font-size:15px;font-weight:600;color:#FFD700;margin-bottom:8px;">${step.title}</div>
        <div style="font-size:13px;color:#94a3b8;line-height:1.5;margin-bottom:12px;">${step.instruction}</div>

        <!-- Step list -->
        <div style="border:1px solid #1e293b;border-radius:8px;padding:10px;margin-bottom:12px;">
          ${stepsHTML}
        </div>

        ${captureForm}
        ${nextBtn}
      </div>
    </div>
  `;
}

function inputStyle(): string {
  return [
    "width:100%",
    "box-sizing:border-box",
    "background:#0d1220",
    "border:1px solid #1e293b",
    "border-radius:6px",
    "color:#e2e8f0",
    "padding:8px 10px",
    "font-size:12px",
    "outline:none",
  ].join(";");
}

function primaryBtnStyle(): string {
  return [
    "width:100%",
    "background:#FFD700",
    "color:#0a0e1a",
    "border:none",
    "border-radius:8px",
    "padding:10px",
    "font-size:13px",
    "font-weight:700",
    "cursor:pointer",
    "transition:background 0.2s",
  ].join(";");
}

// ── Step navigation ──────────────────────────────────────────────────────────

async function onNextStep(step: AwsStep): Promise<void> {
  await chrome.runtime.sendMessage({
    type: "STEP_COMPLETED",
    payload: { step: step.step },
  });

  currentStep = step.step + 1;
  const nextStep = AWS_STEPS.find((s) => s.step === currentStep);

  if (nextStep?.url) {
    window.location.href = nextStep.url;
  } else {
    injectPanel();
  }
}

async function onSubmitKeys(): Promise<void> {
  const accessKey = (panelEl?.querySelector<HTMLInputElement>("#fr-access-key"))?.value?.trim();
  const secretKey = (panelEl?.querySelector<HTMLInputElement>("#fr-secret-key"))?.value?.trim();
  const region = (panelEl?.querySelector<HTMLSelectElement>("#fr-region"))?.value ?? "ap-northeast-1";
  const label = (panelEl?.querySelector<HTMLInputElement>("#fr-label"))?.value?.trim() || "Production AWS";

  if (!accessKey || !secretKey) {
    showError("アクセスキーIDとシークレットアクセスキーを入力してください");
    return;
  }

  if (!accessKey.startsWith("AKIA") && !accessKey.startsWith("ASIA")) {
    showError("有効なアクセスキーIDを入力してください（AKIAまたはASIAで始まる）");
    return;
  }

  const submitBtn = panelEl?.querySelector<HTMLButtonElement>("#fr-submit-btn");
  if (submitBtn) {
    submitBtn.textContent = "送信中...";
    submitBtn.disabled = true;
  }

  const response = await chrome.runtime.sendMessage({
    type: "SUBMIT_KEYS",
    payload: {
      keys: { accessKeyId: accessKey, secretAccessKey: secretKey },
      region,
      label,
    },
  });

  if (!response.ok) {
    showError(`エラー: ${response.error as string}`);
    if (submitBtn) {
      submitBtn.textContent = "FaultRayに送信 →";
      submitBtn.disabled = false;
    }
    return;
  }

  showCompletionToast();
  panelEl?.remove();
}

// ── Element highlighting ──────────────────────────────────────────────────────

function highlightElement(selector: string): void {
  const el = document.querySelector<HTMLElement>(selector);
  if (!el) return;

  el.style.outline = "2px solid #FFD700";
  el.style.outlineOffset = "3px";
  el.style.borderRadius = "4px";
  el.style.animation = "faultray-pulse 1.5s ease-in-out infinite";

  injectPulseKeyframes();
}

function injectPulseKeyframes(): void {
  const styleId = "faultray-keyframes";
  if (document.getElementById(styleId)) return;

  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = `
    @keyframes faultray-pulse {
      0%, 100% { outline-color: #FFD700; box-shadow: 0 0 0 0 rgba(255,215,0,0.4); }
      50% { outline-color: #ffe44d; box-shadow: 0 0 0 6px rgba(255,215,0,0); }
    }
  `;
  document.head.appendChild(style);
}

// ── Toasts ───────────────────────────────────────────────────────────────────

function showError(message: string): void {
  const toast = createToast(message, "#ff6b6b", "#1a0a0a");
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 5000);
}

function showCompletionToast(): void {
  const toast = createToast(
    "✅ AWSの接続が完了しました！FaultRayでスキャンを開始できます。",
    "#4ade80",
    "#0a1a0a"
  );
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 8000);
}

function createToast(message: string, color: string, bg: string): HTMLElement {
  const el = document.createElement("div");
  el.style.cssText = [
    "position:fixed",
    "bottom:24px",
    "left:50%",
    "transform:translateX(-50%)",
    `background:${bg}`,
    `border:1px solid ${color}40`,
    "border-radius:8px",
    "padding:12px 20px",
    `color:${color}`,
    "font-size:13px",
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif",
    "z-index:1000000",
    "max-width:400px",
    "text-align:center",
    "box-shadow:0 8px 30px rgba(0,0,0,0.4)",
  ].join(";");
  el.textContent = message;
  return el;
}

// ── Drag behaviour ────────────────────────────────────────────────────────────

function startDrag(e: MouseEvent): void {
  if (!panelEl) return;
  isDragging = true;
  const rect = panelEl.getBoundingClientRect();
  dragOffsetX = e.clientX - rect.left;
  dragOffsetY = e.clientY - rect.top;
  document.addEventListener("mousemove", onDrag);
  document.addEventListener("mouseup", stopDrag);
}

function onDrag(e: MouseEvent): void {
  if (!isDragging || !panelEl) return;
  panelEl.style.right = "auto";
  panelEl.style.bottom = "auto";
  panelEl.style.left = `${e.clientX - dragOffsetX}px`;
  panelEl.style.top = `${e.clientY - dragOffsetY}px`;
}

function stopDrag(): void {
  isDragging = false;
  document.removeEventListener("mousemove", onDrag);
  document.removeEventListener("mouseup", stopDrag);
}

function closePanel(): void {
  panelEl?.remove();
  panelEl = null;
}

// ── Boot ─────────────────────────────────────────────────────────────────────

void init();
