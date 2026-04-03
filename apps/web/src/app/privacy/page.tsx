import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "FaultRay Privacy Policy — how we collect, use, and protect your data.",
  alternates: { canonical: "https://faultray.com/privacy" },
};

export default function PrivacyPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <div className="mb-10">
        <Link href="/" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
          ← Back to Home
        </Link>
      </div>

      <h1 className="text-3xl font-bold tracking-tight mb-2">Privacy Policy</h1>
      <p className="text-sm text-[var(--text-muted)] mb-12">Last updated: April 1, 2026</p>

      <div className="prose-custom space-y-10 text-[var(--text-secondary)] leading-relaxed">

        {/* 1. Introduction */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">1. Introduction</h2>
          <p>
            FaultRay (&quot;we&quot;, &quot;our&quot;, or &quot;us&quot;) is committed to protecting your personal data. This
            Privacy Policy explains what information we collect, how we use it, and your rights
            regarding your data when you use our infrastructure chaos engineering platform at{" "}
            <a href="https://faultray.com" className="text-[var(--gold)] hover:underline">
              https://faultray.com
            </a>{" "}
            (the &quot;Service&quot;).
          </p>
        </section>

        {/* 2. Data We Collect */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">2. Data We Collect</h2>
          <p className="mb-4">We collect the following categories of data:</p>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-color)]">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Category</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Examples</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Purpose</th>
                </tr>
              </thead>
              <tbody>
                {[
                  {
                    category: "Account Information",
                    examples: "Email address, company name, name",
                    purpose: "Authentication, billing, support",
                  },
                  {
                    category: "Infrastructure Configuration",
                    examples: "Topology YAML files, component names, dependency graphs you upload",
                    purpose: "Running simulations; never shared or sold",
                  },
                  {
                    category: "Usage Data",
                    examples: "Pages visited, features used, simulation counts",
                    purpose: "Product improvement, analytics",
                  },
                  {
                    category: "Payment Information",
                    examples: "Billing address, last 4 digits of card (via Stripe)",
                    purpose: "Subscription management",
                  },
                  {
                    category: "Log & Technical Data",
                    examples: "IP address, browser type, error logs",
                    purpose: "Security, debugging",
                  },
                ].map((row) => (
                  <tr key={row.category} className="border-b border-[var(--border-color)] last:border-0">
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] bg-[var(--bg-card)]">{row.category}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{row.examples}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{row.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 3. How We Store Data */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">3. Data Storage & Infrastructure</h2>
          <p className="mb-3">
            Your data is stored using the following third-party infrastructure providers:
          </p>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Supabase</strong> — Database and authentication.
                Data is stored in the{" "}
                <strong className="text-[var(--text-primary)]">us-east-1</strong> region (AWS). Supabase is
                SOC 2 Type II certified.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Vercel</strong> — Hosting and edge network.
                Your requests may be processed at edge nodes globally, but persistent data is not
                stored on Vercel infrastructure.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Stripe</strong> — Payment processing. We do not
                store full credit card numbers. Stripe is PCI DSS Level 1 certified.
              </span>
            </li>
          </ul>
        </section>

        {/* 4. Third-party sharing */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">4. Third-Party Data Sharing</h2>
          <p className="mb-3">
            <strong className="text-[var(--text-primary)]">We do not sell, rent, or trade your personal data</strong>{" "}
            to third parties for marketing purposes.
          </p>
          <p className="mb-3">
            We may share data with third parties only in the following limited circumstances:
          </p>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>Service providers necessary to operate the Service (Supabase, Vercel, Stripe), bound by data processing agreements.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>When required by law, court order, or government authority.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>In connection with a merger or acquisition, with prior notice to you.</span>
            </li>
          </ul>
          <p className="mt-3">
            Your infrastructure configuration data (topology files, component graphs) is used{" "}
            <strong className="text-[var(--text-primary)]">exclusively</strong> to run simulations on your behalf
            and is never shared with or disclosed to other customers or third parties.
          </p>
        </section>

        {/* 5. Cookies */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">5. Cookies</h2>
          <p className="mb-3">We use the following types of cookies:</p>
          <ul className="space-y-2 ml-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Essential cookies</strong> — Required for
                authentication sessions and basic Service functionality. Cannot be disabled.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Analytics cookies</strong> — Help us understand
                how the Service is used (e.g., Vercel Analytics). You may opt out via browser
                settings or by contacting us.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>
                <strong className="text-[var(--text-primary)]">Preference cookies</strong> — Remember your
                language selection and UI preferences.
              </span>
            </li>
          </ul>
        </section>

        {/* 6. GDPR */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">6. GDPR — Rights for EU/EEA Residents</h2>
          <p className="mb-4">
            If you are located in the European Union or European Economic Area, you have the
            following rights under the General Data Protection Regulation (GDPR):
          </p>
          <ul className="space-y-2 ml-4">
            {[
              {
                right: "Right of access",
                desc: "Request a copy of the personal data we hold about you.",
              },
              {
                right: "Right to rectification",
                desc: "Request correction of inaccurate or incomplete personal data.",
              },
              {
                right: "Right to erasure",
                desc: 'Request deletion of your personal data ("right to be forgotten").',
              },
              {
                right: "Right to restriction",
                desc: "Request that we restrict processing of your personal data.",
              },
              {
                right: "Right to data portability",
                desc: "Receive your data in a structured, machine-readable format.",
              },
              {
                right: "Right to object",
                desc: "Object to processing of your personal data for direct marketing purposes.",
              },
              {
                right: "Right to withdraw consent",
                desc: "Withdraw any consent you have previously given, without affecting lawfulness of prior processing.",
              },
            ].map((item) => (
              <li key={item.right} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>
                  <strong className="text-[var(--text-primary)]">{item.right}</strong> — {item.desc}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-4">
            The legal basis for processing your data is:{" "}
            <strong className="text-[var(--text-primary)]">(a)</strong> performance of a contract (to provide
            the Service), <strong className="text-[var(--text-primary)]">(b)</strong> legitimate interests
            (security, fraud prevention), and <strong className="text-[var(--text-primary)]">(c)</strong> your
            consent (analytics cookies).
          </p>
          <p className="mt-3">
            To exercise any of these rights, contact us at{" "}
            <a href="mailto:privacy@faultray.com" className="text-[var(--gold)] hover:underline">
              privacy@faultray.com
            </a>
            . We will respond within 30 days.
          </p>
        </section>

        {/* 7. Data Retention — RETENTION-DESIGN-01 */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">7. Data Retention</h2>
          <p className="mb-4">
            We retain your personal data for as long as your account is active or as needed to
            provide the Service. The table below defines retention periods by data category:
          </p>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-color)] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Data Category</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Retention Period</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Legal Basis</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { category: "Account data (email, profile)", period: "Until account deletion + 90 days", basis: "Contract performance" },
                  { category: "Simulation results & reports", period: "Free: 30 days  |  Pro/Business: 1 year", basis: "Service provision" },
                  { category: "Audit logs", period: "90 days (Business: 1 year)", basis: "Security / Compliance" },
                  { category: "Billing records", period: "7 years", basis: "Legal obligation (tax law)" },
                  { category: "Infrastructure topology YAML", period: "Until project deleted + 30 days", basis: "Contract performance" },
                  { category: "Analytics data (anonymized)", period: "26 months", basis: "Legitimate interest" },
                  { category: "Support tickets", period: "3 years", basis: "Legitimate interest" },
                ].map((row) => (
                  <tr key={row.category} className="border-b border-[var(--border-color)] last:border-0">
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] bg-[var(--bg-card)]">{row.category}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)] font-mono text-xs">{row.period}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)] text-[var(--text-muted)] text-xs">{row.basis}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            If you delete your account, we will delete or anonymize your personal data within
            90 days, except where legally required to retain it (e.g., financial records for
            7 years). You may request early deletion by emailing{" "}
            <a href="mailto:privacy@faultray.com" className="text-[var(--gold)] hover:underline">
              privacy@faultray.com
            </a>
            .
          </p>
        </section>

        {/* 8. Security */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">8. Security</h2>
          <p>
            We implement industry-standard security measures including TLS encryption in transit,
            encryption at rest (AES-256), role-based access controls, and regular security audits.
            However, no system is completely secure. If you believe your account has been
            compromised, contact us immediately at{" "}
            <a href="mailto:privacy@faultray.com" className="text-[var(--gold)] hover:underline">
              privacy@faultray.com
            </a>
            .
          </p>
        </section>

        {/* 9. Children */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">9. Children&apos;s Privacy</h2>
          <p>
            The Service is not directed to children under the age of 16. We do not knowingly
            collect personal data from children. If you believe we have inadvertently collected
            such data, please contact us and we will delete it promptly.
          </p>
        </section>

        {/* 10. Changes */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">10. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you of material
            changes by email or via a prominent notice in the Service at least 30 days before the
            change takes effect. Continued use of the Service after the effective date constitutes
            acceptance of the updated policy.
          </p>
        </section>

        {/* 11. Contact */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">11. Contact Us</h2>
          <p className="mb-2">
            For privacy-related inquiries or to exercise your rights, contact:
          </p>
          <div className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-1">
            <p className="font-semibold text-[var(--text-primary)]">FaultRay Privacy Team</p>
            <p>
              Email:{" "}
              <a href="mailto:privacy@faultray.com" className="text-[var(--gold)] hover:underline">
                privacy@faultray.com
              </a>
            </p>
            <p>Website: https://faultray.com</p>
          </div>
        </section>
      </div>

      {/* Footer nav */}
      <div className="mt-16 pt-8 border-t border-[var(--border-color)] flex flex-wrap gap-6 text-sm text-[var(--text-muted)]">
        <Link href="/terms" className="hover:text-[var(--text-primary)] transition-colors">
          Terms of Service
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
