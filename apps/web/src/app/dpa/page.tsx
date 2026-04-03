import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data Processing Agreement",
  description:
    "FaultRay Data Processing Agreement (DPA) — GDPR Article 28 compliant template for enterprise customers.",
  alternates: { canonical: "https://faultray.com/dpa" },
};

export default function DpaPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <div className="mb-10">
        <Link href="/" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors">
          ← Back to Home
        </Link>
      </div>

      <h1 className="text-3xl font-bold tracking-tight mb-2">Data Processing Agreement</h1>
      <p className="text-sm text-[var(--text-muted)] mb-2">
        GDPR Article 28 Compliant Template — Last updated: April 1, 2026
      </p>
      <p className="text-sm text-[var(--text-secondary)] mb-12">
        This Data Processing Agreement (&quot;DPA&quot;) is entered into between FaultRay
        (&quot;Data Processor&quot;) and the Customer (&quot;Data Controller&quot;) identified in
        the applicable order form or subscription agreement.
      </p>

      <div className="space-y-10 text-[var(--text-secondary)] leading-relaxed">

        {/* 1. Definitions */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">1. Definitions</h2>
          <ul className="space-y-2 ml-4">
            {[
              ['"Personal Data"', "Any information relating to an identified or identifiable natural person as defined under GDPR Article 4(1)."],
              ['"Processing"', "Any operation performed on Personal Data, as defined under GDPR Article 4(2)."],
              ['"Data Controller"', "The Customer who determines the purposes and means of processing Personal Data."],
              ['"Data Processor"', "FaultRay, which processes Personal Data on behalf of the Data Controller."],
              ['"Sub-processor"', "Any third party engaged by FaultRay to assist in processing Personal Data."],
              ['"GDPR"', "Regulation (EU) 2016/679 of the European Parliament and of the Council."],
            ].map(([term, def]) => (
              <li key={term as string} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>
                  <strong className="text-[var(--text-primary)]">{term}</strong> — {def}
                </span>
              </li>
            ))}
          </ul>
        </section>

        {/* 2. Scope and Purpose */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">2. Scope and Purpose</h2>
          <p className="mb-3">
            This DPA governs the processing of Personal Data by FaultRay on behalf of the
            Customer in connection with the provision of the FaultRay infrastructure chaos
            engineering platform (the &quot;Service&quot;).
          </p>
          <p>
            FaultRay processes Personal Data only for the purpose of providing, maintaining,
            and improving the Service as described in the main Terms of Service, and only on
            documented instructions from the Customer.
          </p>
        </section>

        {/* 3. Nature of Processing */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">3. Nature, Purpose, and Duration of Processing</h2>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-color)] mb-4">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Item</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Details</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Subject matter", "Operation of the FaultRay platform"],
                  ["Nature", "Collection, storage, transmission, analysis, deletion"],
                  ["Purpose", "User authentication, service delivery, support, analytics"],
                  ["Duration", "For the term of the subscription agreement, plus 30-day retention period"],
                  ["Categories of data subjects", "Customer employees and authorized users of the Service"],
                  ["Categories of personal data", "Name, email address, IP address, usage logs, authentication tokens"],
                ].map(([item, detail]) => (
                  <tr key={item as string} className="border-b border-[var(--border-color)] last:border-0">
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] bg-[var(--bg-card)] w-1/3">{item}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 4. Processor Obligations (GDPR Art. 28) */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">
            4. Processor Obligations (GDPR Article 28)
          </h2>
          <p className="mb-3">FaultRay, as Data Processor, shall:</p>
          <ul className="space-y-2 ml-4">
            {[
              "Process Personal Data only on documented instructions from the Data Controller, unless required to do so by applicable law.",
              "Ensure that persons authorized to process Personal Data are bound by confidentiality obligations.",
              "Implement appropriate technical and organizational security measures in accordance with GDPR Article 32.",
              "Respect the conditions for engaging Sub-processors as set forth in Section 5.",
              "Assist the Data Controller in responding to requests from data subjects exercising their rights under GDPR Chapter III.",
              "Assist the Data Controller in ensuring compliance with GDPR Articles 32–36 (security, breach notification, DPIAs).",
              "Delete or return all Personal Data to the Data Controller upon termination of the Service, unless required to retain it by applicable law.",
              "Make available all information necessary to demonstrate compliance with GDPR Article 28 obligations, and allow for audits.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* 5. Sub-processors */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">5. Sub-processors</h2>
          <p className="mb-3">
            The Customer grants FaultRay general authorization to engage Sub-processors,
            subject to the following conditions:
          </p>
          <ul className="space-y-2 ml-4 mb-4">
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>FaultRay will maintain a list of current Sub-processors and provide at least 14 days&apos; prior notice of any intended changes.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>The Customer may object to new Sub-processors on reasonable grounds within 14 days of notice.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
              <span>FaultRay imposes equivalent data protection obligations on each Sub-processor.</span>
            </li>
          </ul>
          <p className="text-sm font-semibold text-[var(--text-primary)] mb-2">Current Sub-processors:</p>
          <div className="overflow-x-auto rounded-xl border border-[var(--border-color)]">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-[var(--border-color)] bg-[var(--bg-tertiary)]">
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Sub-processor</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Purpose</th>
                  <th scope="col" className="px-5 py-3 text-left text-[var(--text-secondary)] font-semibold">Location</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["Supabase", "Authentication, database hosting", "USA (AWS us-east-1)"],
                  ["Vercel", "Application hosting and edge delivery", "Global CDN"],
                  ["Stripe", "Payment processing", "USA"],
                  ["Google Analytics", "Usage analytics (consent-gated)", "USA"],
                ].map(([name, purpose, location]) => (
                  <tr key={name as string} className="border-b border-[var(--border-color)] last:border-0">
                    <td className="px-5 py-3 font-medium text-[var(--text-primary)] bg-[var(--bg-card)]">{name}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{purpose}</td>
                    <td className="px-5 py-3 bg-[var(--bg-card)]">{location}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 6. Security Measures */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">6. Security Measures (GDPR Article 32)</h2>
          <p className="mb-3">
            FaultRay implements the following technical and organizational measures to protect
            Personal Data:
          </p>
          <ul className="space-y-2 ml-4">
            {[
              "Encryption of data in transit (TLS 1.2+) and at rest (AES-256).",
              "Access controls: role-based access, least privilege principle.",
              "Authentication: OAuth2/PKCE via Supabase Auth with secure session management.",
              "Logging and monitoring: access and security event logs retained for 90 days.",
              "Incident response: breach detection procedures with 72-hour notification capability.",
              "Regular security assessments and penetration testing.",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* 7. International Transfers */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">7. International Data Transfers</h2>
          <p>
            Where Personal Data is transferred outside the European Economic Area (EEA),
            FaultRay ensures adequate safeguards are in place, including Standard Contractual
            Clauses (SCCs) as adopted by the European Commission. Customers may request copies
            of applicable SCCs by contacting{" "}
            <a href="mailto:hello@faultray.com" className="text-[var(--gold)] hover:underline">
              hello@faultray.com
            </a>
            .
          </p>
        </section>

        {/* 8. Data Subject Rights */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">8. Data Subject Rights</h2>
          <p className="mb-3">
            FaultRay will assist the Data Controller in fulfilling data subject requests
            within the timeframes required by GDPR, including:
          </p>
          <ul className="space-y-2 ml-4">
            {[
              "Right of access (Article 15)",
              "Right to rectification (Article 16)",
              "Right to erasure / right to be forgotten (Article 17)",
              "Right to restriction of processing (Article 18)",
              "Right to data portability (Article 20)",
              "Right to object (Article 21)",
            ].map((right) => (
              <li key={right} className="flex items-start gap-2">
                <span className="text-[var(--gold)] shrink-0 mt-1">•</span>
                <span>{right}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* 9. Breach Notification */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">9. Personal Data Breach Notification</h2>
          <p>
            In the event of a Personal Data breach, FaultRay will notify the Data Controller
            without undue delay and in any event within <strong className="text-[var(--text-primary)]">48 hours</strong>{" "}
            of becoming aware of the breach. The notification will include: (a) the nature of
            the breach; (b) categories and approximate number of data subjects and records
            concerned; (c) likely consequences; (d) measures taken or proposed to address the
            breach.
          </p>
        </section>

        {/* 10. Audit */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">10. Audit Rights</h2>
          <p>
            The Data Controller may, upon 30 days&apos; written notice, conduct or commission
            an audit of FaultRay&apos;s data processing activities to verify compliance with
            this DPA. Audits shall not unreasonably interfere with FaultRay&apos;s operations.
            FaultRay may satisfy audit requests by providing relevant certifications or third-
            party audit reports.
          </p>
        </section>

        {/* 11. Term */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">11. Term and Termination</h2>
          <p>
            This DPA is effective for the duration of the underlying subscription agreement.
            Upon termination, FaultRay will delete or return all Personal Data within 30 days,
            unless longer retention is required by applicable law.
          </p>
        </section>

        {/* 12. Contact */}
        <section>
          <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">12. Contact</h2>
          <p className="mb-4">
            For data protection inquiries or to execute a signed DPA for enterprise agreements,
            contact:
          </p>
          <div className="p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-1">
            <p className="font-semibold text-[var(--text-primary)]">FaultRay — Data Protection</p>
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
