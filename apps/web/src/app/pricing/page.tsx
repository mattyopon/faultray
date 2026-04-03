"use client";

import Link from "next/link";
import { Check, Minus, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";

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
    name: "Free",
    monthlyPrice: 0,
    annualMonthlyPrice: 0,
    annualTotal: 0,
    desc: "Perfect for individual engineers exploring chaos engineering.",
    features: ["5 simulations / month", "Up to 5 components", "100+ simulation engines", "N-Layer Availability Model", "HTML reports", "Community support"],
    disabledFeatures: ["DORA report export", "Custom SSO"],
    cta: "Get Started Free",
    ctaHref: "/login",
    popular: false,
    stripePlan: null,
    sla: null,
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
    name: "Business",
    monthlyPrice: 999,
    annualMonthlyPrice: 799,   // 999 * 12 * 0.8 / 12 ≈ 799
    annualTotal: 9590,         // 999 * 12 * 0.8 rounded
    desc: "For enterprises needing unlimited access, SSO, and dedicated support.",
    features: ["Unlimited simulations", "Unlimited components", "Everything in Pro", "DORA report + Insurance API", "Custom SSO / SAML", "Dedicated support (1h)", "Prometheus integration", "On-premise deployment"],
    disabledFeatures: [],
    cta: "Contact Us",
    ctaHref: "mailto:sales@faultray.com",
    popular: false,
    stripePlan: null,
    sla: "99.9% Uptime SLA",
  },
];

const featureComparison = [
  { name: "Simulations / month", free: "5", pro: "100", business: "Unlimited" },
  { name: "Components", free: "5", pro: "50", business: "Unlimited" },
  { name: "Simulation engines", free: "100+", pro: "100+", business: "100+" },
  { name: "N-Layer Model", free: true, pro: true, business: true },
  { name: "DORA report export", free: false, pro: "PDF", business: "PDF + API" },
  { name: "Insurance API", free: false, pro: false, business: true },
  { name: "AI-powered analysis", free: false, pro: true, business: true },
  { name: "Custom SSO / SAML", free: false, pro: false, business: true },
  { name: "99.9% Uptime SLA", free: false, pro: true, business: true },
  { name: "Support", free: "Community", pro: "Email (24h)", business: "Dedicated (1h)" },
];

function CellValue({ value }: { value: string | boolean }) {
  if (value === true) return <Check size={18} className="text-emerald-400 mx-auto" />;
  if (value === false) return <Minus size={18} className="text-[#64748b] mx-auto" />;
  return <span>{value}</span>;
}

