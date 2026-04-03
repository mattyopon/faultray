import Link from "next/link";
import type { Metadata } from "next";
import { ShieldCheck, CheckCircle2, AlertTriangle, Clock } from "lucide-react";

// LEGAL-05 / TRUST-01: SLA独立ドキュメント
export const metadata: Metadata = {
  title: "Service Level Agreement (SLA)",
  description: "FaultRay Service Level Agreement — uptime guarantee, response times, and credits for Pro and Business plans.",
  alternates: { canonical: "https://faultray.com/service-level-agreement" },
};

export default function SlaDocPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <div className="mb-10">
        <Link href="/" className="text-sm text-[#64748b] hover:text-white transition-colors">
          ← Back to Home
        </Link>
      </div>

      <div className="flex items-center gap-3 mb-2">
        <ShieldCheck size={28} className="text-[#FFD700]" />
        <h1 className="text-3xl font-bold tracking-tight">Service Level Agreement</h1>
      </div>
      <p className="text-sm text-[#64748b] mb-2">Version 1.0 — Effective: April 1, 2026</p>
      <p className="text-sm text-[#64748b] mb-12">Applies to: FaultRay Pro and Business plans</p>

      <div className="prose-custom space-y-10 text-[#94a3b8] leading-relaxed">

        {/* 1. Uptime Commitment */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">1. Uptime Commitment</h2>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[#1e293b] bg-[#141a2e]">
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Plan</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Uptime Guarantee</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Max Monthly Downtime</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { plan: "Free", uptime: "No SLA", downtime: "Best-effort" },
                  { plan: "Pro", uptime: "99.9%", downtime: "~43.8 minutes/month" },
                  { plan: "Business", uptime: "99.9%", downtime: "~43.8 minutes/month" },
                ].map((row) => (
                  <tr key={row.plan} className="border-b border-[#1e293b] last:border-0">
                    <td className="px-5 py-3 font-semibold text-white bg-[#111827]">{row.plan}</td>
                    <td className="px-5 py-3 bg-[#111827] text-emerald-400 font-bold">{row.uptime}</td>
                    <td className="px-5 py-3 bg-[#111827] font-mono text-xs">{row.downtime}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm">
            &quot;Uptime&quot; means the percentage of time during a calendar month that the FaultRay
            application (https://faultray.com) is accessible and functioning. Scheduled
            maintenance windows (announced 24h in advance via{" "}
            <Link href="/status" className="text-[#FFD700] hover:underline">
              status.faultray.com
            </Link>
            ) are excluded.
          </p>
        </section>

        {/* 2. Service Credits */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">2. Service Credits</h2>
          <p className="mb-4">
            If FaultRay fails to meet the uptime commitment, you are eligible for Service Credits
            applied to future billing:
          </p>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[#1e293b] bg-[#141a2e]">
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Monthly Uptime</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Service Credit</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { uptime: "99.0% – 99.9%", credit: "10% of monthly fee" },
                  { uptime: "95.0% – 99.0%", credit: "25% of monthly fee" },
                  { uptime: "< 95.0%", credit: "50% of monthly fee" },
                ].map((row) => (
                  <tr key={row.uptime} className="border-b border-[#1e293b] last:border-0">
                    <td className="px-5 py-3 font-mono text-white bg-[#111827]">{row.uptime}</td>
                    <td className="px-5 py-3 text-[#FFD700] font-semibold bg-[#111827]">{row.credit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm">
            To claim a Service Credit, submit a request to{" "}
            <a href="mailto:support@faultray.com" className="text-[#FFD700] hover:underline">
              support@faultray.com
            </a>{" "}
            within 30 days of the incident, referencing the incident ID from our status page.
            Credits cannot exceed the monthly subscription fee for the affected month.
          </p>
        </section>

        {/* 3. Support Response Times */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">3. Support Response Times</h2>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[#1e293b] bg-[#141a2e]">
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Plan</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">Channel</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">P1 Response</th>
                  <th className="px-5 py-3 text-left text-[#94a3b8] font-semibold">P2–P3 Response</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { plan: "Free", channel: "Community (GitHub)", p1: "Best-effort", p23: "Best-effort" },
                  { plan: "Pro", channel: "Email", p1: "4 business hours", p23: "1 business day" },
                  { plan: "Business", channel: "Dedicated Slack + Email", p1: "1 hour (24/7)", p23: "4 business hours" },
                ].map((row) => (
                  <tr key={row.plan} className="border-b border-[#1e293b] last:border-0">
                    <td className="px-5 py-3 font-semibold text-white bg-[#111827]">{row.plan}</td>
                    <td className="px-5 py-3 bg-[#111827]">{row.channel}</td>
                    <td className="px-5 py-3 text-emerald-400 font-mono text-xs bg-[#111827]">{row.p1}</td>
                    <td className="px-5 py-3 text-blue-400 font-mono text-xs bg-[#111827]">{row.p23}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 4. Exclusions */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">4. Exclusions</h2>
          <p className="mb-3">This SLA does not apply to downtime caused by:</p>
          <ul className="space-y-2 ml-4">
            {[
              "Scheduled maintenance (announced 24+ hours in advance)",
              "Force majeure events (natural disasters, acts of war, telecommunications failures)",
              "Customer misuse, abuse, or violation of Terms of Service",
              "Third-party service failures (Supabase, Stripe, DNS providers) beyond our reasonable control",
              "Customer-requested configuration changes that cause instability",
              "Incidents lasting less than 5 consecutive minutes",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2 text-sm">
                <span className="text-[#FFD700] shrink-0 mt-1">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* 5. Monitoring */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">5. Monitoring & Transparency</h2>
          <div className="grid md:grid-cols-3 gap-4">
            {[
              { icon: CheckCircle2, title: "Real-time Status", desc: "Live service status and incident history at faultray.com/status", color: "text-emerald-400" },
              { icon: AlertTriangle, title: "Incident Notifications", desc: "Subscribe to email/Slack alerts for service disruptions", color: "text-yellow-400" },
              { icon: Clock, title: "Monthly Reports", desc: "Uptime reports delivered to Business customers on the 1st of each month", color: "text-blue-400" },
            ].map((item) => (
              <div key={item.title} className="p-4 rounded-xl border border-[#1e293b] bg-[#111827]">
                <item.icon size={20} className={`${item.color} mb-2`} />
                <p className="text-sm font-semibold text-white mb-1">{item.title}</p>
                <p className="text-xs text-[#64748b]">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 6. Contact */}
        <section>
          <h2 className="text-xl font-semibold text-white mb-4">6. Contact</h2>
          <p className="mb-4">For SLA questions or credit claims:</p>
          <div className="p-5 rounded-xl border border-[#1e293b] bg-[#111827] space-y-2 text-sm">
            <p>
              <span className="text-white font-semibold">Email: </span>
              <a href="mailto:support@faultray.com" className="text-[#FFD700] hover:underline">
                support@faultray.com
              </a>
            </p>
            <p>
              <span className="text-white font-semibold">Status: </span>
              <Link href="/status" className="text-[#FFD700] hover:underline">
                faultray.com/status
              </Link>
            </p>
            <p>
              <span className="text-white font-semibold">DPA: </span>
              <Link href="/dpa" className="text-[#FFD700] hover:underline">
                faultray.com/dpa
              </Link>
            </p>
          </div>
        </section>
      </div>

      <div className="mt-16 pt-8 border-t border-[#1e293b] flex flex-wrap gap-6 text-sm text-[#64748b]">
        <Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
        <Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
        <Link href="/dpa" className="hover:text-white transition-colors">DPA</Link>
        <Link href="/status" className="hover:text-white transition-colors">Status</Link>
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
      </div>
    </div>
  );
}
