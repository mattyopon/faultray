"use client";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type SimulationRun, type Project } from "@/lib/api";
import { Onboarding } from "@/components/onboarding";
import { GettingStarted } from "@/components/dashboard/getting-started";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import {
  Zap,
  TrendingUp,
  Shield,
  AlertTriangle,
  Clock,
  ArrowRight,
  BarChart3,
  FolderKanban,
  Info,
  Activity,
} from "lucide-react";

// ---- Sample data shown when no simulation runs exist ----
const SAMPLE_SCORE = 72;
const SAMPLE_COMPONENTS = 6;
const SAMPLE_CRITICAL = 2;
const SAMPLE_WARNING = 5;

function ScoreRing({ score, size = 120 }: { score: number; size?: number }) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg viewBox="0 0 100 100" className="transform -rotate-90" style={{ width: size, height: size }} aria-hidden="true">
        <circle cx="50" cy="50" r={radius} stroke="#1e293b" strokeWidth="8" fill="none" />
        <circle
          cx="50" cy="50" r={radius}
          stroke={color} strokeWidth="8" fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-1000 ease-out"
          style={{ animation: "score-fill 1.5s ease-out" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-extrabold" style={{ color }}>{score.toFixed(1)}</span>
        <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider">Score</span>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [runs, setRuns] = useState<SimulationRun[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const locale = useLocale();
  const t = appDict.dashboard[locale] ?? appDict.dashboard.en;
  const tProjects = appDict.projects[locale] ?? appDict.projects.en;

  // Trial state
  const [trialEndsAt, setTrialEndsAt] = useState<string | null>(null);
  const trialDaysLeft = trialEndsAt
    ? Math.max(0, Math.ceil((new Date(trialEndsAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;
  const isTrialActive = trialEndsAt ? new Date(trialEndsAt).getTime() > Date.now() : false;

  // SALES-03 / CVR-04: Pro→Business アップセル — show after 3+ runs
  const [currentPlan, setCurrentPlan] = useState<string>("");
  // ERRMSG-07: past_due状態を追跡して支払い失敗バナーを表示
  const [subscriptionStatus, setSubscriptionStatus] = useState<string>("active");
  const showProUpsell = currentPlan === "pro" && runs.length >= 3;
  const showStarterUpsell = currentPlan === "starter" && runs.length >= 2;
  const showFreeUpsell = currentPlan === "free" && runs.length >= 1;
  const showPaymentFailed = subscriptionStatus === "past_due";

  useEffect(() => {
    Promise.all([
      api.getRuns(undefined, 5).then((data) => setRuns(data.runs || [])).catch((err) => {
        console.error("[dashboard] Failed to fetch runs:", err);
        setFetchError("データの取得に失敗しました");
        setRuns([]);
      }),
      api.getProjects().then((data) => setProjects(Array.isArray(data) ? data.slice(0, 3) : [])).catch((err) => {
        console.error("[dashboard] Failed to fetch projects:", err);
        setFetchError("データの取得に失敗しました");
        setProjects([]);
      }),
    ]).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    import("@/lib/supabase/client").then(({ createClient }) => {
      const supabase = createClient();
      supabase
        .from("profiles")
        .select("trial_ends_at, plan, subscription_status")
        .eq("id", user.id)
        .maybeSingle()
        .then(({ data }) => {
          if (data?.trial_ends_at) setTrialEndsAt(data.trial_ends_at as string);
          if (data?.plan) setCurrentPlan(data.plan as string);
          if (data?.subscription_status) setSubscriptionStatus(data.subscription_status as string);
        });
    }).catch(() => {/* Supabase not configured */});
  }, [user]);

  const latestRun = runs[0];
  const isSampleMode = !loading && runs.length === 0;
  const latestScore = isSampleMode ? SAMPLE_SCORE : (latestRun?.overall_score ?? 85.2);

  return (
    <div className="w-full px-6 py-10">
      <Onboarding />

      {fetchError && (
        <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          {fetchError}
        </div>
      )}

      {/* ERRMSG-07: 支払い失敗バナー — past_due状態の場合に表示 */}
      {showPaymentFailed && (
        <div className="mb-6 px-5 py-4 rounded-xl border border-red-500/40 bg-red-500/[0.08] flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <AlertTriangle size={16} className="text-red-400 shrink-0" />
            <div>
              <span className="text-sm font-semibold text-red-300">
                {locale === "ja" ? "お支払いが失敗しました" : "Payment Failed"}
              </span>
              <p className="text-xs text-red-400/80 mt-0.5">
                {locale === "ja"
                  ? "お支払い情報を更新してください。更新しないとアクセスが制限される場合があります。"
                  : "Please update your payment information to avoid losing access."}
              </p>
            </div>
          </div>
          <Link href="/settings?tab=billing">
            <Button size="sm" variant="secondary" className="border-red-500/40 text-red-300 hover:bg-red-500/10">
              {locale === "ja" ? "支払い情報を更新" : "Update Payment"}
            </Button>
          </Link>
        </div>
      )}

      {/* SALES-03 / CVR-04: Pro→Business アップセルバナー */}
      {showProUpsell && !isTrialActive && (
        <div className="mb-6 px-5 py-4 rounded-xl border border-purple-500/30 bg-purple-500/[0.06] flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <TrendingUp size={16} className="text-purple-400 shrink-0" />
            <div>
              <span className="text-sm font-semibold text-purple-300">
                {locale === "ja" ? "Businessプランへアップグレード" : "Ready for Business?"}
              </span>
              <span className="block text-xs text-[var(--text-secondary)] mt-0.5">
                {locale === "ja"
                  ? "無制限シミュレーション・SSO・専任サポート・保険APIが利用可能です"
                  : "Unlock unlimited simulations, SSO, dedicated support, and Insurance API"}
              </span>
            </div>
          </div>
          <Link
            href="/pricing"
            className="text-xs font-semibold text-purple-300 border border-purple-500/30 px-3 py-1.5 rounded-lg hover:bg-purple-500/10 transition-colors whitespace-nowrap"
          >
            {locale === "ja" ? "プランを見る" : "View Business Plan"}
          </Link>
        </div>
      )}

      {/* Starter→Pro upsell */}
      {showStarterUpsell && !isTrialActive && (
        <div className="mb-6 px-5 py-4 rounded-xl border border-[var(--gold)]/30 bg-[var(--gold)]/[0.06] flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <TrendingUp size={16} className="text-[var(--gold)] shrink-0" />
            <div>
              <span className="text-sm font-semibold text-[var(--gold)]">
                {locale === "ja" ? "Proプランでもっと活用" : "Upgrade to Pro"}
              </span>
              <span className="block text-xs text-[var(--text-secondary)] mt-0.5">
                {locale === "ja"
                  ? "月100回のシミュレーション・DORAレポート・AI分析が利用可能です"
                  : "100 simulations/month, DORA reports, and AI-assisted analysis"}
              </span>
            </div>
          </div>
          <Link
            href="/pricing"
            className="text-xs font-semibold text-[var(--gold)] border border-[var(--gold)]/30 px-3 py-1.5 rounded-lg hover:bg-[var(--gold)]/10 transition-colors whitespace-nowrap"
          >
            {locale === "ja" ? "プランを見る" : "View Pro Plan"}
          </Link>
        </div>
      )}

      {/* Free→upgrade upsell */}
      {showFreeUpsell && !isTrialActive && (
        <div className="mb-6 px-5 py-4 rounded-xl border border-emerald-500/30 bg-emerald-500/[0.06] flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <TrendingUp size={16} className="text-emerald-400 shrink-0" />
            <div>
              <span className="text-sm font-semibold text-emerald-400">
                {locale === "ja" ? "有料プランで診断を強化" : "Upgrade for more simulations"}
              </span>
              <span className="block text-xs text-[var(--text-secondary)] mt-0.5">
                {locale === "ja"
                  ? "月5回の上限を超えて診断を実行。Starterは月30回、Proは月100回"
                  : "Go beyond 5/month. Starter: 30/month, Pro: 100/month"}
              </span>
            </div>
          </div>
          <Link
            href="/pricing"
            className="text-xs font-semibold text-emerald-400 border border-emerald-500/30 px-3 py-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors whitespace-nowrap"
          >
            {locale === "ja" ? "プランを見る" : "View Plans"}
          </Link>
        </div>
      )}

      {/* RETAIN-03: Trial banner — 期限切れ3日前は赤色の警告表示 */}
      {isTrialActive && (
        <div className={`mb-6 px-5 py-3.5 rounded-xl border flex items-center justify-between gap-4 flex-wrap ${trialDaysLeft <= 3 ? "border-red-500/40 bg-red-500/[0.07]" : "border-[var(--gold)]/30 bg-[var(--gold)]/[0.06]"}`}>
          <div className="flex items-center gap-2.5">
            <Clock size={16} className={trialDaysLeft <= 3 ? "text-red-400 shrink-0" : "text-[var(--gold)] shrink-0"} />
            <span className={`text-sm font-semibold ${trialDaysLeft <= 3 ? "text-red-400" : "text-[var(--gold)]"}`}>
              {trialDaysLeft <= 3
                ? (locale === "ja" ? `トライアル終了まで残り${trialDaysLeft}日` : `Trial ends in ${trialDaysLeft} day${trialDaysLeft !== 1 ? "s" : ""}!`)
                : "Business Trial —"}
            </span>
            {trialDaysLeft > 3 && (
              <span className="text-sm text-[var(--text-secondary)]">
                {trialDaysLeft} day{trialDaysLeft !== 1 ? "s" : ""} remaining. Full access to all features.
              </span>
            )}
            {trialDaysLeft <= 3 && (
              <span className="text-sm text-red-300 font-medium">
                {locale === "ja"
                  ? `あと${trialDaysLeft}日でトライアル終了 — 期限後はアクセスが制限されます。今すぐProにアップグレードして継続利用を確保してください。`
                  : `${trialDaysLeft} day${trialDaysLeft !== 1 ? "s" : ""} left — access will be restricted when your trial ends. Upgrade to Pro now to keep unlimited access.`}
              </span>
            )}
          </div>
          <Link
            href="/pricing"
            className={`text-xs font-semibold border px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${trialDaysLeft <= 3 ? "text-red-400 border-red-500/40 hover:bg-red-500/10" : "text-[var(--gold)] border-[var(--gold)]/30 hover:bg-[var(--gold)]/10"}`}
          >
            {locale === "ja" ? "今すぐアップグレード" : "Upgrade Now"}
          </Link>
        </div>
      )}

      {/* DEMO-05: デモデータと本番データの明確な区別バナー */}
      {isSampleMode && (
        <div className="mb-6 px-5 py-3.5 rounded-xl border border-blue-500/30 bg-blue-500/[0.06] flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2.5">
            <Info size={16} className="text-blue-400 shrink-0" />
            <div>
              <span className="text-xs font-bold text-blue-400 uppercase tracking-wider mr-2">
                {locale === "ja" ? "サンプルデータ" : "SAMPLE DATA"}
              </span>
              <span className="text-sm text-[var(--text-secondary)]">
                {locale === "ja"
                  ? "実際のデータではありません。自分のインフラで試してみましょう。"
                  : "This is not real data. Run your first simulation to see real results."}
              </span>
            </div>
          </div>
          <Link
            href="/simulate"
            className="flex items-center gap-1.5 text-xs font-semibold text-blue-400 border border-blue-500/30 px-3 py-1.5 rounded-lg hover:bg-blue-500/10 transition-colors whitespace-nowrap"
          >
            {locale === "ja" ? "シミュレーションを実行 →" : "Run Simulation →"}
          </Link>
        </div>
      )}

      {/* UX-02: 初回ユーザー向け — シミュレーション開始への大きな導線 */}
      {!loading && runs.length === 0 && (
        <Link href="/simulate" className="block mb-6">
          <div className="group p-6 rounded-2xl border-2 border-dashed border-[var(--gold)]/30 bg-[var(--gold)]/[0.03] hover:border-[var(--gold)]/60 hover:bg-[var(--gold)]/[0.06] transition-all text-center cursor-pointer">
            <div className="w-14 h-14 rounded-2xl bg-[var(--gold)]/10 border border-[var(--gold)]/20 flex items-center justify-center mx-auto mb-4 group-hover:bg-[var(--gold)]/20 transition-all">
              <Zap size={24} className="text-[var(--gold)]" />
            </div>
            <h3 className="text-lg font-bold mb-1">
              {locale === "ja" ? "最初のシミュレーションを実行する" : "Run Your First Simulation"}
            </h3>
            <p className="text-sm text-[var(--text-secondary)] mb-3">
              {locale === "ja"
                ? "サンプルトポロジーを選んで、今すぐ2,000+シナリオを実行。本番環境には一切触れません。"
                : "Pick a sample topology and run 2,000+ chaos scenarios now — no production access required."}
            </p>
            <span className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--gold)]">
              {locale === "ja" ? "シミュレーションを開始" : "Start Simulation"}
              <ArrowRight size={14} />
            </span>
          </div>
        </Link>
      )}

      {/* UX-03: オンボーディング後の次ステップ — runs完了後に表示 */}
      {!loading && runs.length === 1 && (
        <div className="mb-6 p-5 rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04]">
          <p className="text-sm font-bold text-emerald-300 mb-2">
            {locale === "ja" ? "シミュレーション完了！次のステップ" : "Great first simulation! Next steps:"}
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/reports" className="text-xs font-semibold text-emerald-400 border border-emerald-500/20 px-3 py-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors">
              {locale === "ja" ? "レポートを見る →" : "View Full Report →"}
            </Link>
            <Link href="/simulate" className="text-xs font-semibold text-emerald-400 border border-emerald-500/20 px-3 py-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors">
              {locale === "ja" ? "別のトポロジーで試す →" : "Try Another Topology →"}
            </Link>
            <Link href="/pricing" className="text-xs font-semibold text-emerald-400 border border-emerald-500/20 px-3 py-1.5 rounded-lg hover:bg-emerald-500/10 transition-colors">
              {locale === "ja" ? "Proプランで制限解除 →" : "Unlock Pro Plan →"}
            </Link>
          </div>
        </div>
      )}

      {/* UX-03: Getting Started Checklist (extracted component) */}
      <GettingStarted hasRun={runs.length > 0} locale={locale} />

      {/* Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
          <p className="text-[var(--text-secondary)] text-sm">
            {t.welcomeBack}{user?.user_metadata?.full_name ? `, ${user.user_metadata.full_name}` : ""}
          </p>
        </div>
        <Link href="/simulate">
          <Button>
            <Zap size={16} />
            {t.newSimulation}
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid md:grid-cols-4 gap-6 mb-10">
        <Card className="flex items-center gap-6">
          <ScoreRing score={latestScore} size={100} />
          <div>
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider mb-1">{t.resilienceScore}</p>
            <p className="text-lg font-bold">{latestScore.toFixed(1)} / 100</p>
            <Badge variant={latestScore >= 90 ? "green" : latestScore >= 70 ? "gold" : "red"}>
              {latestScore >= 90 ? t.excellent : latestScore >= 70 ? t.good : t.needsWork}
            </Badge>
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <TrendingUp size={20} className="text-emerald-400" />
            </div>
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.availability}</p>
          </div>
          <p className="text-2xl font-bold font-mono">99.99%</p>
          <p className="text-xs text-[var(--text-muted)] mt-1">4.00 {t.nines}</p>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-[var(--gold)]/10 flex items-center justify-center">
              <Shield size={20} className="text-[var(--gold)]" />
            </div>
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.scenarios}</p>
          </div>
          <p className="text-2xl font-bold font-mono">
            {isSampleMode ? SAMPLE_COMPONENTS : (latestRun?.total_scenarios ?? 152)}
          </p>
          <div className="flex items-center gap-2 mt-1">
            {isSampleMode ? (
              <span className="text-xs text-[var(--text-muted)]">コンポーネント数</span>
            ) : (
              <>
                <span className="text-xs text-emerald-400">{latestRun?.scenarios_passed ?? 147} {t.passed}</span>
                <span className="text-xs text-[var(--text-muted)]">/</span>
                <span className="text-xs text-red-400">{latestRun?.scenarios_failed ?? 5} {t.failed}</span>
              </>
            )}
          </div>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg bg-red-500/10 flex items-center justify-center">
              <AlertTriangle size={20} className="text-red-400" />
            </div>
            <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">{t.criticalIssues}</p>
          </div>
          <p className="text-2xl font-bold font-mono">
            {isSampleMode ? SAMPLE_CRITICAL : 3}
          </p>
          <p className="text-xs text-red-400 mt-1">
            {isSampleMode
              ? `WARNING ${SAMPLE_WARNING}件`
              : t.requiresAttention}
          </p>
        </Card>
      </div>

      {/* CHURN-03 / KPI-02: Score Improvement Trend — value visualization */}
      {runs.length >= 2 && (() => {
        const recent = runs.slice(0, 5).reverse();
        const first = recent[0].overall_score;
        const last = recent[recent.length - 1].overall_score;
        const delta = last - first;
        const improved = delta > 0;
        return (
          <Card className="mb-10">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-bold flex items-center gap-2">
                <Activity size={18} className="text-emerald-400" />
                {locale === "ja" ? "スコア改善トレンド" : "Resilience Score Trend"}
              </h2>
              {improved ? (
                <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-1 rounded-full">
                  +{delta.toFixed(1)} {locale === "ja" ? "pt 改善" : "pts improved"}
                </span>
              ) : (
                <span className="text-xs font-semibold text-[var(--gold)] bg-[var(--gold)]/10 px-2 py-1 rounded-full">
                  {locale === "ja" ? "シミュレーションを重ねると改善が見えます" : "Keep simulating to track progress"}
                </span>
              )}
            </div>
            <div className="flex items-end gap-2 h-16">
              {recent.map((run, i) => {
                const h = Math.round((run.overall_score / 100) * 64);
                const isLast = i === recent.length - 1;
                return (
                  <div key={run.id} className="flex-1 flex flex-col items-center gap-1">
                    <div
                      className={`w-full rounded-t-md transition-all ${isLast ? "bg-[var(--gold)]" : "bg-[var(--border-color)]"}`}
                      style={{ height: h }}
                      title={`${run.overall_score.toFixed(1)}`}
                    />
                    <span className="text-[10px] text-[var(--text-muted)] font-mono">{run.overall_score.toFixed(0)}</span>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-[var(--text-muted)] mt-2">
              {locale === "ja"
                ? "過去5回のシミュレーションのスコア推移。毎回実行するほど弱点が明確になります。"
                : "Score across last 5 simulations. Each run identifies new weaknesses to harden."}
            </p>
          </Card>
        );
      })()}

      {/* 3-Layer Bar Chart */}
      <Card className="mb-10">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <BarChart3 size={20} className="text-[var(--gold)]" />
            {t.threeLayerModel}
          </h2>
        </div>
        <div className="space-y-4">
          {[
            { label: t.software, value: 4.0, max: 7, color: "bg-emerald-400" },
            { label: t.hardware, value: 5.91, max: 7, color: "bg-[var(--gold)]" },
            { label: t.theoretical, value: 6.65, max: 7, color: "bg-blue-400" },
          ].map((layer) => (
            <div key={layer.label} className="grid grid-cols-[80px_1fr_60px] items-center gap-4">
              <span className="text-sm text-[var(--text-muted)]">{layer.label}</span>
              <div className="h-3 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${layer.color} transition-all duration-1000`}
                  style={{ width: `${(layer.value / layer.max) * 100}%` }}
                />
              </div>
              <span className="text-sm font-mono font-semibold text-right">{layer.value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* Your Projects */}
      {projects.length > 0 && (
        <Card className="mb-10">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <FolderKanban size={20} className="text-[var(--gold)]" />
              {tProjects.yourProjects}
            </h2>
            <Link href="/projects" className="text-sm text-[var(--gold)] hover:underline flex items-center gap-1">
              {t.viewAll} <ArrowRight size={14} />
            </Link>
          </div>
          <div className="grid md:grid-cols-3 gap-4">
            {projects.map((project) => {
              const score = project.last_score;
              const scoreColor = score == null ? "#64748b" : score >= 90 ? "#10B981" : score >= 70 ? "#FFD700" : "#ef4444";
              return (
                <Link key={project.id} href={`/projects/${project.id}`}>
                  <div className="p-4 rounded-xl bg-white/[0.02] border border-[var(--border-color)] hover:border-[var(--gold)]/30 transition-colors cursor-pointer">
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-semibold text-sm truncate flex-1 mr-2">{project.name}</p>
                      {score != null && (
                        <span className="text-lg font-bold font-mono shrink-0" style={{ color: scoreColor }}>
                          {score.toFixed(0)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--text-muted)] line-clamp-1">{project.description || "—"}</p>
                    <p className="text-xs text-[var(--text-muted)] mt-2">
                      {project.run_count ?? 0} {tProjects.runCount}
                      {project.last_run_at && (
                        <> · {new Date(project.last_run_at).toLocaleDateString()}</>
                      )}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        </Card>
      )}

      {/* Recent Runs */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold flex items-center gap-2">
            <Clock size={20} className="text-[var(--gold)]" />
            {t.recentSimulations}
          </h2>
          <Link href="/results" className="text-sm text-[var(--gold)] hover:underline flex items-center gap-1">
            {t.viewAll} <ArrowRight size={14} />
          </Link>
        </div>
        {loading ? (
          <div className="text-center py-8 text-[var(--text-muted)]">{t.loading}</div>
        ) : runs.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-[var(--text-muted)] mb-4">{t.noSimulations}</p>
            <Link href="/simulate">
              <Button size="sm"><Zap size={14} /> {t.runSimulation}</Button>
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-color)]">
                  <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.date}</th>
                  <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.score}</th>
                  <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.availability}</th>
                  <th scope="col" className="text-left py-3 px-2 text-[var(--text-muted)] font-medium">{t.scenariosCol}</th>
                  <th scope="col" className="text-right py-3 px-2 text-[var(--text-muted)] font-medium">{t.status}</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="border-b border-[var(--border-color)]/50 hover:bg-white/[0.02]">
                    <td className="py-3 px-2 text-[var(--text-secondary)]">
                      {new Date(run.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-2 font-mono font-semibold">
                      {run.overall_score.toFixed(1)}
                    </td>
                    <td className="py-3 px-2 text-[var(--text-secondary)]">{run.availability_estimate}</td>
                    <td className="py-3 px-2 text-[var(--text-secondary)]">
                      <span className="text-emerald-400">{run.scenarios_passed}</span>
                      {" / "}
                      <span>{run.total_scenarios}</span>
                    </td>
                    <td className="py-3 px-2 text-right">
                      <Badge variant={run.scenarios_failed === 0 ? "green" : "yellow"}>
                        {run.scenarios_failed === 0 ? t.allPassed : `${run.scenarios_failed} ${t.xFailed}`}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
