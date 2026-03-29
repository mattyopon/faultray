import Link from "next/link";
import { Check, Minus } from "lucide-react";

export const metadata = {
  title: "Pricing",
};

const plans = [
  {
    name: "Free", price: 0,
    desc: "Perfect for individual engineers exploring chaos engineering.",
    features: ["5 simulations / month", "Up to 5 components", "100+ simulation engines", "N-Layer Availability Model", "HTML reports", "Community support"],
    disabledFeatures: ["DORA report export", "Custom SSO"],
    cta: "Get Started Free", ctaHref: "/login", popular: false,
  },
  {
    name: "Pro", price: 299,
    desc: "For teams that need DORA compliance reports and higher limits.",
    features: ["100 simulations / month", "Up to 50 components", "Everything in Free", "DORA report export (PDF)", "AI-powered analysis", "Email support (24h)"],
    disabledFeatures: ["Insurance API", "Custom SSO"],
    cta: "Start Pro", ctaHref: "/login?plan=pro", popular: true,
  },
  {
    name: "Business", price: 999,
    desc: "For enterprises needing unlimited access, SSO, and dedicated support.",
    features: ["Unlimited simulations", "Unlimited components", "Everything in Pro", "DORA report + Insurance API", "Custom SSO / SAML", "Dedicated support (1h)", "Prometheus integration", "On-premise deployment"],
    disabledFeatures: [],
    cta: "Contact Us", ctaHref: "mailto:sales@faultray.com", popular: false,
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
  { name: "Support", free: "Community", pro: "Email (24h)", business: "Dedicated (1h)" },
];

function CellValue({ value }: { value: string | boolean }) {
  if (value === true) return <Check size={18} className="text-emerald-400 mx-auto" />;
  if (value === false) return <Minus size={18} className="text-[#64748b] mx-auto" />;
  return <span>{value}</span>;
}

export default function PricingPage() {
  return (
    <div className="max-w-[1200px] mx-auto px-6 py-20">
      <div className="text-center mb-16">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">Pricing</h1>
        <p className="text-lg text-[#94a3b8]">Start free. Scale as you grow.</p>
      </div>

      {/* Plans */}
      <div className="grid md:grid-cols-3 gap-6 max-w-[1000px] mx-auto mb-20">
        {plans.map((plan) => (
          <div key={plan.name} className={`relative p-9 rounded-2xl border flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-[0_8px_32px_rgba(0,0,0,0.5)] ${plan.popular ? "border-[#FFD700] bg-gradient-to-b from-[#FFD700]/[0.04] to-[#111827] shadow-[0_0_40px_rgba(255,215,0,0.1)]" : "border-[#1e293b] bg-[#111827]"}`}>
            {plan.popular && <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 text-xs font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full uppercase tracking-wide">Most Popular</div>}
            <div className="text-lg font-bold mb-4">{plan.name}</div>
            <div className="flex items-baseline gap-0.5 mb-4">
              <span className="text-xl font-semibold text-[#94a3b8]">$</span>
              <span className="text-4xl font-extrabold tracking-tight">{plan.price}</span>
              <span className="text-sm text-[#64748b] ml-1">/month</span>
            </div>
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
            <Link href={plan.ctaHref} className={`w-full text-center py-3 rounded-xl font-semibold transition-all ${plan.popular ? "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d]" : "border border-[#1e293b] text-white hover:border-[#64748b]"}`}>
              {plan.cta}
            </Link>
          </div>
        ))}
      </div>

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
    </div>
  );
}
