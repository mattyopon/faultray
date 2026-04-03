"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { locales, type Locale } from "@/i18n/config";
import {
  Zap,
  BarChart3,
  Terminal,
  Rocket,
  X,
  ChevronRight,
  ChevronLeft,
  Sparkles,
} from "lucide-react";

/* ─── i18n texts ─── */

interface StepText {
  title: string;
  description: string;
  detail?: string;
}

interface OnboardingTexts {
  steps: StepText[];
  skip: string;
  next: string;
  prev: string;
  done: string;
  stepOf: (current: number, total: number) => string;
  dontShowAgain: string;
}

const texts: Record<"en" | "ja", OnboardingTexts> = {
  en: {
    steps: [
      {
        title: "Welcome to FaultRay!",
        description:
          "Verify your infrastructure's fault tolerance in 3 minutes.",
        detail:
          "FaultRay runs 2,000+ chaos scenarios against your topology — purely in simulation, zero production risk.",
      },
      {
        title: "Run a Simulation",
        description:
          'Select a sample topology from the Dashboard and click "Run Simulation".',
        detail:
          "One click to run. No agents, no staging environment needed for your first test.",
      },
      {
        title: "Read the Results",
        description:
          "Understand your Resilience Score, 3-Layer Model, and Critical Failures.",
        detail:
          "The score (0-100) shows your availability ceiling. The 3-Layer Model breaks it down by Software, Hardware, and Theoretical limits.",
      },
      {
        title: "Connect Your Environment",
        description:
          "Install the CLI Agent to scan your production topology.",
        detail:
          "Run: npx faultray-agent@latest init — then link it to your FaultRay account for live topology scanning.",
      },
      {
        title: "You're All Set!",
        description: "Start with a sample simulation and explore.",
        detail:
          "We'll redirect you to the simulation page so you can try it right away.",
      },
    ],
    skip: "Skip",
    next: "Next",
    prev: "Back",
    done: "Get Started",
    stepOf: (c, t) => `${c} of ${t}`,
    dontShowAgain: "Don\u2019t show this again",
  },
  ja: {
    steps: [
      {
        title: "FaultRayへようこそ！",
        description:
          "3分でインフラの耐障害性を確認できます。",
        detail:
          "FaultRayは2,000以上のChaosシナリオをトポロジーに対して実行します。完全なシミュレーションで、本番リスクはゼロです。",
      },
      {
        title: "シミュレーションを実行",
        description:
          "ダッシュボードからサンプルトポロジーを選んで「Run Simulation」をクリック。",
        detail:
          "ワンクリックで実行。最初のテストにはエージェントもステージング環境も不要です。",
      },
      {
        title: "結果の読み方",
        description:
          "レジリエンススコア、3レイヤーモデル、クリティカル障害の見方を学びます。",
        detail:
          "スコア(0-100)は可用性の上限を示します。3レイヤーモデルはソフトウェア、ハードウェア、理論限界に分解します。",
      },
      {
        title: "本番環境を接続",
        description:
          "CLIエージェントをインストールして本番トポロジーをスキャン。",
        detail:
          "実行: npx faultray-agent@latest init — FaultRayアカウントにリンクしてライブトポロジースキャンを開始します。",
      },
      {
        title: "準備完了！",
        description: "まずはサンプルシミュレーションを試してみましょう。",
        detail:
          "シミュレーションページに移動して、すぐにお試しいただけます。",
      },
    ],
    skip: "スキップ",
    next: "次へ",
    prev: "戻る",
    done: "始める",
    stepOf: (c, t) => `${c} / ${t}`,
    dontShowAgain: "今後表示しない",
  },
};

/* ─── Step icons ─── */

const stepIcons = [Sparkles, Zap, BarChart3, Terminal, Rocket];

/* ─── Locale detection ─── */

function detectLocale(): "en" | "ja" {
  if (typeof document === "undefined") return "en";
  const cookie = document.cookie
    .split(";")
    .find((c) => c.trim().startsWith("NEXT_LOCALE="));
  if (cookie) {
    const val = cookie.split("=")[1]?.trim();
    if (val && locales.includes(val as Locale)) {
      // Onboarding only has en/ja texts; other locales fall back to en
      return val === "ja" ? "ja" : "en";
    }
  }
  // Also check URL path
  const path = window.location.pathname;
  if (path.startsWith("/ja/") || path === "/ja") {
    return "ja";
  }
  return "en";
}

/* ─── Constants ─── */

const STORAGE_KEY = "faultray_onboarded";
const TOTAL_STEPS = 5;

/* ─── Component ─── */

