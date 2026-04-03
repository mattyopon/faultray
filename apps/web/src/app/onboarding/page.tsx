"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  Rocket,
  CheckCircle2,
  Circle,
  ChevronRight,
  ChevronLeft,
  Cloud,
  Server,
  BarChart3,
  Shield,
  FileCode2,
  BookOpen,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type CloudProvider = "aws" | "gcp" | "azure" | "onprem" | "dontknow";
type Industry = "fintech" | "healthcare" | "ecommerce" | "saas" | "media" | "other";

interface OnboardingState {
  cloud: CloudProvider | null;
  industry: Industry | null;
  answers: Record<number, boolean | null>;
}

interface Recommendation {
  icon: React.ElementType;
  labelKey: string;
  href: string;
  priority: "high" | "medium" | "low";
}

/* ------------------------------------------------------------------ */
/*  Score calculation                                                  */
/* ------------------------------------------------------------------ */

function calcScore(answers: Record<number, boolean | null>): number {
  const yesCount = Object.values(answers).filter((v) => v === true).length;
  const total = 5;
  return Math.round(20 + (yesCount / total) * 65);
}

function getScoreColor(score: number): string {
  if (score >= 70) return "text-green-400";
  if (score >= 45) return "text-yellow-400";
  return "text-red-400";
}

function getScoreLabel(score: number, _t: Record<string, string>): string {
  if (score >= 70) return "Good foundation";
  if (score >= 45) return "Needs improvement";
  return "Critical gaps identified";
}

function getRecommendations(
  answers: Record<number, boolean | null>,
  _t: Record<string, string>
): Recommendation[] {
  const recs: Recommendation[] = [
    {
      icon: Zap,
      labelKey: "rec1",
      href: "/simulate",
      priority: "high",
    },
  ];
  if (!answers[1]) {
    recs.push({ icon: BarChart3, labelKey: "rec2", href: "/apm", priority: "high" });
  }
  if (!answers[3]) {
    recs.push({ icon: FileCode2, labelKey: "rec3", href: "/iac", priority: "medium" });
  }
  if (!answers[4]) {
    recs.push({ icon: BookOpen, labelKey: "rec5", href: "/runbooks", priority: "medium" });
  }
  if (!answers[2]) {
    recs.push({ icon: Shield, labelKey: "rec4", href: "/compliance", priority: "low" });
  }
  return recs.slice(0, 4);
}

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

interface StepIndicatorProps {
  current: number;
  total: number;
}

