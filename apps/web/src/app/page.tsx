import Link from "next/link";
import { Logo } from "@/components/logo";
import {
  Shield,
  Zap,
  BarChart3,
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
} from "lucide-react";

function HeroTerminal() {
  return (
    <div className="max-w-[620px] mx-auto">
      <div className="rounded-2xl overflow-hidden border border-[#1e293b] shadow-[0_8px_32px_rgba(0,0,0,0.5),0_0_40px_rgba(255,215,0,0.1)] bg-[#0d1117]">
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
            <span className="text-[#64748b] pl-5 block">Successfully installed faultray-0.3.0</span>
          </div>
          <div className="terminal-line terminal-line-3">
            <span className="text-emerald-400 mr-2 select-none">$</span>
            <span className="text-white">faultray demo</span>
          </div>
          <div className="terminal-line terminal-line-4">
            <span className="text-[#FFD700] pl-5 block">Running 152 chaos scenarios...</span>
          </div>
          <div className="terminal-line terminal-line-5">
            <span className="text-emerald-400 pl-5 block">Availability Ceiling: 99.9991% (4.05 nines)</span>
          </div>
          <div className="terminal-line terminal-line-6">
            <span className="text-emerald-400 pl-5 block">3-Layer Analysis: Software=4.00 | Hardware=5.91 | Theoretical=6.65</span>
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

const features = [
  { icon: Activity, title: "5 Simulation Engines", desc: "Network, process, resource, dependency, and latency chaos engines powered by Monte Carlo, Markov chains, and queuing theory." },
  { icon: Boxes, title: "150+ Auto-Generated Scenarios", desc: "From single-node failures to cascading multi-region outages. Every scenario is generated from your topology YAML." },
  { icon: BarChart3, title: "3-Layer Availability Model", desc: "The only tool that separates Software, Hardware, and Theoretical limits to reveal your true availability ceiling." },
  { icon: Brain, title: "AI-Powered Analysis", desc: "Claude-driven root cause analysis and actionable improvement recommendations ranked by impact and cost." },
  { icon: FileCheck, title: "DORA Compliance Reports", desc: "Generate audit-ready Digital Operational Resilience Act reports with evidence trails and risk assessments." },
  { icon: Lock, title: "Security Feed Integration", desc: "Automatically incorporate CVE data and NVD feeds to simulate vulnerability-triggered cascading failures." },
];

const agentFeatures = [
  { icon: Bot, title: "Cross-Layer Analysis", desc: "Trace how infrastructure failures cascade into agent hallucinations. Expose silent degradation that looks healthy but produces wrong results." },
  { icon: Shield, title: "PREDICT \u00b7 ADOPT \u00b7 MANAGE", desc: "Three pillars for agent resilience: simulate chaos scenarios, assess deployment risk with blast-radius analysis, and generate monitoring rules." },
  { icon: Boxes, title: "4 New Component Types", desc: "Model AI Agents, LLM Endpoints, Tool Services, and Agent Orchestrators as first-class nodes in your dependency graph." },
  { icon: AlertTriangle, title: "7 Agent-Specific Faults", desc: "Hallucination, context overflow, LLM rate limiting, token exhaustion, tool failure, agent loops, and prompt injection." },
];

const comparison = [
  { label: "Approach", faultray: "Mathematical Simulation", gremlin: "Real Fault Injection", steadybit: "Real Fault Injection", aws: "Real Fault Injection" },
  { label: "Production Risk", faultray: "green:Zero", gremlin: "red:High", steadybit: "yellow:Medium", aws: "red:High" },
  { label: "Setup Time", faultray: "green:5 minutes", gremlin: "yellow:Days", steadybit: "yellow:Hours", aws: "yellow:Hours" },
  { label: "Scenarios", faultray: "150+ auto-generated", gremlin: "Manual configuration", steadybit: "Template-based", aws: "AWS services only" },
  { label: "Availability Proof", faultray: "check:3-Layer Mathematical", gremlin: "x:No", steadybit: "x:No", aws: "x:No" },
  { label: "Starting Cost", faultray: "green:Free / OSS", gremlin: "red:$10,000+/yr", steadybit: "yellow:$5,000+/yr", aws: "yellow:Pay per use" },
];

function ComparisonCell({ value }: { value: string }) {
  if (value.startsWith("green:")) return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/10 text-emerald-400">{value.slice(6)}</span>;
  if (value.startsWith("red:")) return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-red-500/10 text-red-400">{value.slice(4)}</span>;
  if (value.startsWith("yellow:")) return <span className="inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full bg-yellow-500/10 text-yellow-400">{value.slice(7)}</span>;
  if (value.startsWith("check:")) return <span className="flex items-center gap-1"><Check size={16} className="text-emerald-400" />{value.slice(6)}</span>;
  if (value.startsWith("x:")) return <span className="flex items-center gap-1"><XIcon size={16} className="text-red-400" />{value.slice(2)}</span>;
  return <span>{value}</span>;
}

const plans = [
  {
    name: "Free", price: 0,
    desc: "Perfect for individual engineers exploring chaos engineering.",
    features: ["5 simulations / month", "Up to 5 components", "5 simulation engines", "3-Layer Availability Model", "HTML reports", "Community support"],
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
    cta: "Contact Us", ctaHref: "mailto:hello@faultray.dev", popular: false,
  },
];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="relative min-h-screen flex items-center overflow-hidden py-24">
        <div className="absolute inset-0 bg-[repeating-linear-gradient(rgba(255,215,0,0.03)_1px,transparent_1px),repeating-linear-gradient(90deg,rgba(255,215,0,0.03)_1px,transparent_1px)] bg-[size:60px_60px] [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_70%)]" />
        <div className="max-w-[1200px] mx-auto px-6 relative z-10 text-center">
          <div className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-8 tracking-wide">
            Open Source &middot; BSL 1.1 License
          </div>
          <h1 className="text-[clamp(3rem,10vw,6rem)] font-extrabold tracking-tighter leading-none mb-5">
            <span className="text-white">Chaos</span>
            <span className="text-[#FFD700]">Proof</span>
          </h1>
          <p className="text-[clamp(1.125rem,3vw,1.5rem)] text-emerald-400 font-semibold mb-3">
            Zero-Risk Infrastructure Chaos Engineering
          </p>
          <p className="text-[clamp(1rem,2vw,1.25rem)] text-[#94a3b8] max-w-[640px] mx-auto mb-10 leading-relaxed">
            Prove your system&apos;s availability ceiling mathematically &mdash; without touching production.
          </p>
          <div className="flex gap-4 justify-center flex-wrap mb-14">
            <Link href="/login" className="inline-flex items-center gap-2 px-7 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:bg-[#ffe44d] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] hover:-translate-y-0.5 transition-all">
              <Zap size={16} />
              Get Started Free
            </Link>
            <Link href="#features" className="inline-flex items-center gap-2 px-7 py-3 border border-[#1e293b] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] hover:-translate-y-0.5 transition-all">
              Learn More
            </Link>
          </div>
          <HeroTerminal />
        </div>
      </section>

      {/* Problem / Solution */}
      <section className="py-24">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="grid md:grid-cols-2 gap-8">
            <div className="p-10 rounded-2xl border border-red-500/20 bg-[#111827]">
              <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-red-500/10 mb-5">
                <AlertTriangle size={28} className="text-red-400" />
              </div>
              <h2 className="text-2xl font-bold mb-3">The Problem</h2>
              <p className="text-[#94a3b8] mb-6">Existing chaos tools inject <strong className="text-white">real faults</strong> into your infrastructure.</p>
              <ul className="space-y-3.5">
                {["Requires production or staging environment", "Risk of real outages during testing", "Expensive infrastructure costs", "Complex setup and teardown", "No mathematical availability proof"].map((item) => (
                  <li key={item} className="flex items-start gap-3 text-[#94a3b8] text-[0.9375rem]">
                    <XIcon size={16} className="text-red-400 mt-0.5 shrink-0" />
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="p-10 rounded-2xl border border-emerald-500/20 bg-gradient-to-br from-[#111827] to-emerald-500/[0.03]">
              <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-emerald-500/10 mb-5">
                <Shield size={28} className="text-emerald-400" />
              </div>
              <h2 className="text-2xl font-bold mb-3">The Solution</h2>
              <p className="text-[#94a3b8] mb-6">FaultRay uses <strong className="text-white">pure mathematical simulation</strong>.</p>
              <ul className="space-y-3.5">
                {["Zero risk \u2014 no real faults injected", "Zero cost \u2014 runs on a laptop", "Instant results in seconds", "Works from YAML topology alone", "Mathematically proven availability ceiling"].map((item) => (
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

      {/* Features */}
      <section id="features" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">Everything You Need</h2>
            <p className="text-lg text-[#94a3b8] max-w-[540px] mx-auto">Six pillars of zero-risk chaos engineering</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] transition-all duration-200 hover:border-[#FFD700]/30 hover:bg-[#1a2035] hover:-translate-y-0.5 hover:shadow-[0_0_40px_rgba(255,215,0,0.1)]">
                  <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={24} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2.5">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* AI Agent Resilience */}
      <section id="agent-resilience" className="py-24 bg-[#0f1424] border-t border-[#FFD700]/15">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16">
            <span className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-4">New in v11.0</span>
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">AI Agent Resilience Simulation</h2>
            <p className="text-lg text-[#94a3b8] max-w-[640px] mx-auto">Simulate how infrastructure failures cascade into agent hallucinations &mdash; before they happen in production.</p>
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            {agentFeatures.map((f) => {
              const Icon = f.icon;
              return (
                <div key={f.title} className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] transition-all duration-200 hover:border-[#FFD700]/30 hover:bg-[#1a2035] hover:-translate-y-0.5">
                  <div className="w-14 h-14 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={24} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2.5">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Comparison */}
      <section id="comparison" className="py-24">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">How We Compare</h2>
            <p className="text-lg text-[#94a3b8] max-w-[540px] mx-auto">FaultRay takes a fundamentally different approach</p>
          </div>
          <div className="overflow-x-auto rounded-2xl border border-[#1e293b]">
            <table className="w-full min-w-[700px] border-collapse text-[0.9375rem]">
              <thead>
                <tr>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm" />
                  <th className="px-5 py-4 text-left bg-[#FFD700]/[0.06] text-[#FFD700] font-semibold text-sm">
                    <span className="inline-block px-2 py-0.5 text-[0.6875rem] font-bold text-[#0a0e1a] bg-[#FFD700] rounded-full uppercase tracking-wide mb-1">Recommended</span><br />FaultRay
                  </th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Gremlin</th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">Steadybit</th>
                  <th className="px-5 py-4 text-left bg-[#141a2e] text-[#94a3b8] font-semibold text-sm">AWS FIS</th>
                </tr>
              </thead>
              <tbody>
                {comparison.map((row, i) => (
                  <tr key={row.label} className={i < comparison.length - 1 ? "border-b border-[#1e293b]" : ""}>
                    <td className="px-5 py-4 font-semibold text-white whitespace-nowrap bg-[#111827]">{row.label}</td>
                    <td className="px-5 py-4 bg-[#FFD700]/[0.03] text-white font-medium"><ComparisonCell value={row.faultray} /></td>
                    <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]"><ComparisonCell value={row.gremlin} /></td>
                    <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]"><ComparisonCell value={row.steadybit} /></td>
                    <td className="px-5 py-4 bg-[#111827] text-[#94a3b8]"><ComparisonCell value={row.aws} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 3-Layer Model */}
      <section id="model" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">3-Layer Availability Limit Model</h2>
            <p className="text-lg text-[#94a3b8]">The only tool that proves your availability ceiling</p>
          </div>
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="flex flex-col">
              {[
                { label: "Theoretical Limit", nines: "6.65 nines", pct: "99.999978%", desc: "Mathematical upper bound assuming perfect software and ideal hardware", colorClass: "text-blue-400", border: "border-blue-500/25", bg: "from-blue-500/[0.08]" },
                { label: "Hardware Limit", nines: "5.91 nines", pct: "99.99988%", desc: "Constrained by physical components: disk MTBF, network gear, power systems", colorClass: "text-[#FFD700]", border: "border-[#FFD700]/20", bg: "from-[#FFD700]/[0.06]" },
                { label: "Software Limit", nines: "4.00 nines", pct: "99.99%", desc: "Your actual ceiling: deploy pipelines, config errors, dependency failures", colorClass: "text-emerald-400", border: "border-emerald-500/25", bg: "from-emerald-500/[0.08]" },
              ].map((layer, i) => (
                <div key={layer.label} className={`px-8 py-7 border ${layer.border} bg-gradient-to-br ${layer.bg} to-[#111827] ${i === 0 ? "rounded-t-2xl" : ""} ${i === 2 ? "rounded-b-2xl" : ""}`}>
                  <div className={`font-bold mb-1 ${layer.colorClass}`}>{layer.label}</div>
                  <div className="flex items-baseline gap-4 mb-2">
                    <span className={`text-[1.75rem] font-extrabold tracking-tight ${layer.colorClass}`}>{layer.nines}</span>
                    <span className="text-sm text-[#64748b] font-mono">{layer.pct}</span>
                  </div>
                  <p className="text-sm text-[#94a3b8] leading-relaxed">{layer.desc}</p>
                </div>
              ))}
            </div>
            <div className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827]">
              <h3 className="text-xl font-bold text-[#FFD700] mb-3">Why This Matters</h3>
              <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed mb-5">
                Most teams chase hardware nines while their software layer caps availability at 4 nines. FaultRay reveals exactly where your bottleneck lives so you invest in the right layer.
              </p>
              <code className="block px-4 py-3.5 bg-[#0d1117] rounded-lg font-mono text-[0.8125rem] text-emerald-400 border border-[#1e293b] overflow-x-auto">
                faultray analyze --topology infra.yaml --output 3-layer
              </code>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-24 bg-[#0f1424]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-16">
            <h2 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">Pricing</h2>
            <p className="text-lg text-[#94a3b8]">Start free. Scale as you grow.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6 max-w-[1000px] mx-auto">
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
                <Link href={plan.ctaHref} className={`w-full text-center py-3 rounded-xl font-semibold transition-all ${plan.popular ? "bg-[#FFD700] text-[#0a0e1a] hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)]" : "border border-[#1e293b] text-white hover:border-[#64748b] hover:bg-white/[0.03]"}`}>
                  {plan.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-16 border-t border-[#1e293b]">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="grid md:grid-cols-4 gap-12 mb-12">
            <div>
              <div className="flex items-center gap-2 font-bold mb-3"><Logo size={24} />FaultRay</div>
              <p className="text-sm text-[#64748b] leading-relaxed mb-4 max-w-[300px]">Zero-risk infrastructure chaos engineering. Prove your availability ceiling mathematically.</p>
              <span className="inline-flex items-center gap-1.5 text-[0.8125rem] text-[#64748b] px-3 py-1 border border-[#1e293b] rounded-full">Made in Tokyo</span>
            </div>
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">Product</h4>
              <ul className="space-y-2.5">
                {[["Features", "#features"], ["Comparison", "#comparison"], ["Pricing", "#pricing"]].map(([label, href]) => (
                  <li key={label}><Link href={href} className="text-sm text-[#64748b] hover:text-white transition-colors">{label}</Link></li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">Resources</h4>
              <ul className="space-y-2.5">
                <li><Link href="https://github.com/yutaro-and-and-and/faultray" target="_blank" className="text-sm text-[#64748b] hover:text-white transition-colors">GitHub</Link></li>
                <li><Link href="https://pypi.org/project/faultray/" target="_blank" className="text-sm text-[#64748b] hover:text-white transition-colors">PyPI</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="text-xs font-bold text-[#94a3b8] uppercase tracking-wider mb-4">Legal</h4>
              <ul className="space-y-2.5">
                <li><Link href="https://github.com/yutaro-and-and-and/faultray/blob/main/LICENSE" target="_blank" className="text-sm text-[#64748b] hover:text-white transition-colors">BSL 1.1 License</Link></li>
                <li><Link href="mailto:hello@faultray.dev" className="text-sm text-[#64748b] hover:text-white transition-colors">Contact</Link></li>
              </ul>
            </div>
          </div>
          <div className="pt-6 border-t border-[#1e293b] text-center">
            <p className="text-[0.8125rem] text-[#64748b]">&copy; 2026 FaultRay. Open source under the BSL 1.1 (Business Source License).</p>
          </div>
        </div>
      </footer>
    </>
  );
}