export function Onboarding() {
  const router = useRouter();
  const [visible, setVisible] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) !== "true";
    } catch {
      return true;
    }
  });
  const [step, setStep] = useState(0);
  const [locale, setLocale] = useState<"en" | "ja">(() => detectLocale());
  const [dontShow, setDontShow] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [direction, setDirection] = useState<"next" | "prev">("next");

  const t = texts[locale];

  const close = useCallback(() => {
    setVisible(false);
    try {
      localStorage.setItem(STORAGE_KEY, "true");
    } catch {
      // ignore
    }
  }, []);

  const handleSkip = useCallback(() => {
    close();
  }, [close]);

  const handleDone = useCallback(() => {
    if (dontShow) {
      try {
        localStorage.setItem(STORAGE_KEY, "true");
      } catch {
        // ignore
      }
    }
    close();
    router.push("/simulate");
  }, [close, dontShow, router]);

  const goNext = useCallback(() => {
    if (animating) return;
    if (step >= TOTAL_STEPS - 1) {
      handleDone();
      return;
    }
    setDirection("next");
    setAnimating(true);
    setTimeout(() => {
      setStep((s) => s + 1);
      setAnimating(false);
    }, 200);
  }, [step, animating, handleDone]);

  const goPrev = useCallback(() => {
    if (animating || step <= 0) return;
    setDirection("prev");
    setAnimating(true);
    setTimeout(() => {
      setStep((s) => s - 1);
      setAnimating(false);
    }, 200);
  }, [step, animating]);

  // Keyboard navigation
  useEffect(() => {
    if (!visible) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" || e.key === "Enter") goNext();
      else if (e.key === "ArrowLeft") goPrev();
      else if (e.key === "Escape") handleSkip();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [visible, goNext, goPrev, handleSkip]);

  if (!visible) return null;

  const Icon = stepIcons[step];
  const currentStep = t.steps[step];
  const isLast = step === TOTAL_STEPS - 1;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={handleSkip}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg mx-4 bg-[#0f1629] border border-[#1e293b] rounded-2xl shadow-2xl shadow-black/50 overflow-hidden">
        {/* Gold accent line */}
        <div className="h-1 bg-gradient-to-r from-[#FFD700] via-[#ffe44d] to-[#FFD700]" />

        {/* Close button */}
        <button
          onClick={handleSkip}
          className="absolute top-4 right-4 p-1.5 text-[#64748b] hover:text-white transition-colors rounded-lg hover:bg-white/5"
          aria-label={locale === "ja" ? "閉じる" : "Close"}
        >
          <X size={18} />
        </button>

        {/* Progress bar */}
        <div className="px-8 pt-6">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-[#64748b]">
              {t.stepOf(step + 1, TOTAL_STEPS)}
            </span>
          </div>
          <div className="h-1 bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full bg-[#FFD700] rounded-full transition-all duration-500 ease-out"
              style={{ width: `${((step + 1) / TOTAL_STEPS) * 100}%` }}
            />
          </div>
        </div>

        {/* Content */}
        <div className="px-8 py-8">
          <div
            className={`transition-all duration-200 ${
              animating
                ? direction === "next"
                  ? "opacity-0 translate-x-4"
                  : "opacity-0 -translate-x-4"
                : "opacity-100 translate-x-0"
            }`}
          >
            {/* Icon */}
            <div className="w-16 h-16 rounded-2xl bg-[#FFD700]/10 border border-[#FFD700]/20 flex items-center justify-center mb-6">
              <Icon size={28} className="text-[#FFD700]" />
            </div>

            {/* Title */}
            <h2 className="text-xl font-bold text-white mb-2">
              {currentStep.title}
            </h2>

            {/* Description */}
            <p className="text-[#94a3b8] text-sm leading-relaxed mb-3">
              {currentStep.description}
            </p>

            {/* Detail */}
            {currentStep.detail && (
              <p className="text-[#64748b] text-xs leading-relaxed border-l-2 border-[#FFD700]/30 pl-3">
                {currentStep.detail}
              </p>
            )}
          </div>
        </div>

        {/* Step indicators */}
        <div className="flex justify-center gap-2 pb-4">
          {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
            <button
              key={i}
              onClick={() => {
                if (!animating) {
                  setDirection(i > step ? "next" : "prev");
                  setStep(i);
                }
              }}
              className={`w-2 h-2 rounded-full transition-all duration-300 ${
                i === step
                  ? "bg-[#FFD700] w-6"
                  : i < step
                    ? "bg-[#FFD700]/40"
                    : "bg-white/10"
              }`}
              aria-label={`Step ${i + 1}`}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="px-8 pb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {step > 0 ? (
              <button
                onClick={goPrev}
                className="flex items-center gap-1 px-3 py-2 text-sm text-[#94a3b8] hover:text-white transition-colors rounded-lg hover:bg-white/5"
              >
                <ChevronLeft size={16} />
                {t.prev}
              </button>
            ) : (
              <button
                onClick={handleSkip}
                className="px-3 py-2 text-sm text-[#64748b] hover:text-white transition-colors rounded-lg hover:bg-white/5"
              >
                {t.skip}
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {isLast && (
              <label className="flex items-center gap-2 text-xs text-[#64748b] cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={dontShow}
                  onChange={(e) => setDontShow(e.target.checked)}
                  className="w-3.5 h-3.5 rounded border-[#1e293b] bg-transparent accent-[#FFD700]"
                />
                {t.dontShowAgain}
              </label>
            )}
            <button
              onClick={goNext}
              className="flex items-center gap-1.5 px-5 py-2.5 text-sm font-semibold bg-[#FFD700] text-[#0a0e1a] rounded-lg hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] transition-all duration-200 hover:-translate-y-0.5"
            >
              {isLast ? t.done : t.next}
              {!isLast && <ChevronRight size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
