import Link from "next/link";
import { Logo } from "@/components/logo";
import {
  Shield,
  Zap,
  Brain,
  FileCheck,
  Lock,
  Check,
  X as XIcon,
  Minus,
  Bot,
  Boxes,
  Activity,
  AlertTriangle,
  Layers,
  ExternalLink,
  LineChart,
  Cpu,
  Wrench,
  LayoutDashboard,
} from "lucide-react";
import { isValidLocale } from "@/i18n/config";
import { getDictionary } from "@/i18n/get-dictionary";
import { notFound } from "next/navigation";
import { LanguageSwitcher } from "@/components/language-switcher";
import { SocialProof } from "@/components/social-proof";
import { RoiCalculator } from "@/components/roi-calculator";

/* ================================================================
   HERO TERMINAL — animated pip install + faultray demo
   ================================================================ */
function HeroTerminal() {
  return (
    <div className="max-w-[640px] mx-auto">
      <div className="rounded-2xl overflow-hidden border border-[#1e293b] shadow-[0_8px_32px_rgba(0,0,0,0.5),0_0_60px_rgba(255,215,0,0.08)] bg-[#0d1117]">
        <div className="flex items-center gap-2 px-4 py-3 bg-[#161b22] border-b border-[#1e293b]">
          <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
          <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
          <span className="w-3 h-3 rounded-full bg-[#28c840]" />
          <span className="ml-auto text-xs text-[#64748b] font-mono">terminal</span>
        </div>
        <div className="p-5 font-mono text-[0.8125rem] leading-[1.8] text-left">
          <div className="terminal-line terminal-line-1">
            <span className="text-emerald-400 mr-2 select-none">$</span>
            <span className="text-white">pip install faultray</span>
          </div>
          <div className="terminal-line terminal-line-2">
            <span className="text-[#64748b] pl-5 block">Successfully installed faultray-11.0.0</span>
          </div>
          <div className="terminal-line terminal-line-3">
            <span className="text-emerald-400 mr-2 select-none">$</span>
            <span className="text-white">faultray demo</span>
          </div>
          <div className="terminal-line terminal-line-4">
            <span className="text-[#FFD700] pl-5 block">Running 2,048 chaos scenarios across 100+ engines...</span>
          </div>
          <div className="terminal-line terminal-line-5">
            <span className="text-emerald-400 pl-5 block">Availability Ceiling: 99.9991% (4.05 nines)</span>
          </div>
          <div className="terminal-line terminal-line-6">
            <span className="text-emerald-400 pl-5 block">N-Layer Analysis: Software=4.00 | Hardware=5.91 | Theoretical=6.65 | Ops=5.20 | External=4.85</span>
          </div>
          <div className="terminal-line terminal-line-7">
            <span className="text-[#64748b] pl-5 block">Report saved: faultray-report.html</span>
          </div>
          <div className="inline-block w-2 h-4 bg-[#FFD700] ml-1 align-text-bottom cursor-blink" />
        </div>
      </div>
    </div>
  );
}

/* ================================================================
   DATA — icons for features (order matches dictionary)
   ================================================================ */
const featureIcons = [Activity, Boxes, Layers, Brain, FileCheck, Lock, LineChart, Cpu, Wrench, LayoutDashboard];
const agentFeatureIcons = [Bot, Shield, Boxes, AlertTriangle];

/*
  10-Mode AI Agent Failure Taxonomy (paper Table 2)
  Source: faultray-paper.tex, Table 2 "AI agent failure taxonomy (10 modes)"
  Mode names stay in English per spec.
*/
const failureTaxonomy = [
  { mode: "Hallucination", health: "Degraded" },
  { mode: "Context Overflow", health: "Down" },
  { mode: "LLM Rate Limit", health: "Overloaded" },
  { mode: "Token Exhaustion", health: "Down" },
  { mode: "Tool Failure", health: "Degraded" },
  { mode: "Agent Loop", health: "Down" },
  { mode: "Prompt Injection", health: "Degraded" },
  { mode: "Confidence Miscal.", health: "Degraded" },
  { mode: "CoT Collapse", health: "Degraded" },
  { mode: "Output Amplification", health: "Degraded" },
];

/* Taxonomy descriptions stay in English (technical terms) */
const failureTaxonomyDescs = [
  "Ungrounded output from degraded data sources",
  "Token limit exceeded, agent cannot process input",
  "API throttling from provider-side limits",
  "Budget depleted, no tokens remaining",
  "External tool or API unavailable",
  "Infinite iteration, agent stuck in cycle",
  "Adversarial input manipulates agent behavior",
  "Unreliable confidence scores",
  "Chain-of-thought reasoning chain failure",
  "Upstream error propagation to downstream agents",
];

const comparison = [
  { key: "approach", faultrayColor: "", gremlinColor: "", steadybitColor: "", awsColor: "" },
  { key: "productionRisk", faultrayColor: "green", gremlinColor: "red", steadybitColor: "yellow", awsColor: "red" },
  { key: "setupTime", faultrayColor: "green", gremlinColor: "yellow", steadybitColor: "yellow", awsColor: "yellow" },
  { key: "scenarios", faultrayColor: "", gremlinColor: "", steadybitColor: "", awsColor: "" },
  { key: "availabilityProof", faultrayColor: "check", gremlinColor: "x", steadybitColor: "x", awsColor: "x" },
  { key: "aiAgentModeling", faultrayColor: "check", gremlinColor: "x", steadybitColor: "x", awsColor: "x" },
  { key: "startingCost", faultrayColor: "green", gremlinColor: "red", steadybitColor: "yellow", awsColor: "yellow" },
];