export default function PricingPage() {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingCycle>("monthly");

  const handleCheckout = async (plan: "pro" | "business") => {
    setLoadingPlan(plan);
    try {
      const interval = billing === "annual" ? "year" : "month";
      const { url } = await api.createCheckoutSession(plan, interval);
      if (url) {
        window.location.href = url;
      }
    } catch {
      // Stripe not configured yet — fall back to login
      window.location.href = `/login?plan=${plan}`;
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-20">
      <div className="text-center mb-10">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">Pricing</h1>
        <p className="text-lg text-[#94a3b8]">Start free. Scale as you grow.</p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/20">
            <span className="text-sm font-semibold text-[#FFD700]">14-day free trial on Pro</span>
          </div>
          {/* CVR-03: Explicitly state no credit card required */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-500/20">
            <ShieldCheck size={14} className="text-emerald-400" />
            <span className="text-sm font-semibold text-emerald-400">No credit card required</span>
          </div>
        </div>
      </div>

      {/* Billing toggle */}
      <div className="flex items-center justify-center gap-4 mb-12">
        <span className={`text-sm font-medium transition-colors ${billing === "monthly" ? "text-white" : "text-[#64748b]"}`}>
          Monthly
        </span>
        <button
          role="switch"
          aria-checked={billing === "annual"}
          onClick={() => setBilling((b) => (b === "monthly" ? "annual" : "monthly"))}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#FFD700] ${
            billing === "annual" ? "bg-[#FFD700]" : "bg-[#1e293b]"
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
              billing === "annual" ? "translate-x-6" : "translate-x-1"
            }`}
          />
        </button>
        <span className={`text-sm font-medium transition-colors ${billing === "annual" ? "text-white" : "text-[#64748b]"}`}>
          Annual
        </span>
        {billing === "annual" && (
          <span className="px-2 py-0.5 text-xs font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full">
            SAVE 20%
          </span>
        )}
      </div>

      {/* Plans */}
      <div className="grid md:grid-cols-3 gap-6 max-w-[1000px] mx-auto mb-20">
        {plans.map((plan) => {
          const displayPrice = billing === "annual" ? plan.annualMonthlyPrice : plan.monthlyPrice;
          return (
            <div key={plan.name} className={`relative p-9 rounded-2xl border flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-[0_8px_32px_rgba(0,0,0,0.5)] ${plan.popular ? "border-[#FFD700] bg-gradient-to-b from-[#FFD700]/[0.04] to-[#111827] shadow-[0_0_40px_rgba(255,215,0,0.1)]" : "border-[#1e293b] bg-[#111827]"}`}>
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 text-xs font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full uppercase tracking-wide">
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

              <div className="flex items-baseline gap-0.5 mb-1">
                <span className="text-xl font-semibold text-[#94a3b8]">$</span>
                <span className="text-4xl font-extrabold tracking-tight">{displayPrice}</span>
                <span className="text-sm text-[#64748b] ml-1">/month</span>
              </div>
              {billing === "annual" && plan.annualTotal > 0 && (
                <p className="text-xs text-[#64748b] mb-4">
                  Billed annually (${plan.annualTotal.toLocaleString()}/yr)
                </p>
              )}
              {!(billing === "annual" && plan.annualTotal > 0) && <div className="mb-4" />}

              <p className="text-sm text-[#94a3b8] leading-relaxed mb-6">{plan.desc}</p>
              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-[#94a3b8]">
                    <Check size={16} className="text-emerald-400 shrink-0" />{f}
                  </li>
                ))}
                {plan.disabledFeatures.map((f) => (
                  <li key={f} className="flex items-center gap-2.5 text-sm text-[#94a3b8] opacity-40">
                    <Minus size={16} className="shrink-0" />{f}
                  </li>
                ))}
              </ul>
              {plan.stripePlan ? (
                <button
                  onClick={() => handleCheckout(plan.stripePlan!)}
                  disabled={loadingPlan === plan.stripePlan}
                  className={`w-full text-center py-3 rounded-xl font-semibold transition-all flex items-center justify-center gap-2 ${plan.popular ? "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d] disabled:opacity-70" : "border border-[#1e293b] text-white hover:border-[#64748b] disabled:opacity-70"}`}
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
                  className={`w-full text-center py-3 rounded-xl font-semibold transition-all block ${plan.popular ? "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d]" : "border border-[#1e293b] text-white hover:border-[#64748b]"}`}
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

      {/* Feature Comparison Table */}
      <div className="max-w-[900px] mx-auto">
        <h2 className="text-xl font-bold text-center mb-8">Feature Comparison</h2>
        <div className="overflow-x-auto rounded-2xl border border-[#1e293b]">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold">Feature</th>
                <th className="px-5 py-4 text-center bg-[#141a2e] text-[#94a3b8] font-semibold">Free</th>
                <th className="px-5 py-4 text-center bg-[#FFD700]/[0.06] text-[#FFD700] font-semibold">Pro</th>
                <th className="px-5 py-4 text-center bg-[#141a2e] text-[#94a3b8] font-semibold">Business</th>
              </tr>
            </thead>
            <tbody>
              {featureComparison.map((row, i) => (
                <tr key={row.name} className={i < featureComparison.length - 1 ? "border-b border-[#1e293b]" : ""}>
                  <td className="px-5 py-4 font-medium text-white bg-[#111827]">{row.name}</td>
                  <td className="px-5 py-4 text-center bg-[#111827] text-[#94a3b8]"><CellValue value={row.free} /></td>
                  <td className="px-5 py-4 text-center bg-[#FFD700]/[0.03] text-white"><CellValue value={row.pro} /></td>
                  <td className="px-5 py-4 text-center bg-[#111827] text-[#94a3b8]"><CellValue value={row.business} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* SLA note */}
      <div className="max-w-[900px] mx-auto mt-8">
        <p className="text-xs text-[#64748b] text-center">
          99.9% Uptime SLA applies to Pro and Business plans. Service status:{" "}
          <a
            href="https://status.faultray.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#94a3b8] hover:text-white transition-colors"
          >
            status.faultray.com
          </a>
          . View our{" "}
          <Link href="/terms" className="text-[#94a3b8] hover:text-white transition-colors">
            Terms of Service
          </Link>{" "}
          for full SLA details.
        </p>
      </div>

      {/* Footer links */}
      <div className="max-w-[900px] mx-auto mt-16 pt-8 border-t border-[#1e293b] flex flex-wrap justify-center gap-6 text-sm text-[#64748b]">
        <Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
        <Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
        <Link href="/tokushoho" className="hover:text-white transition-colors">特定商取引法に基づく表記</Link>
        <a href="mailto:sales@faultray.com" className="hover:text-white transition-colors">Contact Sales</a>
      </div>
    </div>
  );
}
