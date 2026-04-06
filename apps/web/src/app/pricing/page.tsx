"use client";

import Link from "next/link";
import { Check, Minus, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useLocale } from "@/lib/useLocale";

type BillingCycle = "monthly" | "annual";

interface Plan {
  name: string;
  monthlyPrice: number;
  annualMonthlyPrice: number; // per-month equivalent when billed annually
  annualTotal: number;
  desc: string;
  features: string[];
  disabledFeatures: string[];
  cta: string;
  ctaHref: string;
  popular: boolean;
  stripePlan: "pro" | "business" | null;
  sla: string | null;
}

const plans: Plan[] = [
  {
    name: "Business",
    monthlyPrice: 999,
    annualMonthlyPrice: 799,   // 999 * 12 * 0.8 / 12 ≈ 799
    annualTotal: 9590,         // 999 * 12 * 0.8 rounded
    desc: "For enterprises needing unlimited access, SSO, and dedicated support.",
    features: ["Unlimited simulations", "Unlimited components", "Everything in Pro", "DORA report + Insurance API", "Custom SSO / SAML", "Dedicated support (1h)", "Prometheus integration", "On-premise deployment"],
    disabledFeatures: [],
    cta: "Get a Quote",
    ctaHref: "/contact?plan=business",
    popular: false,
    stripePlan: null,
    sla: "99.9% Uptime SLA",
  },
  {
    name: "Pro",
    monthlyPrice: 299,
    annualMonthlyPrice: 239,   // 299 * 12 * 0.8 / 12 ≈ 239
    annualTotal: 2869,         // 299 * 12 * 0.8 rounded
    desc: "For teams that need DORA compliance reports and higher limits.",
    features: ["14-day free trial", "100 simulations / month", "Up to 50 components", "Everything in Free", "DORA report export (PDF)", "AI-powered analysis", "Email support (24h)"],
    disabledFeatures: ["Insurance API", "Custom SSO"],
    cta: "Start Free Trial",
    ctaHref: "/login?plan=pro",
    popular: true,
    stripePlan: "pro",
    sla: "99.9% Uptime SLA",
  },
  {
    name: "Starter",
    monthlyPrice: 99,
    annualMonthlyPrice: 79,
    annualTotal: 949,
    desc: "For small teams getting started with reliability testing. 30 simulations covers most ongoing monitoring needs.",
    features: ["30 simulations / month", "Up to 20 components", "Everything in Free", "Email support (48h)", "Basic remediation suggestions"],
    disabledFeatures: ["DORA report export", "AI-powered analysis", "Custom SSO"],
    cta: "Start Starter",
    ctaHref: "/login?plan=starter",
    popular: false,
    stripePlan: null,
    sla: null,
  },
  {
    name: "Free",
    monthlyPrice: 0,
    annualMonthlyPrice: 0,
    annualTotal: 0,
    desc: "Perfect for individual engineers exploring chaos engineering. 5 simulations covers most proof-of-concept evaluations.",
    features: ["5 simulations / month", "Up to 5 components", "100+ simulation engines", "N-Layer Availability Model", "HTML reports", "Community support"],
    disabledFeatures: ["DORA report export", "Custom SSO"],
    cta: "Get Started Free",
    ctaHref: "/login",
    popular: false,
    stripePlan: null,
    sla: null,
  },
];

const featureComparison = [
  { name: "Simulations / month", free: "5", starter: "30", pro: "100", business: "Unlimited" },
  { name: "Components", free: "5", starter: "20", pro: "50", business: "Unlimited" },
  { name: "Simulation engines", free: "100+", starter: "100+", pro: "100+", business: "100+" },
  { name: "N-Layer Model", free: true, starter: true, pro: true, business: true },
  { name: "DORA report export", free: false, starter: false, pro: "PDF", business: "PDF + API" },
  { name: "Insurance API", free: false, starter: false, pro: false, business: true },
  { name: "AI-powered analysis", free: false, starter: false, pro: true, business: true },
  { name: "Custom SSO / SAML", free: false, starter: false, pro: false, business: true },
  { name: "99.9% Uptime SLA", free: false, starter: false, pro: true, business: true },
  { name: "Support", free: "Community", starter: "Email (48h)", pro: "Email (24h)", business: "Dedicated (1h)" },
];

