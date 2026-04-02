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
        className="inline-flex items-center gap-1.5 text-sm text-[#64748b] hover:text-white transition-colors mb-8"
      >
        <ArrowLeft size={14} />
        Back to Home
      </Link>

      <div className="mb-10">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
          Contact Us
        </h1>
        <p className="text-[#94a3b8] leading-relaxed">
          Tell us about your infrastructure challenges. We&apos;ll follow up
          within one business day.
        </p>
      </div>

      {submitted ? (
        <div className="p-8 rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-[#111827] to-emerald-500/[0.04] text-center">
          <CheckCircle size={48} className="text-emerald-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">Message sent!</h2>
          <p className="text-[#94a3b8] mb-6">
            Thank you for reaching out. We&apos;ll get back to you within one
            business day.
          </p>
          <Link
            href="/"
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] transition-colors"
          >
            Back to Home
          </Link>
        </div>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] space-y-5"
        >
          {/* Company */}
          <div>
            <label
              htmlFor="company"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              Company Name <span className="text-red-400">*</span>
            </label>
            <input
              id="company"
              name="company"
              type="text"
              required
              value={form.company}
              onChange={handleChange}
              placeholder="Acme Corp"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              Your Name <span className="text-red-400">*</span>
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              value={form.name}
              onChange={handleChange}
              placeholder="Jane Smith"
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
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
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Company size */}
          <div>
            <label
              htmlFor="companySize"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              Company Size <span className="text-red-400">*</span>
            </label>
            <select
              id="companySize"
              name="companySize"
              required
              value={form.companySize}
              onChange={handleChange}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm appearance-none"
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
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              Challenges &amp; Questions <span className="text-red-400">*</span>
            </label>
            <textarea
              id="message"
              name="message"
              required
              rows={5}
              value={form.message}
              onChange={handleChange}
              placeholder="Describe your infrastructure, current reliability challenges, and what you hope to achieve with FaultRay..."
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm resize-none"
            />
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-[0_0_20px_rgba(255,215,0,0.2)]"
          >
            <Send size={16} />
            {submitting ? "Sending..." : "Send Message"}
          </button>
        </form>
      )}
    </div>
  );
}
