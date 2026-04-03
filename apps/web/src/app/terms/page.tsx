import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "FaultRay Terms of Service — rules and conditions for using the platform.",
  alternates: { canonical: "https://faultray.com/terms" },
};

export default function TermsPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <div className="mb-10">
        <Link href="/" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
          ← Back to Home
        </Link>
      </div>

      <h1 className="text-3xl font-bold tracking-tight mb-2">Terms of Service</h1>
      <p className="text-sm text-[var(--text-muted)] mb-12">Last updated: April 1, 2026</p>

      <div className="space-y-10 text-[var(--text-secondary)] leading-relaxed">

        {/* 1. Overview */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">1. Overview</h2>
          <p>
            These Terms of Service (&quot;Terms&quot;) govern your access to and use of the FaultRay
            infrastructure chaos engineering platform, including our website at{" "}
            <a href="https://faultray.com" className="text-[var(--gold)] hover:underline">
              https://faultray.com
            </a>{" "}
            and all associated services (collectively, the &quot;Service&quot;). By creating an account
            or using the Service, you agree to be bound by these Terms. If you do not agree,
            do not use the Service.
          </p>
          <p className="mt-3">
            FaultRay provides a <strong className="text-[var(--text-primary)]">pure simulation</strong> chaos
            engineering platform that allows SRE and DevOps teams to model and test infrastructure
            failure scenarios without touching production systems.
          </p>
        </section>

        {/* 2. Account Registration */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">2. Account Registration</h2>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>You must provide accurate and complete information when creating an account.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>You are responsible for safeguarding your account credentials. Notify us immediately at{" "}
                <a href="mailto:hello@faultray.com" className="text-[var(--gold)] hover:underline">
                  hello@faultray.com
                </a>{" "}
                if you suspect unauthorized access.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>One account per individual or organization. Sharing accounts is prohibited.</span>
            </li>
          </ul>
        </section>

        {/* 3. Pricing and Payment */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">3. Pricing and Payment</h2>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mb-3">3.1 Subscription Plans</h3>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-color)] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Plan</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Monthly</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Annual (20% off)</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">SLA</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { plan: "Free", monthly: "$0", annual: "$0", sla: "Best effort" },
                  { plan: "Pro", monthly: "$299/mo", annual: "$2,870/yr", sla: "99.9% uptime" },
                  { plan: "Business", monthly: "$999/mo", annual: "$9,590/yr", sla: "99.9% uptime" },
                ].map((row) => (
                  <tr key={row.plan} className="border-b border-[var(--border-color)] last:border-0">
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] bg-[var(--bg-card)]">{row.plan}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{row.monthly}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{row.annual}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{row.sla}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm">
            All prices are in USD. Japanese yen pricing (JPY) is available on request. Prices
            are exclusive of applicable taxes.
          </p>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mt-5 mb-3">3.2 Billing</h3>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Subscriptions are billed in advance on a monthly or annual basis via Stripe.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Annual subscriptions are non-refundable except as required by applicable law or as described in Section 3.3.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Monthly subscriptions may be cancelled at any time; access continues until the end of the billing period.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Failed payments will result in a 7-day grace period, after which the account will be downgraded to Free.</span>
            </li>
          </ul>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mt-5 mb-3">3.3 Free Trial</h3>
          <p>
            Pro plan subscribers receive a 14-day free trial. You will not be charged until the
            trial period ends. Cancel at any time during the trial to avoid charges.
          </p>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mt-5 mb-3">3.4 Refunds</h3>
          <p>
            Monthly subscribers may request a pro-rated refund within 7 days of a billing cycle
            if the Service experienced unplanned downtime exceeding SLA commitments. Refund
            requests must be submitted to{" "}
            <a href="mailto:hello@faultray.com" className="text-[var(--gold)] hover:underline">
              hello@faultray.com
            </a>
            .
          </p>
        </section>

        {/* 4. Acceptable Use */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">4. Acceptable Use and Prohibited Activities</h2>
          <p className="mb-3">You agree <strong className="text-[var(--text-primary)]">not</strong> to:</p>
          <ul className="space-y-2 ml-4">
            {[
              "Use the Service to attack, probe, or disrupt third-party systems without authorization.",
              "Attempt to reverse-engineer, decompile, or extract source code from the Service.",
              "Circumvent usage limits or access controls (e.g., creating multiple Free accounts).",
              "Upload malicious code, exploits, or content that violates applicable law.",
              "Resell or sublicense access to the Service without prior written consent.",
              "Use simulation results as the sole basis for production decisions without independent verification.",
              "Violate any applicable law, regulation, or third-party rights.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-red-400 shrink-0 mt-1">✕</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* 5. Disclaimer */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">5. Disclaimer — Simulation Results are Reference Values</h2>
          <div className="p-5 rounded-xl border border-yellow-500/20 bg-yellow-500/[0.04] mb-4">
            <p className="text-yellow-200 font-semibold mb-2">Important Disclaimer</p>
            <p>
              FaultRay is a <strong>pure simulation platform</strong>. All availability scores,
              failure probabilities, DORA metrics, and analysis outputs are{" "}
              <strong>reference values based on mathematical models</strong> — they do not
              constitute guarantees of actual system behavior, uptime, or compliance.
            </p>
          </div>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Simulation results depend on the accuracy and completeness of the topology data you provide.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>FaultRay does not guarantee that using the Service will prevent outages or improve production availability.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                THE SERVICE IS PROVIDED &quot;AS IS&quot; WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR
                IMPLIED, INCLUDING WITHOUT LIMITATION WARRANTIES OF MERCHANTABILITY, FITNESS FOR
                A PARTICULAR PURPOSE, OR NON-INFRINGEMENT.
              </span>
            </li>
          </ul>
        </section>

        {/* 6. Limitation of Liability */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">6. Limitation of Liability</h2>
          <p className="mb-3">
            TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, FAULTRAY SHALL NOT BE LIABLE FOR
            ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES, INCLUDING
            LOSS OF PROFITS, DATA, OR BUSINESS OPPORTUNITIES, ARISING FROM YOUR USE OF OR
            INABILITY TO USE THE SERVICE.
          </p>
          <p>
            OUR TOTAL AGGREGATE LIABILITY TO YOU FOR ALL CLAIMS ARISING FROM OR RELATED TO
            THESE TERMS OR THE SERVICE SHALL NOT EXCEED THE GREATER OF (A) THE AMOUNTS PAID
            BY YOU IN THE 12 MONTHS PRECEDING THE CLAIM, OR (B) USD $100.
          </p>
        </section>

        {/* 7. SLA */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">7. Service Level Agreement (SLA)</h2>
          <p className="mb-3">
            For Pro and Business subscribers, FaultRay commits to{" "}
            <strong className="text-[var(--text-primary)]">99.9% monthly uptime</strong> (approximately 8.7
            hours of permitted downtime per year), excluding:
          </p>
          <ul className="space-y-2 ml-4 mb-4">
            {[
              "Scheduled maintenance windows (announced at least 48 hours in advance).",
              "Force majeure events (natural disasters, infrastructure provider outages beyond our control).",
              "Issues caused by customer actions or third-party integrations.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <p>
            Service status is published at{" "}
            <a
              href="https://status.faultray.com"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--gold)] hover:underline"
            >
              https://status.faultray.com
            </a>
            . SLA credits (up to 30% of monthly fee) may be requested if uptime falls below
            99.9% in a given month.
          </p>
        </section>

        {/* 8. Termination */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">8. Cancellation and Termination</h2>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mb-3">8.1 Cancellation by You</h3>
          <p className="mb-3">
            You may cancel your subscription at any time from your account settings or by
            contacting{" "}
            <a href="mailto:hello@faultray.com" className="text-[var(--gold)] hover:underline">
              hello@faultray.com
            </a>
            . Upon cancellation:
          </p>
          <ul className="space-y-2 ml-4 mb-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Monthly plans: access continues until the end of the current billing period.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Annual plans: access continues until the end of the annual term; no pro-rated refund unless SLA was breached.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Your data will be retained for 30 days after cancellation, after which it will be deleted. You may export your data before cancellation.</span>
            </li>
          </ul>

          <h3 className="text-base font-semibold text-[var(--text-primary)] mb-3">8.2 Termination by FaultRay</h3>
          <p>
            We reserve the right to suspend or terminate your account immediately, without
            notice, if you materially violate these Terms, engage in fraudulent activity, or
            otherwise cause harm to the Service or other users. In such cases, no refund will
            be provided.
          </p>
        </section>

        {/* 9. Intellectual Property */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">9. Intellectual Property</h2>
          <p className="mb-3">
            The Service and all associated software, algorithms, models, and content are owned
            by FaultRay and protected by intellectual property laws.
          </p>
          <p>
            You retain full ownership of the infrastructure topology data and configuration
            files you upload. You grant FaultRay a limited, non-exclusive license to process
            that data solely for the purpose of providing the Service.
          </p>
        </section>

        {/* 10. Governing Law */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">10. Governing Law and Dispute Resolution</h2>
          <p className="mb-3">
            These Terms are governed by and construed in accordance with the laws of{" "}
            <strong className="text-[var(--text-primary)]">Japan</strong>, without regard to its conflict of
            law provisions.
          </p>
          <p className="mb-3">
            Any disputes arising from or relating to these Terms shall be subject to the
            exclusive jurisdiction of the{" "}
            <strong className="text-[var(--text-primary)]">Tokyo District Court</strong> as the court of first
            instance, unless otherwise required by applicable consumer protection law.
          </p>
          <p>
            For EU/EEA residents, nothing in these Terms limits your rights under applicable
            mandatory consumer protection law in your country of residence.
          </p>
        </section>

        {/* 11. Anti-Social Forces Exclusion */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">
            11. Exclusion of Anti-Social Forces（反社会的勢力の排除）
          </h2>
          <p className="mb-2 text-sm text-[var(--text-muted)]">
            ※ 日本語要約: 暴力団、暴力団員、暴力団準構成員、暴力団関係企業その他の反社会的勢力に該当する方はサービスをご利用いただけません。
          </p>
          <p className="mb-3">
            You represent and warrant that you are not, and none of your officers, directors,
            employees, agents, or affiliates are, any of the following (collectively,
            &quot;Anti-Social Forces&quot;):
          </p>
          <ul className="space-y-2 ml-4 mb-4">
            {[
              "An organized crime group (boryokudan) or a member thereof.",
              "A quasi-member of an organized crime group.",
              "A company or organization affiliated with, controlled by, or substantially influenced by an organized crime group.",
              "A corporate extortionist (sokaiya), a group engaging in criminal activities under the pretext of social movements, or a crime group specialized in intellectual crimes.",
              "Any other person equivalent to the above.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-red-400 shrink-0 mt-1">✕</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <p className="mb-3">
            You further represent and warrant that you will not, directly or indirectly:
          </p>
          <ul className="space-y-2 ml-4 mb-4">
            {[
              "Make violent demands or demands with threats.",
              "Make unreasonable demands beyond legal liability.",
              "Use threatening behavior or violence in connection with the Service.",
              "Damage FaultRay's reputation or interfere with its business by spreading rumors or using fraudulent means.",
              "Cause others to engage in any of the foregoing acts.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-red-400 shrink-0 mt-1">✕</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
          <p>
            If FaultRay determines that you or any associated party constitutes Anti-Social
            Forces or engages in the prohibited conduct above, FaultRay may immediately
            terminate your account without notice and without liability for any resulting
            damages.
          </p>
        </section>

        {/* 12. Changes */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">12. Changes to These Terms</h2>
          <p>
            We may update these Terms from time to time. We will provide at least 30 days&apos;
            notice of material changes via email or a prominent notice in the Service. Continued
            use after the effective date constitutes acceptance. If you disagree with the
            updated Terms, you may cancel your subscription before the effective date.
          </p>
        </section>

        {/* 13. Contact */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">13. Contact</h2>
          <p className="mb-4">
            For questions about these Terms, contact us at:
          </p>
          <div className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-1">
            <p className="font-semibold text-[var(--text-primary)]">FaultRay</p>
            <p>
              Email:{" "}
              <a href="mailto:hello@faultray.com" className="text-[var(--gold)] hover:underline">
                hello@faultray.com
              </a>
            </p>
            <p>Website: https://faultray.com</p>
          </div>
        </section>
      </div>

      {/* Footer nav */}
      <div className="mt-16 pt-8 border-t border-[var(--border-color)] flex flex-wrap gap-6 text-sm text-[var(--text-muted)]">
        <Link href="/privacy" className="hover:text-[var(--text-primary)] transition-colors">
          Privacy Policy
        </Link>
        <Link href="/dpa" className="hover:text-[var(--text-primary)] transition-colors">
          DPA
        </Link>
        <Link href="/contact" className="hover:text-[var(--text-primary)] transition-colors">
          Contact
        </Link>
        <Link href="/" className="hover:text-[var(--text-primary)] transition-colors">
          Home
        </Link>
      </div>
    </div>
  );
}