function ComparisonCellStyled({ value, color }: { value: string; color: string }) {
  if (color === "green")
    return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400">{value}</span>;
  if (color === "red")
    return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-red-500/10 text-red-400">{value}</span>;
  if (color === "yellow")
    return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-yellow-500/10 text-yellow-400">{value}</span>;
  if (color === "check")
    return <span className="flex items-center gap-1"><Check size={16} className="text-emerald-400" />{value}</span>;
  if (color === "x")
    return <span className="flex items-center gap-1"><XIcon size={16} className="text-red-400" />{value}</span>;
  return <span>{value}</span>;
}

const layerStyles = [
  { nines: "5.91 nines", pct: "99.99988%", colorClass: "text-[#FFD700]", border: "border-[#FFD700]/20", bg: "from-[#FFD700]/[0.06]" },
  { nines: "4.00 nines", pct: "99.99%", colorClass: "text-emerald-400", border: "border-emerald-500/25", bg: "from-emerald-500/[0.08]" },
  { nines: "6.65 nines", pct: "99.999978%", colorClass: "text-blue-400", border: "border-blue-500/25", bg: "from-blue-500/[0.08]" },
  { nines: "5.20 nines", pct: "99.99937%", colorClass: "text-purple-400", border: "border-purple-500/25", bg: "from-purple-500/[0.08]" },
  { nines: "4.85 nines", pct: "99.9986%", colorClass: "text-orange-400", border: "border-orange-500/25", bg: "from-orange-500/[0.08]" },
];

const planData = [
  {
    price: 0,
    features: [
      "5 simulations / month",
      "Up to 5 components",
      "100+ simulation engines",
      "N-Layer Availability Model",
      "HTML reports",
      "Community support",
    ],
    disabledFeatures: ["DORA report export", "Custom SSO"],
    ctaHref: "/login",
    popular: false,
  },
  {
    price: 299,
    features: [
      "100 simulations / month",
      "Up to 50 components",
      "Everything in Free",
      "DORA report export (PDF)",
      "AI-powered analysis",
      "Email support (24h response)",
    ],
    disabledFeatures: ["Insurance API", "Custom SSO"],
    ctaHref: "/login?plan=pro",
    popular: true,
  },
  {
    price: 999,
    features: [
      "Unlimited simulations",
      "Unlimited components",
      "Everything in Pro",
      "DORA report + Insurance API",
      "Custom SSO / SAML",
      "Dedicated support (1h response)",
      "Prometheus integration",
      "On-premise deployment",
    ],
    disabledFeatures: [],
    ctaHref: "mailto:sales@faultray.com",
    popular: false,
  },
];

const pricingComparison = [
  { feature: "Simulations / month", free: "5", pro: "100", business: "Unlimited" },
  { feature: "Components", free: "5", pro: "50", business: "Unlimited" },
  { feature: "Simulation engines", free: "100+", pro: "100+", business: "100+" },
  { feature: "N-Layer Model", free: "check", pro: "check", business: "check" },
  { feature: "DORA report export", free: "no", pro: "PDF", business: "PDF + API" },
  { feature: "Insurance API", free: "no", pro: "no", business: "check" },
  { feature: "AI-powered analysis", free: "no", pro: "check", business: "check" },
  { feature: "Custom SSO / SAML", free: "no", pro: "no", business: "check" },
  { feature: "Support", free: "Community", pro: "Email (24h)", business: "Dedicated (1h)" },
];

function PricingComparisonCell({ value }: { value: string }) {
  if (value === "check") return <Check size={18} className="text-emerald-400 mx-auto" />;
  if (value === "no") return <Minus size={18} className="text-[#64748b] mx-auto" />;
  return <span>{value}</span>;
}

/* ================================================================
   MAIN PAGE
   ================================================================ */