function StepIndicator({ current, total }: StepIndicatorProps) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => (
        <div key={i} className="flex items-center gap-2">
          <div
            className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-colors ${
              i + 1 < current
                ? "bg-[#FFD700] text-black"
                : i + 1 === current
                ? "bg-[#FFD700]/20 border border-[#FFD700]/40 text-[#FFD700]"
                : "bg-[#1e293b] text-[#475569]"
            }`}
          >
            {i + 1 < current ? <CheckCircle2 size={14} /> : i + 1}
          </div>
          {i < total - 1 && (
            <div
              className={`h-px w-8 transition-colors ${
                i + 1 < current ? "bg-[#FFD700]" : "bg-[#1e293b]"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function OnboardingPage() {
  const locale = useLocale();
  const t = (appDict.onboarding as Record<string, Record<string, string>>)[locale] ?? appDict.onboarding.en;
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [state, setState] = useState<OnboardingState>({
    cloud: null,
    industry: null,
    answers: {},
  });

  const cloudOptions: { id: CloudProvider; label: string; icon: React.ElementType }[] = [
    { id: "aws", label: t.aws, icon: Cloud },
    { id: "gcp", label: t.gcp, icon: Cloud },
    { id: "azure", label: t.azure, icon: Cloud },
    { id: "onprem", label: t.onprem, icon: Server },
    { id: "dontknow", label: t.dontKnow, icon: Circle },
  ];

  const industryOptions: { id: Industry; label: string }[] = [
    { id: "fintech", label: t.fintech },
    { id: "healthcare", label: t.healthcare },
    { id: "ecommerce", label: t.ecommerce },
    { id: "saas", label: t.saas },
    { id: "media", label: t.media },
    { id: "other", label: t.other },
  ];

  const questions: { id: number; label: string }[] = [
    { id: 1, label: t.q1 },
    { id: 2, label: t.q2 },
    { id: 3, label: t.q3 },
    { id: 4, label: t.q4 },
    { id: 5, label: t.q5 },
  ];

  const score = calcScore(state.answers);
  const recommendations = getRecommendations(state.answers, t);

  const canProceedStep1 = state.cloud !== null && state.industry !== null;
  const canProceedStep2 = Object.keys(state.answers).length === 5;

  return (
    <main className="min-h-screen bg-[#0a0e1a] text-white pt-20 pb-12">
      <div className="max-w-[1200px] mx-auto px-6 py-10">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-[#FFD700]/10 border border-[#FFD700]/20 mb-4">
            <Rocket size={28} className="text-[#FFD700]" />
          </div>
          <h1 className="text-2xl font-bold mb-2">{t.title}</h1>
          <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        </div>

        {/* Step indicator */}
        <div className="flex justify-center mb-8">
          <StepIndicator current={step} total={3} />
        </div>

        {/* Step 1: Stack selection */}
        {step === 1 && (
          <Card className="bg-[#0f1629] border-[#1e293b] p-6">
            <h2 className="text-lg font-semibold mb-1">{t.step1}</h2>
            <p className="text-sm text-[#64748b] mb-6">{t.step1Desc}</p>

            <div className="mb-6">
              <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider mb-3">
                {t.cloud}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {cloudOptions.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setState((s) => ({ ...s, cloud: id }))}
                    className={`flex items-center gap-2 p-3 rounded-lg border text-sm transition-colors ${
                      state.cloud === id
                        ? "border-[#FFD700]/40 bg-[#FFD700]/5 text-white"
                        : "border-[#1e293b] text-[#94a3b8] hover:border-[#334155] hover:text-white"
                    }`}
                  >
                    <Icon size={16} className={state.cloud === id ? "text-[#FFD700]" : "text-[#475569]"} />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <div className="mb-8">
              <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider mb-3">
                {t.industry}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {industryOptions.map(({ id, label }) => (
                  <button
                    key={id}
                    onClick={() => setState((s) => ({ ...s, industry: id }))}
                    className={`p-3 rounded-lg border text-sm transition-colors ${
                      state.industry === id
                        ? "border-[#FFD700]/40 bg-[#FFD700]/5 text-white"
                        : "border-[#1e293b] text-[#94a3b8] hover:border-[#334155] hover:text-white"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <Button
              onClick={() => setStep(2)}
              disabled={!canProceedStep1}
              className="w-full bg-[#FFD700] text-black hover:bg-[#FFD700]/90 disabled:opacity-40"
            >
              {t.next}
              <ChevronRight size={16} className="ml-1" />
            </Button>
          </Card>
        )}

        {/* Step 2: Quick Assessment */}
        {step === 2 && (
          <Card className="bg-[#0f1629] border-[#1e293b] p-6">
            <h2 className="text-lg font-semibold mb-1">{t.step2}</h2>
            <p className="text-sm text-[#64748b] mb-6">{t.step2Desc}</p>

            <div className="space-y-3 mb-8">
              {questions.map(({ id, label }) => (
                <div
                  key={id}
                  className="flex items-center justify-between p-4 rounded-lg border border-[#1e293b] bg-[#060b16]"
                >
                  <p className="text-sm text-[#94a3b8] pr-4">{label}</p>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() =>
                        setState((s) => ({
                          ...s,
                          answers: { ...s.answers, [id]: true },
                        }))
                      }
                      className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors border ${
                        state.answers[id] === true
                          ? "bg-green-500/10 border-green-500/30 text-green-400"
                          : "border-[#1e293b] text-[#64748b] hover:border-[#334155] hover:text-white"
                      }`}
                    >
                      {t.yes}
                    </button>
                    <button
                      onClick={() =>
                        setState((s) => ({
                          ...s,
                          answers: { ...s.answers, [id]: false },
                        }))
                      }
                      className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors border ${
                        state.answers[id] === false
                          ? "bg-red-500/10 border-red-500/30 text-red-400"
                          : "border-[#1e293b] text-[#64748b] hover:border-[#334155] hover:text-white"
                      }`}
                    >
                      {t.no}
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <Button
                variant="secondary"
                onClick={() => setStep(1)}
                className="border-[#1e293b] text-[#94a3b8] hover:text-white"
              >
                <ChevronLeft size={16} className="mr-1" />
                {t.back}
              </Button>
              <Button
                onClick={() => setStep(3)}
                disabled={!canProceedStep2}
                className="flex-1 bg-[#FFD700] text-black hover:bg-[#FFD700]/90 disabled:opacity-40"
              >
                {t.next}
                <ChevronRight size={16} className="ml-1" />
              </Button>
            </div>
          </Card>
        )}

        {/* Step 3: Results */}
        {step === 3 && (
          <Card className="bg-[#0f1629] border-[#1e293b] p-6">
            <h2 className="text-lg font-semibold mb-1">{t.step3}</h2>
            <p className="text-sm text-[#64748b] mb-6">{t.step3Desc}</p>

            {/* Score */}
            <div className="bg-[#060b16] rounded-xl p-6 text-center mb-6">
              <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.yourScore}</p>
              <div className="relative inline-flex items-center justify-center w-28 h-28 mb-3">
                <svg viewBox="0 0 36 36" className="w-28 h-28 -rotate-90">
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none" stroke="#1e293b" strokeWidth="2"
                  />
                  <circle
                    cx="18" cy="18" r="15.9"
                    fill="none"
                    stroke={score >= 70 ? "#4ade80" : score >= 45 ? "#facc15" : "#f87171"}
                    strokeWidth="2"
                    strokeDasharray={`${score} ${100 - score}`}
                    strokeLinecap="round"
                  />
                </svg>
                <span className={`absolute text-3xl font-bold ${getScoreColor(score)}`}>
                  {score}
                </span>
              </div>
              <p className={`text-sm font-semibold ${getScoreColor(score)}`}>
                {getScoreLabel(score, t)}
              </p>
            </div>

            {/* Recommendations */}
            <div className="mb-6">
              <p className="text-xs font-medium text-[#94a3b8] uppercase tracking-wider mb-3">
                {t.recommendations}
              </p>
              <div className="space-y-2">
                {recommendations.map((rec, idx) => {
                  const Icon = rec.icon;
                  return (
                    <Link
                      key={idx}
                      href={rec.href}
                      className="flex items-center gap-3 p-3 rounded-lg border border-[#1e293b] hover:border-[#334155] transition-colors group"
                    >
                      <div className="w-8 h-8 rounded-lg bg-[#FFD700]/10 flex items-center justify-center shrink-0">
                        <Icon size={15} className="text-[#FFD700]" />
                      </div>
                      <span className="text-sm text-[#94a3b8] group-hover:text-white transition-colors flex-1">
                        {t[rec.labelKey]}
                      </span>
                      <Badge className={`text-[9px] shrink-0 ${
                        rec.priority === "high"
                          ? "bg-red-500/10 text-red-400 border-red-500/20"
                          : rec.priority === "medium"
                          ? "bg-yellow-500/10 text-yellow-400 border-yellow-500/20"
                          : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                      }`}>
                        {rec.priority}
                      </Badge>
                      <ChevronRight size={14} className="text-[#475569] group-hover:text-[#94a3b8]" />
                    </Link>
                  );
                })}
              </div>
            </div>

            {/* CTAs */}
            <div className="space-y-3">
              {/* FLOW-05: Auto-redirect to simulate after onboarding completion */}
              <Button
                className="w-full bg-[#FFD700] text-black hover:bg-[#FFD700]/90 font-semibold"
                onClick={() => router.push("/simulate")}
              >
                <Zap size={16} className="mr-2" />
                {t.startFree}
              </Button>
              <Button
                variant="secondary"
                className="w-full border-[#1e293b] text-[#64748b] hover:text-white hover:border-[#334155]"
                onClick={() => router.push("/dashboard")}
              >
                {t.skipOnboarding}
              </Button>
            </div>
          </Card>
        )}

        {/* Progress dots */}
        <div className="flex justify-center gap-2 mt-6">
          {[1, 2, 3].map((s) => (
            <button
              key={s}
              onClick={() => {
                if (s < step || (s === 2 && canProceedStep1) || (s === 3 && canProceedStep2)) {
                  setStep(s);
                }
              }}
              className={`w-2 h-2 rounded-full transition-colors ${
                s === step ? "bg-[#FFD700]" : s < step ? "bg-[#FFD700]/40" : "bg-[#1e293b]"
              }`}
            />
          ))}
        </div>
      </div>
    </main>
  );
}