function CellValue({ value }: { value: string | boolean }) {
  if (value === true) return <Check size={18} className="text-emerald-400 mx-auto" />;
  if (value === false) return <Minus size={18} className="text-[var(--text-muted)] mx-auto" />;
  return <span>{value}</span>;
}

export default function PricingPage() {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingCycle>("monthly");
  const [checkoutError, setCheckoutError] = useState<{ plan: "pro" | "business"; message: string } | null>(null);
  // COPY-NEW-06: ロケール検出して日本語UIに対応
  const locale = useLocale();
  const isJa = locale === "ja";

  const handleCheckout = async (plan: "pro" | "business") => {
    setLoadingPlan(plan);
    setCheckoutError(null);
    try {
      const interval = billing === "annual" ? "year" : "month";
      const { url } = await api.createCheckoutSession(plan, interval);
      if (url) {
        window.location.href = url;
      }
    } catch {
      // Stripe not configured — show retry UI instead of silent redirect
      setCheckoutError({ plan, message: "決済処理に失敗しました。再試行するか、サポートにお問い合わせください。" });
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="w-full px-6 py-20">
      {/* ERRMSG-07: Payment failure retry UI */}
      {checkoutError && (
        <div role="alert" className="mb-6 p-4 rounded-lg border border-red-500/40 bg-red-500/10 flex items-start gap-3">
          <span className="text-red-400 text-lg leading-none mt-0.5">&#9888;</span>
          <div className="flex-1">
            <p className="text-red-300 text-sm font-medium">{checkoutError.message}</p>
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => handleCheckout(checkoutError.plan)}
                disabled={loadingPlan !== null}
                className="px-3 py-1.5 text-xs font-medium rounded bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/30 transition-colors disabled:opacity-50"
              >
                再試行
              </button>
              <a
                href="mailto:support@faultray.io?subject=決済エラー"
                className="px-3 py-1.5 text-xs font-medium rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] border border-[var(--border-color)] transition-colors"
              >
                サポートに連絡
              </a>
            </div>
          </div>
          <button onClick={() => setCheckoutError(null)} aria-label="閉じる" className="text-[var(--text-muted)] hover:text-[var(--text-primary)] text-sm leading-none">&times;</button>
        </div>
      )}
      <div className="text-center mb-10">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
          {isJa ? "信頼性に投資し、障害が発生する前に防ぐ。" : "Invest in reliability. Prevent the outage before it costs you."}
        </h1>
        {/* PSYCH-02: Loss aversion framing — emphasize cost of NOT having FaultRay */}
        <p className="text-lg text-[var(--text-secondary)]">
          {isJa ? (
            <>中規模SaaSでは1時間のダウンタイムで{" "}<span className="text-[var(--text-primary)] font-semibold">1,000万円以上</span>の損失。FaultRayが弱点を先に見つけます。</>
          ) : (
            <>A single hour of downtime costs{" "}<span className="text-[var(--text-primary)] font-semibold">$100,000+</span> for mid-size SaaS. FaultRay finds the weak points before they find you.</>
          )}
        </p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[var(--gold)]/10 border border-[var(--gold)]/20">
            <span className="text-sm font-semibold text-[var(--gold)]">14-day free trial on Pro</span>
          </div>
          {/* CVR-03: Explicitly state no credit card required */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">No credit card required</span>
          </div>
          {/* COMPDIFF-03: Security posture badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-500/10 border border-blue-500/20">
            <ShieldCheck size={14} className="text-blue-400" />
            <span className="text-sm font-semibold text-blue-400">OWASP-hardened · Data encrypted at rest</span>
          </div>
        </div>
        {/* CVR-05: Social proof micro-stats */}
        <div className="mt-5 flex flex-wrap items-center justify-center gap-6 text-sm text-[var(--text-muted)]">
          <span><span className="font-bold text-[var(--text-primary)]">2,000+</span> simulations run/month</span>
          <span className="hidden sm:block">·</span>
          <span><span className="font-bold text-[var(--text-primary)]">$0</span> to get started</span>
          <span className="hidden sm:block">·</span>
          <span>Cancel anytime</span>
        </div>
        {/* JP-05: 日本語サポートの保証を明示 */}
        <div className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full bg-blue-500/10 border border-blue-500/20">
          <span className="text-sm font-semibold text-blue-400">日本語サポート対応 — 日本語でのメール・稟議書サポートを提供</span>
        </div>
      </div>

      {/* Billing toggle */}
      <div className="flex items-center justify-center gap-4 mb-12">
        <span className={`text-sm font-medium transition-colors ${billing === "monthly" ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]"}`}>
          {isJa ? "月額" : "Monthly"}
        </span>
        <button
          role="switch"
          aria-checked={billing === "annual"}
          aria-label={isJa ? "年額と月額を切り替え" : "Toggle annual billing"}
          onClick={() => setBilling((b) => (b === "monthly" ? "annual" : "monthly"))}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gold)] ${
            billing === "annual" ? "bg-[var(--gold)]" : "bg-[var(--border-color)]"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              billing === "annual" ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <span className={`text-sm font-medium transition-colors ${billing === "annual" ? "text-[var(--text-primary)]" : "text-[var(--text-muted)]"}`}>
          {isJa ? "年額" : "Annual"}
        </span>
        {billing === "annual" && (
          <span className="px-2 py-0.5 text-xs font-bold text-white bg-[var(--gold)] rounded-full">
            {isJa ? "20%お得" : "SAVE 20%"}
          </span>
        )}
      </div>

      {/* Plans */}
      <div className="grid md:grid-cols-4 gap-6 max-w-[1300px] mx-auto mb-20">
        {plans.map((plan) => {
          const displayPrice = billing === "annual" ? plan.annualMonthlyPrice : plan.monthlyPrice;
          // JP-STARTER: Starter plan Japanese price display
          const jaMonthlyPrice: Record<string, string> = { Starter: "¥15,000" };
          const jaAnnualMonthlyPrice: Record<string, string> = { Starter: "¥11,900" };
          return (
            <div key={plan.name} className={`relative p-9 rounded-2xl border flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${plan.popular ? "border-[var(--gold)] bg-gradient-to-b from-[var(--gold)]/[0.04] to-[var(--bg-card)] shadow-md" : "border-[var(--border-color)] bg-[var(--bg-card)]"}`}>
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 text-xs font-bold text-white bg-[var(--gold)] rounded-full uppercase tracking-wide">
                  Most Popular
                </div>
              )}
              <div className="text-lg font-bold mb-2">{plan.name}</div>

              {/* SLA badge */}
              {plan.sla && (
                <div className="flex items-center gap-1.5 mb-4">
                  <ShieldCheck size={13} className="text-emerald-400 shrink-0" />
                  <span className="text-xs font-semibold text-emerald-400">{plan.sla}</span>
                </div>
              )}

              {isJa && plan.name in jaMonthlyPrice ? (
                <div className="flex items-baseline gap-0.5 mb-1">
                  <span className="text-4xl font-extrabold tracking-tight">
                    {billing === "annual" ? jaAnnualMonthlyPrice[plan.name] : jaMonthlyPrice[plan.name]}
                  </span>
                  <span className="text-sm text-[var(--text-muted)] ml-1">/月</span>
                </div>
              ) : (
                <div className="flex items-baseline gap-0.5 mb-1">
                  <span className="text-xl font-semibold text-[var(--text-secondary)]">$</span>
                  <span className="text-4xl font-extrabold tracking-tight">{displayPrice}</span>
                  <span className="text-sm text-[var(--text-muted)] ml-1">/month</span>
                </div>
              )}
              {billing === "annual" && plan.annualTotal > 0 && (
                <p className="text-xs text-[var(--text-muted)] mb-4">
                  Billed annually (${plan.annualTotal.toLocaleString()}/yr)
                </p>
              )}
              {!(billing === "annual" && plan.annualTotal > 0) && <div className="mb-4" />}

              <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-6">{plan.desc}</p>
              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-[var(--text-secondary)]">
                    <Check size={16} className="text-emerald-400 shrink-0" />{f}
                  </li>
                ))}
                {plan.disabledFeatures.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-[var(--text-secondary)] opacity-40">
                    <Minus size={16} className="shrink-0" />{f}
                  </li>
                ))}
              </ul>
              {plan.stripePlan ? (
                <button
                  onClick={() => handleCheckout(plan.stripePlan!)}
                  disabled={loadingPlan === plan.stripePlan}
                  className={`w-full text-center py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 ${plan.popular ? "bg-[var(--gold)] text-white hover:bg-[#044a99] disabled:opacity-70" : "border border-[var(--border-color)] text-[var(--text-primary)] hover:border-[var(--text-muted)] disabled:opacity-70"}`}
                >
                  {loadingPlan === plan.stripePlan ? (
                    <><Loader2 size={16} className="animate-spin" /> Processing...</>
                  ) : (
                    plan.cta
                  )}
                </button>
              ) : (
                <Link
                  href={plan.ctaHref}
                  className={`w-full text-center py-3 rounded-xl font-semibold transition-all block ${plan.popular ? "bg-[var(--gold)] text-white hover:bg-[#044a99]" : "border border-[var(--border-color)] text-[var(--text-primary)] hover:border-[var(--text-muted)]"}`}
                >
                  {plan.cta}
                </Link>
              )}
            </div>
          );
        })}
      </div>

      {/* Annual savings callout */}
      {billing === "annual" && (
        <div className="max-w-[1000px] mx-auto mb-16">
          <div className="p-5 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.04] flex items-center gap-3">
            <ShieldCheck size={20} className="text-emerald-400 shrink-0" />
            <p className="text-sm text-emerald-300">
              <strong>Annual billing saves you 20%.</strong> Pro plan: save $719/yr. Business plan: save $2,398/yr.
              All annual plans include 99.9% Uptime SLA guarantee.
            </p>
          </div>
        </div>
      )}

      {/* PRICE-02: Value anchoring — cost of $299/mo vs. cost of 1 downtime incident */}
      <div className="max-w-[900px] mx-auto mb-12">
        <div className="grid md:grid-cols-3 gap-4 text-center">
          {[
            { label: "Average cost of 1 hour downtime", value: "$100,000+", color: "text-red-400", icon: "⚠️" },
            { label: "FaultRay Pro — per month", value: "$299", color: "text-[var(--gold)]", icon: "✅" },
            { label: "ROI if it prevents 1 incident/year", value: "33,000%+", color: "text-emerald-400", icon: "📈" },
          ].map((stat) => (
            <div key={stat.label} className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]">
              <p className="text-2xl mb-1">{stat.icon}</p>
              <p className={`text-2xl font-extrabold font-mono mb-1 ${stat.color}`}>{stat.value}</p>
              <p className="text-xs text-[var(--text-muted)]">{stat.label}</p>
            </div>
          ))}
        </div>
        <p className="text-center text-xs text-[var(--text-muted)] mt-3">
          Industry average: $5,600/minute downtime cost (Gartner, 2024). One incident prevented pays for 27+ years of Pro.
        </p>
      </div>

      {/* Feature Comparison Table */}
      <div className="max-w-[900px] mx-auto">
        <h2 className="text-xl font-bold text-center mb-8">Feature Comparison</h2>
        <div className="overflow-x-auto rounded-2xl border border-[var(--border-color)]">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th scope="col" className="px-5 py-4 text-left bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">Feature</th>
                <th scope="col" className="px-5 py-4 text-center bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">Free</th>
                <th scope="col" className="px-5 py-4 text-center bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">Starter</th>
                <th scope="col" className="px-5 py-4 text-center bg-[var(--gold)]/[0.06] text-[var(--gold)] font-semibold">Pro</th>
                <th scope="col" className="px-5 py-4 text-center bg-[var(--bg-tertiary)] text-[var(--text-secondary)] font-semibold">Business</th>
              </tr>
            </thead>
            <tbody>
              {featureComparison.map((row, i) => (
                <tr key={row.name} className={i < featureComparison.length - 1 ? "border-b border-[var(--border-color)]" : ""}>
                  <td className="px-5 py-4 font-medium text-[var(--text-primary)] bg-[var(--bg-card)]">{row.name}</td>
                  <td className="px-5 py-4 text-center bg-[var(--bg-card)] text-[var(--text-secondary)]"><CellValue value={row.free} /></td>
                  <td className="px-5 py-4 text-center bg-[var(--bg-card)] text-[var(--text-secondary)]"><CellValue value={row.starter} /></td>
                  <td className="px-5 py-4 text-center bg-[var(--gold)]/[0.03] text-[var(--text-primary)]"><CellValue value={row.pro} /></td>
                  <td className="px-5 py-4 text-center bg-[var(--bg-card)] text-[var(--text-secondary)]"><CellValue value={row.business} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* SLA note */}
      <div className="max-w-[900px] mx-auto mt-8">
        <p className="text-xs text-[var(--text-muted)] text-center">
          99.9% Uptime SLA applies to Pro and Business plans. Service status:{" "}
          <a
            href="https://status.faultray.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            status.faultray.com
          </a>
          . View our{" "}
          <Link href="/terms" className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Terms of Service
          </Link>{" "}
          for full SLA details.
        </p>
      </div>

      {/* SALES-02: プロフェッショナルサービス（対面診断） */}
      <div className="max-w-[900px] mx-auto mt-16 mb-8">
        <div className="text-center mb-8">
          <span className="inline-block px-3 py-1 text-xs font-semibold text-[var(--gold)] border border-[var(--gold)]/20 rounded-full bg-[var(--gold)]/5 mb-3">
            {isJa ? "NEW" : "NEW"}
          </span>
          <h2 className="text-xl font-bold tracking-tight mb-2">
            {isJa ? "プロフェッショナルサービス" : "Professional Services"}
          </h2>
          <p className="text-sm text-[var(--text-secondary)] max-w-[540px] mx-auto">
            {isJa
              ? "SaaSのセルフサービスに加え、専門エンジニアによる対面診断・レポート作成を承ります。"
              : "In addition to our self-service SaaS, our engineers provide hands-on assessment and reporting."}
          </p>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          {/* セルフサービス */}
          <div className="p-6 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)]">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-8 h-8 flex items-center justify-center rounded-lg bg-[var(--gold)]/10 text-[var(--gold)] text-sm font-bold">S</span>
              <h3 className="font-bold text-[var(--text-primary)]">{isJa ? "セルフサービス（SaaS）" : "Self-Service (SaaS)"}</h3>
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-4">
              {isJa
                ? "今すぐサインアップして、ご自身でシミュレーションを実行。レポートも自動生成。"
                : "Sign up now, run simulations yourself. Reports auto-generated."}
            </p>
            <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
              {[
                isJa ? "無料〜¥150,000/月" : "Free – $999/mo",
                isJa ? "即日開始・クレカ不要" : "Start today, no credit card",
                isJa ? "自動レポート生成" : "Automated report generation",
                isJa ? "24時間利用可能" : "Available 24/7",
              ].map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <Check size={14} className="text-emerald-400 shrink-0" />{f}
                </li>
              ))}
            </ul>
          </div>
          {/* プロフェッショナル */}
          <div className="p-6 rounded-2xl border border-[var(--gold)]/20 bg-gradient-to-br from-[var(--gold)]/[0.03] to-[var(--bg-card)]">
            <div className="flex items-center gap-2 mb-3">
              <span className="w-8 h-8 flex items-center justify-center rounded-lg bg-[var(--gold)]/10 text-[var(--gold)] text-sm font-bold">P</span>
              <h3 className="font-bold text-[var(--text-primary)]">{isJa ? "プロフェッショナル診断" : "Professional Assessment"}</h3>
            </div>
            <div className="mb-4">
              <span className="text-2xl font-extrabold text-[var(--text-primary)]">{isJa ? "¥150,000〜" : "$1,000+"}</span>
              <span className="text-sm text-[var(--text-muted)] ml-1">{isJa ? "/回" : "/engagement"}</span>
            </div>
            <p className="text-sm text-[var(--text-secondary)] mb-4">
              {isJa
                ? "テレビ朝日グループ6年の経験を持つエンジニアが、御社インフラを直接診断しレポートを作成します。"
                : "Our engineers with 6+ years of media infrastructure experience assess your systems and deliver a custom report."}
            </p>
            <ul className="space-y-2 text-sm text-[var(--text-secondary)]">
              {[
                isJa ? "専門エンジニアによる対面診断" : "Hands-on assessment by expert engineers",
                isJa ? "カスタムレポート・改善提案" : "Custom report with remediation plan",
                isJa ? "経営層向け報告資料作成" : "Executive summary included",
                isJa ? "稟議書テンプレート提供" : "Procurement documentation support",
              ].map((f) => (
                <li key={f} className="flex items-center gap-2">
                  <Check size={14} className="text-[var(--gold)] shrink-0" />{f}
                </li>
              ))}
            </ul>
            <Link
              href="/contact?service=professional"
              className="mt-5 w-full text-center py-2.5 rounded-xl font-semibold border border-[var(--gold)]/30 text-[var(--gold)] hover:bg-[var(--gold)]/10 transition-all block text-sm"
            >
              {isJa ? "お問い合わせ" : "Contact Us"}
            </Link>
          </div>
        </div>
      </div>

      {/* SALES-03: Pro→Business アップセル — 比較CTA */}
      <div className="max-w-[900px] mx-auto mt-16 p-6 rounded-2xl border border-purple-500/20 bg-purple-500/[0.04]">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)] mb-1">Already on Pro? Unlock more with Business.</h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Unlimited simulations, custom SSO, dedicated Slack support, Insurance API, and on-premise deployment.
              Enterprises choose Business for compliance-critical workloads.
            </p>
          </div>
          <Link
            href="/contact?plan=business"
            className="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl border border-purple-500/30 text-purple-300 text-sm font-semibold hover:bg-purple-500/10 transition-colors"
          >
            Talk to Sales
          </Link>
        </div>
      </div>

      {/* PAY-01: 請求書払い（銀行振込）対応のお知らせ */}
      <div className="max-w-[900px] mx-auto mt-8 p-4 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] flex items-start gap-3">
        <span className="text-lg shrink-0">🏦</span>
        <div>
          <p className="text-sm text-[var(--text-secondary)]">
            <span className="text-[var(--text-primary)] font-semibold">請求書払い・銀行振込に対応しています。</span>{" "}
            年間契約をご希望の企業様は <a href="mailto:sales@faultray.com" className="text-[var(--gold)] hover:underline">sales@faultray.com</a> までお問い合わせください。
            インボイス制度対応の適格請求書を発行いたします。
          </p>
          <p className="text-xs text-[var(--text-muted)] mt-1">Invoice payment (bank transfer) available for annual plans. Contact us for enterprise billing.</p>
        </div>
      </div>

      {/* Footer links */}
      <div className="max-w-[900px] mx-auto mt-8 pt-8 border-t border-[var(--border-color)] flex flex-wrap justify-center gap-6 text-sm text-[var(--text-muted)]">
        <Link href="/privacy" className="hover:text-[var(--text-primary)] transition-colors">Privacy Policy</Link>
        <Link href="/terms" className="hover:text-[var(--text-primary)] transition-colors">Terms of Service</Link>
        <Link href="/tokushoho" className="hover:text-[var(--text-primary)] transition-colors">特定商取引法に基づく表記</Link>
        <a href="mailto:sales@faultray.com" className="hover:text-[var(--text-primary)] transition-colors">Contact Sales</a>
      </div>
    </div>
  );
}