export default async function LangHomePage({
  
}: {
  
}) {
  const lang = "en" as "en" | "ja" | "de" | "fr";
  
  const dict = await getDictionary(lang);

  // GitHub Stars (LP-02): fetch at build/request time, fallback to 0 on error
  let githubStars = 0;
  try {
    const ghRes = await fetch("https://api.github.com/repos/mattyopon/faultray", {
      next: { revalidate: 3600 }, // revalidate every hour
    });
    if (ghRes.ok) {
      const ghData = await ghRes.json() as { stargazers_count?: number };
      githubStars = ghData.stargazers_count ?? 0;
    }
  } catch {
    // silently fallback to 0
  }

  const comparisonLabels = dict.comparison.labels;
  const comparisonKeys = ["approach", "productionRisk", "setupTime", "scenarios", "availabilityProof", "aiAgentModeling", "startingCost"] as const;

  return (
    <>
      {/* ===== HERO ===== */}
      <section className="relative min-h-screen flex items-center overflow-hidden py-24">
        {/* Grid background */}
        <div className="absolute inset-0 bg-[repeating-linear-gradient(rgba(255,215,0,0.03)_1px,transparent_1px),repeating-linear-gradient(90deg,rgba(255,215,0,0.03)_1px,transparent_1px)] bg-[size:60px_60px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_70%)]" />
        {/* Radial glow */}
        <div className="absolute inset-0 hero-radial-glow pointer-events-none" />

        <div className="max-w-[1200px] mx-auto px-6 relative z-10 text-center">
          <div className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-8 tracking-wide">
            {dict.hero.badge}
          </div>

          <h1 className="text-[clamp(3rem,10vw,6rem)] font-extrabold tracking-tighter leading-none mb-5">
            <span className="text-white">Fault</span>
            <span className="text-gradient-gold">Ray</span>
          </h1>

          <p className="text-[clamp(1.125rem,3vw,1.5rem)] text-emerald-400 font-semibold mb-3">
            {dict.hero.subtitle}
          </p>
          <p className="text-[clamp(1rem,2vw,1.25rem)] text-[#94a3b8] max-w-[640px] mx-auto mb-10 leading-relaxed">
            {dict.hero.description}
          </p>

          {/* Stats bar */}
          <div className="flex flex-wrap items-center justify-center gap-6 md:gap-10 mb-10 text-sm">
            <div className="text-center">
              <div className="text-2xl font-extrabold text-[#FFD700]">2,000+</div>
              <div className="text-[#64748b]">{dict.hero.stats.scenarios}</div>
            </div>
            <div className="w-px h-8 bg-[#1e293b] hidden md:block" />
            <div className="text-center">
              <div className="text-2xl font-extrabold text-[#FFD700]">52</div>
              <div className="text-[#64748b]">{dict.hero.stats.doraControls}</div>
            </div>
            <div className="w-px h-8 bg-[#1e293b] hidden md:block" />
            <div className="text-center">
              <div className="text-2xl font-extrabold text-[#FFD700]">35+</div>
              <div className="text-[#64748b]">{dict.hero.stats.dashboardPages}</div>
            </div>
            <div className="w-px h-8 bg-[#1e293b] hidden md:block" />
            <div className="text-center">
              <div className="text-2xl font-extrabold text-[#FFD700]">32,000+</div>
              <div className="text-[#64748b]">{dict.hero.stats.tests}</div>
            </div>
            <div className="w-px h-8 bg-[#1e293b] hidden md:block" />
            <div className="text-center">
              <div className="text-2xl font-extrabold text-[#FFD700]">8</div>
              <div className="text-[#64748b]">{dict.hero.stats.languages}</div>
            </div>
          </div>

          <div className="flex gap-4 justify-center flex-wrap mb-14">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-7 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:bg-[#ffe44d] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] hover:-translate-y-0.5 transition-all"
            >
              <Zap size={16} />
              {dict.hero.cta}
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-7 py-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-semibold rounded-xl hover:bg-emerald-500/20 hover:border-emerald-500/50 hover:-translate-y-0.5 transition-all"
            >
              <ExternalLink size={16} />
              {"Book a Free Demo"}
            </Link>
            <Link
              href="/simulate"
              className="inline-flex items-center gap-2 px-7 py-3 border border-[#1e293b] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] hover:-translate-y-0.5 transition-all"
            >
              {dict.hero.demo}
            </Link>
          </div>

          <HeroTerminal />
        </div>
      </section>

      {/* ===== PROBLEM / SOLUTION ===== */}
      <section className="py-24 ">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-8">
            {/* Problem */}
            <div className="p-10 rounded-2xl border border-red-500/20 bg-[#111827] transition-all duration-300 hover:border-red-500/30">
              <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-red-500/10 mb-5">
                <AlertTriangle size={28} className="text-red-400" />
              </div>
              <h2 className="text-2xl font-bold mb-3">{dict.problem.title}</h2>
              <p className="text-[#94a3b8] mb-6">
                {dict.problem.descriptionParts.before}
                <strong>{dict.problem.descriptionParts.highlight}</strong>
                {dict.problem.descriptionParts.after}
              </p>
              <ul className="space-y-3.5">
                {dict.problem.items.map((item: string) => (
                  <li key={item} className="flex items-start gap-3 text-[#94a3b8] text-[0.9375rem]">
                    <XIcon size={16} className="text-red-400 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>

            {/* Solution */}
            <div className="p-10 rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-[#111827] to-emerald-500/[0.03] transition-all duration-300 hover:border-emerald-500/30">
              <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-emerald-500/10 mb-5">
                <Shield size={28} className="text-emerald-400" />
              </div>
              <h2 className="text-2xl font-bold mb-3">{dict.solution.title}</h2>
              <p className="text-[#94a3b8] mb-6">
                {dict.solution.descriptionParts.before}
                <strong>{dict.solution.descriptionParts.highlight}</strong>
                {dict.solution.descriptionParts.after}
              </p>
              <ul className="space-y-3.5">
                {dict.solution.items.map((item: string) => (
                  <li key={item} className="flex items-start gap-3 text-[#94a3b8] text-[0.9375rem]">
                    <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ===== CHALLENGES ===== */}
      {dict.challenges && (
        <section className="py-24 bg-[#0a0e1a]">
          <div className="max-w-[1200px] mx-auto px-6">
            <div className="text-center mb-14">
              <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.challenges.heading}</h2>
              <p className="text-lg text-[#94a3b8] max-w-[540px] mx-auto">{dict.challenges.subheading}</p>
            </div>
            <div className="space-y-4 max-w-[800px] mx-auto">
              {(dict.challenges.items as Array<{ problem: string; solution: string }>).map((item, i) => (
                <div key={i} className="grid md:grid-cols-2 gap-0 rounded-2xl overflow-hidden border border-[#1e293b]">
                  <div className="flex items-start gap-3 p-5 bg-red-500/[0.03] border-b md:border-b-0 md:border-r border-[#1e293b]">
                    <XIcon size={16} className="text-red-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-[#94a3b8]">{item.problem}</p>
                  </div>
                  <div className="flex items-start gap-3 p-5 bg-emerald-500/[0.03]">
                    <Check size={16} className="text-emerald-400 mt-0.5 shrink-0" />
                    <p className="text-sm text-[#94a3b8]">{item.solution}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ===== FEATURES ===== */}
      <section id="features" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.features.heading}</h2>
            <p className="text-lg text-[#94a3b8] max-w-[540px] mx-auto">{dict.features.subheading}</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 ">
            {dict.features.cards.map((f: { title: string; desc: string }, i: number) => {
              const Icon = featureIcons[i];
              return (
                <div
                  key={f.title}
                  className=" p-8 rounded-2xl border border-[#1e293b] bg-[#111827] transition-all duration-200 hover:border-[#FFD700]/30 hover:bg-[#1a2035] hover:-translate-y-0.5 hover:shadow-[0_0_40px_rgba(255,215,0,0.1)]"
                >
                  <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={24} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2.5">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
          {/* LP-05: Link to /features for full details */}
          <div className="text-center mt-10">
            <Link
              href="/features"
              className="inline-flex items-center gap-2 px-6 py-3 border border-[#1e293b] text-[#94a3b8] rounded-xl hover:border-[#64748b] hover:text-white hover:bg-white/[0.03] transition-all text-sm"
            >
              <ExternalLink size={14} />
              {dict.features?.viewAll ?? "View Full Feature Details"}
            </Link>
          </div>
        </div>
      </section>

      {/* ===== AI AGENT RESILIENCE ===== */}
      <section id="agent-resilience" className="py-24 bg-[#0f1424] border-t border-[#FFD700]/15">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <span className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-4">
              {dict.agentResilience.badge}
            </span>
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.agentResilience.heading}</h2>
            <p className="text-lg text-[#94a3b8] max-w-[640px] mx-auto">
              {dict.agentResilience.subheading}
            </p>
          </div>

          {/* Agent feature cards */}
          <div className="grid md:grid-cols-2 gap-6 mb-12">
            {dict.agentResilience.cards.map((f: { title: string; desc: string }, i: number) => {
              const Icon = agentFeatureIcons[i];
              return (
                <div
                  key={f.title}
                  className=" p-8 rounded-2xl border border-[#1e293b] bg-[#111827] transition-all duration-200 hover:border-[#FFD700]/30 hover:bg-[#1a2035] hover:-translate-y-0.5"
                >
                  <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={24} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2.5">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>

          {/* 10-Mode Failure Taxonomy Table */}
          <div className=" max-w-[900px] mx-auto mb-10">
            <h3 className="text-xl font-bold text-center mb-6">
              <span className="text-[#FFD700]">{dict.agentResilience.taxonomyHeadingHighlight}</span>
              {dict.agentResilience.taxonomyHeadingSuffix}
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {failureTaxonomy.map((f, i) => (
                <div
                  key={f.mode}
                  className="taxonomy-card p-4 rounded-xl border border-[#1e293b] bg-[#111827]/80 text-center transition-all duration-200 hover:bg-[#1a2035]"
                >
                  <div className="text-sm font-bold text-white mb-1">{f.mode}</div>
                  <div
                    className={`inline-block px-2 py-0.5 text-[0.6875rem] font-semibold rounded-full mb-2 ${
                      f.health === "Down"
                        ? "bg-red-500/10 text-red-400"
                        : f.health === "Overloaded"
                          ? "bg-yellow-500/10 text-yellow-400"
                          : "bg-orange-500/10 text-orange-400"
                    }`}
                  >
                    {f.health}
                  </div>
                  <div className="text-xs text-[#64748b] leading-snug">{failureTaxonomyDescs[i]}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Agent CLI demo */}
          <div className=" max-w-[680px] mx-auto">
            <div className="rounded-xl overflow-hidden border border-[#1e293b] bg-[#0d1117]">
              <div className="flex items-center justify-between px-4 py-2.5 bg-[#161b22] border-b border-[#1e293b]">
                <span className="text-xs text-[#64748b]">Terminal</span>
              </div>
              <pre className="p-4 font-mono text-[0.8125rem] leading-[1.7] overflow-x-auto">
                <code>
                  <span className="text-emerald-400">$</span>{" "}faultray agent assess infra.yaml{"\n"}
                  <span className="text-[#FFD700]">Agent Risk Assessment</span>{"\n"}
                  {"  "}support-agent    Risk: 4.2/10 (MEDIUM)  Blast radius: 3 components{"\n"}
                  <span className="text-emerald-400">{"  "}Recommendations: Add fallback LLM, enable hallucination circuit breaker</span>{"\n"}
                  {"\n"}
                  <span className="text-emerald-400">$</span>{" "}faultray agent scenarios infra.yaml{"\n"}
                  {"  "}Generated 12 agent-specific chaos scenarios{"\n"}
                  {"\n"}
                  <span className="text-emerald-400">$</span>{" "}faultray agent monitor infra.yaml{"\n"}
                  <span className="text-emerald-400">{"  "}14 monitoring rules generated (context_window, hallucination_rate, ...)</span>
                </code>
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* ===== COMPARISON TABLE ===== */}
      <section id="comparison" className="py-24">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.comparison.heading}</h2>
            <p className="text-lg text-[#94a3b8] max-w-[540px] mx-auto">{dict.comparison.subheading}</p>
          </div>
          <div className=" overflow-x-auto rounded-2xl border border-[#1e293b]">
            <table className="w-full min-w-[700px] border-collapse text-[0.9375rem]">
              <thead>
                <tr>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm" />
                  <th className="px-5 py-4 text-left bg-[#FFD700]/[0.06] text-[#FFD700] font-semibold text-sm">
                    <span className="inline-block px-2 py-0.5 text-[0.6875rem] font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full uppercase tracking-wide mb-1">
                      {dict.comparison.recommended}
                    </span>
                    <br />
                    FaultRay
                  </th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Gremlin</th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Steadybit</th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">AWS FIS</th>
                </tr>
              </thead>
              <tbody>
                {comparisonKeys.map((key, i) => {
                  const row = comparison[i];
                  const label = comparisonLabels[key];
                  const faultrayVal = dict.comparison.faultray[key] || "";
                  const gremlinVal = (dict.comparison.gremlin as Record<string, string>)[key] || "No";
                  const steadybitVal = (dict.comparison.steadybit as Record<string, string>)[key] || "No";
                  const awsVal = (dict.comparison.awsFis as Record<string, string>)[key] || "No";
                  return (
                    <tr key={key} className={i < comparisonKeys.length - 1 ? "border-b border-[#1e293b]" : ""}>
                      <td className="px-5 py-4 font-semibold text-white whitespace-nowrap bg-[#111827]">{label}</td>
                      <td className="px-5 py-4 bg-[#FFD700]/[0.03] text-white font-medium">
                        <ComparisonCellStyled value={faultrayVal} color={row.faultrayColor} />
                      </td>
                      <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]">
                        <ComparisonCellStyled value={gremlinVal} color={row.gremlinColor} />
                      </td>
                      <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]">
                        <ComparisonCellStyled value={steadybitVal} color={row.steadybitColor} />
                      </td>
                      <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]">
                        <ComparisonCellStyled value={awsVal} color={row.awsColor} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ===== N-LAYER (5-LAYER) AVAILABILITY MODEL ===== */}
      <section id="model" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
              {dict.nlayer.heading}
            </h2>
            <p className="text-lg text-[#94a3b8] max-w-[640px] mx-auto">
              {dict.nlayer.subheading}
            </p>
          </div>
          <div className="grid lg:grid-cols-2 gap-12 items-start">
            {/* Layer stack */}
            <div className=" flex flex-col layer-stack">
              {dict.nlayer.layers.map((layer: { label: string; desc: string }, i: number) => {
                const style = layerStyles[i];
                return (
                  <div
                    key={layer.label}
                    className={`px-8 py-6 border ${style.border} bg-gradient-to-br ${style.bg} to-[#111827] transition-all duration-200 hover:brightness-110 ${
                      i === 0 ? "rounded-t-2xl" : ""
                    } ${i === layerStyles.length - 1 ? "rounded-b-2xl" : ""}`}
                  >
                    <div className={`font-bold text-sm mb-1 ${style.colorClass}`}>{layer.label}</div>
                    <div className="flex items-baseline gap-4 mb-1.5">
                      <span className={`text-[1.5rem] font-extrabold tracking-tight ${style.colorClass}`}>{style.nines}</span>
                      <span className="text-xs text-[#64748b] font-mono">{style.pct}</span>
                    </div>
                    <p className="text-xs text-[#94a3b8] leading-relaxed">{layer.desc}</p>
                  </div>
                );
              })}
              {/* Formula */}
              <div className="mt-4 px-4 py-3 rounded-xl bg-[#0d1117] border border-[#1e293b]">
                <code className="text-xs font-mono text-emerald-400">
                  A_system = min(A_hw, A_sw, A_theoretical, A_ops, A_external)
                </code>
              </div>
            </div>

            {/* Insight card */}
            <div className="">
              <div className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] mb-6">
                <h3 className="text-xl font-bold text-[#FFD700] mb-3">{dict.nlayer.whyTitle}</h3>
                <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed mb-5">
                  {dict.nlayer.whyP1}
                </p>
                <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed mb-5">
                  {dict.nlayer.whyP2}
                </p>
                <code className="block px-4 py-3.5 bg-[#0d1117] rounded-lg font-mono text-[0.8125rem] text-emerald-400 border border-[#1e293b] overflow-x-auto">
                  faultray analyze --topology infra.yaml --output n-layer
                </code>
              </div>

              {/* Key insight card */}
              <div className="p-6 rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-[#111827] to-emerald-500/[0.03]">
                <div className="flex items-start gap-3">
                  <Check size={20} className="text-emerald-400 mt-0.5 shrink-0" />
                  <div>
                    <div className="font-semibold text-white mb-1">{dict.nlayer.bindingTitle}</div>
                    <p className="text-sm text-[#94a3b8] leading-relaxed">
                      {dict.nlayer.bindingDesc}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== QUICK START ===== */}
      <section id="quickstart" className="py-24">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.quickstart.heading}</h2>
            <p className="text-lg text-[#94a3b8]">{dict.quickstart.subheading}</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 mb-16">
            {/* Step 1 */}
            <div className="">
              <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/25 text-[#FFD700] font-bold text-sm mb-4">
                1
              </div>
              <h3 className="text-lg font-bold mb-4">{dict.quickstart.step1Title}</h3>
              <div className="rounded-xl overflow-hidden border border-[#1e293b] bg-[#0d1117]">
                <div className="flex items-center justify-between px-4 py-2.5 bg-[#161b22] border-b border-[#1e293b]">
                  <span className="text-xs text-[#64748b]">Terminal</span>
                </div>
                <pre className="p-4 font-mono text-[0.8125rem] leading-[1.7]">
                  <code>
                    <span className="text-emerald-400">$</span> pip install faultray
                  </code>
                </pre>
              </div>
            </div>

            {/* Step 2 */}
            <div className="">
              <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/25 text-[#FFD700] font-bold text-sm mb-4">
                2
              </div>
              <h3 className="text-lg font-bold mb-4">{dict.quickstart.step2Title}</h3>
              <div className="rounded-xl overflow-hidden border border-[#1e293b] bg-[#0d1117]">
                <div className="flex items-center justify-between px-4 py-2.5 bg-[#161b22] border-b border-[#1e293b]">
                  <span className="text-xs text-[#64748b]">infra.yaml</span>
                </div>
                <pre className="p-4 font-mono text-[0.8125rem] leading-[1.7] overflow-x-auto">
                  <code>
                    <span className="text-blue-400">topology</span>:{"\n"}
                    {"  "}<span className="text-blue-400">name</span>: <span className="text-emerald-400">my-saas-platform</span>{"\n"}
                    {"  "}<span className="text-blue-400">regions</span>:{"\n"}
                    {"    "}- <span className="text-blue-400">name</span>: <span className="text-emerald-400">us-east-1</span>{"\n"}
                    {"      "}<span className="text-blue-400">zones</span>: <span className="text-emerald-400">[a, b, c]</span>{"\n"}
                    {"  "}<span className="text-blue-400">services</span>:{"\n"}
                    {"    "}- <span className="text-blue-400">name</span>: <span className="text-emerald-400">api-gateway</span>{"\n"}
                    {"      "}<span className="text-blue-400">replicas</span>: <span className="text-[#FFD700]">3</span>{"\n"}
                    {"      "}<span className="text-blue-400">dependencies</span>: <span className="text-emerald-400">[auth, database]</span>
                  </code>
                </pre>
              </div>
            </div>

            {/* Step 3 */}
            <div className="">
              <div className="flex items-center justify-center w-9 h-9 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/25 text-[#FFD700] font-bold text-sm mb-4">
                3
              </div>
              <h3 className="text-lg font-bold mb-4">{dict.quickstart.step3Title}</h3>
              <div className="rounded-xl overflow-hidden border border-[#1e293b] bg-[#0d1117]">
                <div className="flex items-center justify-between px-4 py-2.5 bg-[#161b22] border-b border-[#1e293b]">
                  <span className="text-xs text-[#64748b]">Terminal</span>
                </div>
                <pre className="p-4 font-mono text-[0.8125rem] leading-[1.7] overflow-x-auto">
                  <code>
                    <span className="text-emerald-400">$</span> faultray run --topology infra.yaml{"\n"}
                    <span className="text-[#64748b]">Running 2,048 scenarios across 100+ engines...</span>{"\n"}
                    <span className="text-emerald-400">Completed in 8.3s | Pass: 2,043 | Fail: 5</span>{"\n"}
                    {"\n"}
                    <span className="text-emerald-400">$</span> faultray report --format html{"\n"}
                    <span className="text-[#64748b]">Report saved: report.html</span>{"\n"}
                    {"\n"}
                    <span className="text-emerald-400">$</span> faultray dashboard{"\n"}
                    <span className="text-[#FFD700]">Dashboard running at http://localhost:8550</span>
                  </code>
                </pre>
              </div>
            </div>
          </div>

          {/* Dashboard mockup */}
          <div className=" max-w-[900px] mx-auto">
            <div className="rounded-2xl overflow-hidden border border-[#1e293b] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
              <div className="flex items-center gap-3 px-4 py-3 bg-[#161b22] border-b border-[#1e293b]">
                <div className="flex gap-2">
                  <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                  <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
                  <span className="w-3 h-3 rounded-full bg-[#28c840]" />
                </div>
                <span className="text-xs text-[#64748b] font-mono ml-2">localhost:8550/dashboard</span>
              </div>
              <div className="grid grid-cols-[160px_1fr] min-h-[280px] bg-[#0d1117] max-md:grid-cols-1">
                {/* Sidebar */}
                <div className="border-r border-[#1e293b] py-4 max-md:hidden">
                  {["Overview", "Scenarios", "N-Layer", "Reports"].map((item, i) => (
                    <div
                      key={item}
                      className={`px-5 py-2 text-[0.8125rem] ${
                        i === 0
                          ? "text-white bg-white/[0.03] border-l-2 border-[#FFD700]"
                          : "text-[#64748b]"
                      }`}
                    >
                      {item}
                    </div>
                  ))}
                </div>
                {/* Main */}
                <div className="p-6">
                  <div className="grid grid-cols-4 gap-4 mb-6 max-md:grid-cols-2">
                    {[
                      { value: "99.99%", label: "Availability", color: "text-emerald-400" },
                      { value: "2,048", label: "Scenarios", color: "text-white" },
                      { value: "2,043", label: "Passed", color: "text-emerald-400" },
                      { value: "5", label: "Failed", color: "text-red-400" },
                    ].map((stat) => (
                      <div key={stat.label} className="text-center p-4 rounded-lg bg-white/[0.02] border border-[#1e293b]">
                        <div className={`text-xl font-bold font-mono mb-1 ${stat.color}`}>{stat.value}</div>
                        <div className="text-[0.6875rem] text-[#64748b] uppercase tracking-wider">{stat.label}</div>
                      </div>
                    ))}
                  </div>
                  <div className="p-5 rounded-lg bg-white/[0.02] border border-[#1e293b]">
                    <div className="text-[0.8125rem] font-semibold text-[#94a3b8] mb-4">Availability by Layer</div>
                    {[
                      { label: "Hardware", width: "89%", value: "5.91", color: "bg-[#FFD700]" },
                      { label: "Software", width: "60%", value: "4.00", color: "bg-emerald-400" },
                      { label: "Theoretical", width: "100%", value: "6.65", color: "bg-blue-400" },
                      { label: "Operational", width: "78%", value: "5.20", color: "bg-purple-400" },
                      { label: "External", width: "73%", value: "4.85", color: "bg-orange-400" },
                    ].map((bar) => (
                      <div key={bar.label} className="grid grid-cols-[80px_1fr_48px] items-center gap-3 mb-3 last:mb-0">
                        <span className="text-xs text-[#64748b]">{bar.label}</span>
                        <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                          <div className={`h-full rounded-full ${bar.color}`} style={{ width: bar.width }} />
                        </div>
                        <span className="text-[0.8125rem] font-semibold font-mono text-right text-[#94a3b8]">{bar.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== MID-PAGE CTA ===== */}
      <section className="py-16 bg-gradient-to-r from-[#0a0e1a] via-[#111827] to-[#0a0e1a] border-y border-[#1e293b]">
        <div className="max-w-[900px] mx-auto px-6 text-center">
          <h2 className="text-[clamp(1.5rem,3vw,2rem)] font-bold tracking-tight mb-3">
            Ready to prove your availability ceiling?
          </h2>
          <p className="text-[#94a3b8] mb-8 max-w-[540px] mx-auto leading-relaxed">
            See FaultRay in action with your own infrastructure. Our team will walk you through a live simulation in 30 minutes.
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-8 py-3.5 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:bg-[#ffe44d] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] hover:-translate-y-0.5 transition-all"
            >
              <ExternalLink size={16} />
              Book a Free Demo
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-8 py-3.5 border border-[#1e293b] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] hover:-translate-y-0.5 transition-all"
            >
              <Zap size={16} />
              Start Free
            </Link>
          </div>
        </div>
      </section>

      {/* ===== SOCIAL PROOF (LP-02) ===== */}
      {dict.socialProof && (
        <SocialProof dict={dict.socialProof} stars={githubStars} />
      )}

      {/* ===== ROI CALCULATOR (LP-04) ===== */}
      {dict.roi && (
        <RoiCalculator dict={dict.roi} lang={lang} />
      )}

      {/* ===== PRICING ===== */}
      <section id="pricing" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16 ">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">{dict.pricing.heading}</h2>
            <p className="text-lg text-[#94a3b8]">{dict.pricing.subheading}</p>
          </div>

          {/* Plan cards */}
          <div className="grid md:grid-cols-3 gap-6 max-w-[1000px] mx-auto mb-20">
            {dict.pricing.plans.map((plan: { name: string; desc: string; cta: string }, i: number) => {
              const data = planData[i];
              return (
                <div
                  key={plan.name}
                  className={` relative p-9 rounded-2xl border flex flex-col transition-all duration-200 hover:-translate-y-1 hover:shadow-[0_8px_32px_rgba(0,0,0,0.5)] ${
                    data.popular
                      ? "border-[#FFD700] bg-gradient-to-b from-[#FFD700]/[0.04] to-[#111827] shadow-[0_0_40px_rgba(255,215,0,0.1)]"
                      : "border-[#1e293b] bg-[#111827]"
                  }`}
                >
                  {data.popular && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 text-xs font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full uppercase tracking-wide">
                      {dict.pricing.mostPopular}
                    </div>
                  )}
                  <div className="text-lg font-bold mb-4">{plan.name}</div>
                  <div className="flex items-baseline gap-0.5 mb-4">
                    {dict.pricing.prices[i] === 0 ? (
                      <span className="text-4xl font-extrabold tracking-tight">Free</span>
                    ) : (
                      <>
                        <span className="text-xl font-semibold text-[#94a3b8]">{dict.pricing.currency}</span>
                        <span className="text-4xl font-extrabold tracking-tight">{dict.pricing.prices[i].toLocaleString()}</span>
                        <span className="text-sm text-[#64748b] ml-1">{dict.pricing.perMonth}</span>
                        {dict.pricing.taxNote && (
                          <span className="text-xs text-[#64748b] ml-1">{dict.pricing.taxNote}</span>
                        )}
                      </>
                    )}
                  </div>
                  <p className="text-sm text-[#94a3b8] leading-relaxed mb-4">{plan.desc}</p>
                  {/* LP-07: Japanese support badge on paid plans */}
                  {i > 0 && dict.pricing.japaneseSupportBadge && (
                    <div className="inline-flex items-center gap-1.5 px-3 py-1 mb-5 text-xs font-semibold rounded-full bg-[#1e293b] text-[#94a3b8] border border-[#1e293b] w-fit">
                      <span>🇯🇵</span>
                      {dict.pricing.japaneseSupportBadge}
                    </div>
                  )}
                  <ul className="space-y-3 mb-8 flex-1">
                    {data.features.map((f) => (
                      <li key={f} className="flex items-center gap-2.5 text-sm text-[#94a3b8]">
                        <Check size={16} className="text-emerald-400 shrink-0" />
                        {f}
                      </li>
                    ))}
                    {data.disabledFeatures.map((f) => (
                      <li key={f} className="flex items-center gap-2.5 text-sm text-[#94a3b8] opacity-40">
                        <Minus size={16} className="shrink-0" />
                        {f}
                      </li>
                    ))}
                  </ul>
                  <Link
                    href={data.ctaHref}
                    className={`w-full text-center py-3 rounded-xl font-semibold transition-all ${
                      data.popular
                        ? "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)]"
                        : "border border-[#1e293b] text-white hover:border-[#64748b] hover:bg-white/[0.03]"
                    }`}
                  >
                    {plan.cta}
                  </Link>
                </div>
              );
            })}
          </div>

          {/* Feature comparison table */}
          <div className=" max-w-[900px] mx-auto">
            <h3 className="text-xl font-bold text-center mb-8">{dict.pricing.featureComparison}</h3>
            <div className="overflow-x-auto rounded-2xl border border-[#1e293b]">
              <table className="w-full min-w-[600px] border-collapse text-[0.9375rem]">
                <thead>
                  <tr>
                    <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Feature</th>
                    <th className="px-5 py-4 text-center bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Free</th>
                    <th className="px-5 py-4 text-center bg-[#FFD700]/[0.06] text-[#FFD700] font-semibold text-sm">Pro</th>
                    <th className="px-5 py-4 text-center bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Business</th>
                  </tr>
                </thead>
                <tbody>
                  {pricingComparison.map((row, i) => (
                    <tr key={row.feature} className={i < pricingComparison.length - 1 ? "border-b border-[#1e293b]" : ""}>
                      <td className="px-5 py-3.5 font-semibold text-white bg-[#111827]">{row.feature}</td>
                      <td className="px-5 py-3.5 text-center bg-[#111827] text-[#94a3b8]">
                        <PricingComparisonCell value={row.free} />
                      </td>
                      <td className="px-5 py-3.5 text-center bg-[#FFD700]/[0.03] text-white">
                        <PricingComparisonCell value={row.pro} />
                      </td>
                      <td className="px-5 py-3.5 text-center bg-[#111827] text-[#94a3b8]">
                        <PricingComparisonCell value={row.business} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="py-16 border-t border-[#1e293b]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-12">
            {/* Brand */}
            <div>
              <div className="flex items-center gap-2 font-bold mb-3">
                <Logo size={24} />
                FaultRay
              </div>
              <p className="text-sm text-[#64748b] leading-relaxed mb-4 max-w-[300px]">
                {dict.footer.tagline}
              </p>
              <span className="inline-flex items-center gap-1.5 text-[0.8125rem] text-[#64748b] px-3 py-1 border border-[#1e293b] rounded-full">
                {dict.footer.madeIn}
              </span>
            </div>

            {/* Product */}
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">{dict.footer.product}</h4>
              <ul className="space-y-2.5">
                {[
                  [dict.nav.features, "#features"],
                  [dict.comparison.heading, "#comparison"],
                  [dict.nav.pricing, "#pricing"],
                  [dict.quickstart.heading, "#quickstart"],
                ].map(([label, href]) => (
                  <li key={label}>
                    <Link href={href} className="text-sm text-[#64748b] hover:text-white transition-colors">
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>

            {/* Resources */}
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">{dict.footer.resources}</h4>
              <ul className="space-y-2.5">
                <li>
                  <Link href="https://github.com/mattyopon/faultray" target="_blank" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    GitHub
                  </Link>
                </li>
                <li>
                  <Link href="https://pypi.org/project/faultray/" target="_blank" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    PyPI
                  </Link>
                </li>
                <li>
                  <Link href="/simulate" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    {dict.hero.demo}
                  </Link>
                </li>
                <li>
                  <Link
                    href="https://github.com/mattyopon/faultray/blob/main/docs/"
                    target="_blank"
                    className="text-sm text-[#64748b] hover:text-white transition-colors"
                  >
                    Documentation
                  </Link>
                </li>
              </ul>
            </div>

            {/* Legal + Language */}
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">{dict.footer.legal}</h4>
              <ul className="space-y-2.5">
                <li>
                  <Link
                    href="https://github.com/mattyopon/faultray/blob/main/LICENSE"
                    target="_blank"
                    className="text-sm text-[#64748b] hover:text-white transition-colors"
                  >
                    BSL 1.1 (Business Source License)
                  </Link>
                </li>
                <li>
                  <Link href="/contact" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    Book a Demo
                  </Link>
                </li>
                <li>
                  <Link href="mailto:hello@faultray.com" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    Contact
                  </Link>
                </li>
                <li>
                  <Link href="/privacy" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    Privacy Policy
                  </Link>
                </li>
                <li>
                  <Link href="/terms" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    Terms of Service
                  </Link>
                </li>
                <li>
                  <Link href="/dpa" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    DPA
                  </Link>
                </li>
                <li>
                  <Link href="/status" className="text-sm text-[#64748b] hover:text-white transition-colors">
                    System Status
                  </Link>
                </li>
              </ul>
              <div className="mt-6">
                <LanguageSwitcher />
              </div>
            </div>
          </div>

          <div className="pt-6 border-t border-[#1e293b] text-center space-y-2">
            {/* LP-07: Japanese support notice */}
            {dict.footer.japaneseSupport && (
              <p className="text-[0.8125rem] text-[#64748b]">
                <span className="mr-1.5">🇯🇵</span>
                {dict.footer.japaneseSupport}
              </p>
            )}
            <p className="text-[0.8125rem] text-[#64748b]">
              {dict.footer.copyright}
            </p>
          </div>
        </div>
      </footer>
    </>
  );
}
