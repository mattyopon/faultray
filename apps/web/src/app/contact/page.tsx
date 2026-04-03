"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Send, CheckCircle } from "lucide-react";

const COMPANY_SIZE_OPTIONS = [
  { value: "1-10", label: "1–10 employees" },
  { value: "11-50", label: "11–50 employees" },
  { value: "51-200", label: "51–200 employees" },
  { value: "201-1000", label: "201–1,000 employees" },
  { value: "1000+", label: "1,000+ employees" },
];

interface FormState {
  company: string;
  name: string;
  email: string;
  companySize: string;
  message: string;
}

const INITIAL_FORM: FormState = {
  company: "",
  name: "",
  email: "",
  companySize: "",
  message: "",
};

export default function ContactPage() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleChange(
    e: React.ChangeEvent<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { error: dbError } = await supabase
        .from("contact_requests")
        .insert({
          company: form.company,
          name: form.name,
          email: form.email,
          company_size: form.companySize,
          message: form.message,
        });

      if (dbError) throw dbError;

      setSubmitted(true);
      setForm(INITIAL_FORM);
    } catch (err) {
      // Supabase not configured or insert failed — show user-friendly error
      const message =
        err instanceof Error ? err.message : "Submission failed. Please try again.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[640px] mx-auto px-6 py-20">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors mb-8"
      >
        <ArrowLeft size={14} />
        Back to Home
      </Link>

      <div className="mb-10">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
          Contact Us
        </h1>
        <p className="text-[var(--text-secondary)] leading-relaxed">
          Tell us about your infrastructure challenges. We&apos;ll follow up
          within one business day.
        </p>
      </div>

      {/* JP-03: 稟議決裁サポートバナー */}
      <div className="mb-6 p-4 rounded-xl border border-blue-500/20 bg-blue-500/[0.04] flex items-start gap-3">
        <span className="text-blue-400 text-lg mt-0.5">🗂</span>
        <div>
          <p className="text-sm font-semibold text-blue-300 mb-1">日本企業向け：稟議書テンプレート提供中</p>
          <p className="text-xs text-[var(--text-secondary)]">
            社内承認プロセス（稟議決裁）に必要なコスト・ROI・セキュリティをまとめたテンプレートを無償提供しています。
            導入検討段階でお気軽にご相談ください。
          </p>
          <Link href="/ringi" className="text-xs text-blue-400 hover:text-blue-300 transition-colors mt-1 inline-block">
            稟議書テンプレートを見る →
          </Link>
        </div>
      </div>

      {/* COMP-04: Multiple demo formats */}
      <div className="mb-8 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <a
          href="/simulate"
          className="flex flex-col gap-2 p-5 rounded-xl border border-[var(--gold)]/20 bg-[var(--gold)]/[0.04] hover:bg-[var(--gold)]/[0.08] transition-all"
        >
          <span className="text-[var(--gold)] font-bold text-sm">Self-Service Demo</span>
          <span className="text-xs text-[var(--text-secondary)]">Run a simulation instantly — no account required</span>
          <span className="text-xs text-[var(--text-muted)] mt-1">Available now →</span>
        </a>
        <div className="flex flex-col gap-2 p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]">
          <span className="text-[var(--text-primary)] font-bold text-sm">Guided Demo (30 min)</span>
          <span className="text-xs text-[var(--text-secondary)]">Live walkthrough with a FaultRay engineer via video call</span>
          <span className="text-xs text-[var(--text-muted)] mt-1">Fill the form below →</span>
        </div>
        <a
          href="mailto:sales@faultray.com?subject=PoC%20Request"
          className="flex flex-col gap-2 p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--text-muted)] transition-all"
        >
          <span className="text-[var(--text-primary)] font-bold text-sm">PoC (Proof of Concept)</span>
          <span className="text-xs text-[var(--text-secondary)]">2-week free trial with your actual infrastructure</span>
          <span className="text-xs text-[var(--text-muted)] mt-1">Email us →</span>
        </a>
      </div>

      {submitted ? (
        <div className="p-8 rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-[var(--bg-card)] to-emerald-500/[0.04] text-center">
          <CheckCircle size={48} className="text-emerald-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">Message sent!</h2>
          <p className="text-[var(--text-secondary)] mb-6">
            Thank you for reaching out. We&apos;ll get back to you within one
            business day.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--gold)] text-white font-semibold rounded-xl hover:bg-[#044a99] transition-colors"
          >
            Back to Home
          </Link>
        </div>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-5"
        >
          {/* Company */}
          <div>
            <label
              htmlFor="company"
              className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5"
            >
              Company Name <span className="text-red-400">*</span>
            </label>
            <input
              id="company"
              name="company"
              type="text"
              required
              maxLength={100}
              value={form.company}
              onChange={handleChange}
              placeholder="Acme Corp"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[var(--border-color)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--gold)]/50 transition-colors text-sm"
            />
          </div>

          {/* Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5"
            >
              Your Name <span className="text-red-400">*</span>
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              maxLength={100}
              value={form.name}
              onChange={handleChange}
              placeholder="Jane Smith"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[var(--border-color)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--gold)]/50 transition-colors text-sm"
            />
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5"
            >
              Work Email <span className="text-red-400">*</span>
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              value={form.email}
              onChange={handleChange}
              placeholder="jane@acmecorp.com"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[var(--border-color)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--gold)]/50 transition-colors text-sm"
            />
          </div>

          {/* Company size */}
          <div>
            <label
              htmlFor="companySize"
              className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5"
            >
              Company Size <span className="text-red-400">*</span>
            </label>
            <select
              id="companySize"
              name="companySize"
              required
              value={form.companySize}
              onChange={handleChange}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[var(--border-color)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--gold)]/50 transition-colors text-sm appearance-none"
            >
              <option value="" disabled>
                Select company size
              </option>
              {COMPANY_SIZE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          {/* Message */}
          <div>
            <label
              htmlFor="message"
              className="block text-sm font-medium text-[var(--text-secondary)] mb-1.5"
            >
              Challenges &amp; Questions <span className="text-red-400">*</span>
            </label>
            <textarea
              id="message"
              name="message"
              required
              rows={5}
              maxLength={2000}
              value={form.message}
              onChange={handleChange}
              placeholder="Describe your infrastructure, current reliability challenges, and what you hope to achieve with FaultRay..."
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[var(--border-color)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--gold)]/50 transition-colors text-sm resize-none"
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 bg-[var(--gold)] text-white font-semibold rounded-xl hover:bg-[#044a99] disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-md"
          >
            <Send size={16} />
            {submitting ? "Sending..." : "Send Message"}
          </button>
        </form>
      )}
    </div>
  );
}
