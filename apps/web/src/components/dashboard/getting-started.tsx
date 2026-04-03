"use client";

/**
 * UX-03: Getting Started Checklist — extracted as reusable component.
 * 4-step onboarding: account → first simulation → report → improvements.
 * Progress persisted via localStorage.
 */

import { useState, useEffect } from "react";
import Link from "next/link";
import { Zap, CheckCircle2, Circle, X, PartyPopper } from "lucide-react";

const STORAGE_KEY_DISMISSED = "faultray_checklist_dismissed";
const STORAGE_KEY_CHECKED = "faultray_checklist_checked";

interface Step {
  label: string;
  labelEn: string;
  href: string | null;
  alwaysDone: boolean;
}

const STEPS: Step[] = [
  { label: "アカウント作成", labelEn: "Create account", href: null, alwaysDone: true },
  { label: "最初のシミュレーションを実行", labelEn: "Run first simulation", href: "/simulate", alwaysDone: false },
  { label: "レポートを確認", labelEn: "Review report", href: "/reports", alwaysDone: false },
  { label: "改善提案を確認", labelEn: "Check improvement suggestions", href: "/suggestions", alwaysDone: false },
];

interface GettingStartedProps {
  hasRun: boolean;
  locale?: string;
}

export function GettingStarted({ hasRun, locale = "en" }: GettingStartedProps) {
  const isJa = locale === "ja";
  const [dismissed, setDismissed] = useState(false);
  const [checkedItems, setCheckedItems] = useState<Record<number, boolean>>({});

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY_DISMISSED) === "true") {
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setDismissed(true);
      }
      const stored = localStorage.getItem(STORAGE_KEY_CHECKED);
      if (stored) {
        setCheckedItems(JSON.parse(stored) as Record<number, boolean>);
      }
    } catch { /* ignore */ }
  }, []);

  // Auto-check step 1 (first simulation) when a run exists
  useEffect(() => {
    if (hasRun) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCheckedItems((prev) => {
        const next = { ...prev, 1: true };
        try { localStorage.setItem(STORAGE_KEY_CHECKED, JSON.stringify(next)); } catch { /* ignore */ }
        return next;
      });
    }
  }, [hasRun]);

  const dismiss = () => {
    setDismissed(true);
    try { localStorage.setItem(STORAGE_KEY_DISMISSED, "true"); } catch { /* ignore */ }
  };

  const toggle = (idx: number) => {
    setCheckedItems((prev) => {
      const next = { ...prev, [idx]: !prev[idx] };
      try { localStorage.setItem(STORAGE_KEY_CHECKED, JSON.stringify(next)); } catch { /* ignore */ }
      return next;
    });
  };

  const allDone = STEPS.every((s, i) => s.alwaysDone || checkedItems[i]);

  if (dismissed) return null;

  // All complete → congratulations message
  if (allDone) {
    return (
      <div className="mb-8 p-5 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04]">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <PartyPopper size={16} className="text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-300">
              {isJa ? "おめでとうございます！セットアップ完了です" : "Congratulations! Setup complete"}
            </span>
          </div>
          <button
            onClick={dismiss}
            className="p-1 text-[#64748b] hover:text-white transition-colors rounded"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    );
  }

  const completedCount = STEPS.filter((s, i) => s.alwaysDone || checkedItems[i]).length;

  return (
    <div className="mb-8 p-5 rounded-xl border border-[#1e293b] bg-[#0d1117]">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Zap size={14} className="text-[#FFD700]" />
          Getting Started
          <span className="text-xs text-[#64748b] font-normal">
            {completedCount}/{STEPS.length}
          </span>
        </h3>
        <button
          onClick={dismiss}
          className="p-1 text-[#64748b] hover:text-white transition-colors rounded"
          aria-label="Close checklist"
        >
          <X size={14} />
        </button>
      </div>
      {/* Progress bar */}
      <div className="h-1 bg-[#1e293b] rounded-full overflow-hidden mb-4">
        <div
          className="h-full bg-[#FFD700] rounded-full transition-all duration-500"
          style={{ width: `${(completedCount / STEPS.length) * 100}%` }}
        />
      </div>
      <div className="space-y-2">
        {STEPS.map((step, i) => {
          const done = step.alwaysDone || !!checkedItems[i];
          const label = isJa ? step.label : step.labelEn;
          return (
            <div key={i} className="flex items-center gap-3">
              <button
                onClick={() => !step.alwaysDone && toggle(i)}
                className="shrink-0 transition-colors"
                aria-label={done ? "Done" : "Mark done"}
                disabled={step.alwaysDone}
              >
                {done
                  ? <CheckCircle2 size={16} className="text-emerald-400" />
                  : <Circle size={16} className="text-[#334155]" />}
              </button>
              {step.href ? (
                <Link
                  href={step.href}
                  className={`text-sm transition-colors hover:text-[#FFD700] ${done ? "line-through text-[#475569]" : "text-[#94a3b8]"}`}
                >
                  {label}
                </Link>
              ) : (
                <span className={`text-sm ${done ? "line-through text-[#475569]" : "text-[#94a3b8]"}`}>
                  {label}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
