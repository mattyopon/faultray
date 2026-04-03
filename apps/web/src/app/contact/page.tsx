"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Send, CheckCircle } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

const COMPANY_SIZE_OPTIONS_EN = [
  { value: "1-10", label: "1–10 employees" },
  { value: "11-50", label: "11–50 employees" },
  { value: "51-200", label: "51–200 employees" },
  { value: "201-1000", label: "201–1,000 employees" },
  { value: "1000+", label: "1,000+ employees" },
];

const COMPANY_SIZE_OPTIONS_JA = [
  { value: "1-10", label: "1〜10名" },
  { value: "11-50", label: "11〜50名" },
  { value: "51-200", label: "51〜200名" },
  { value: "201-1000", label: "201〜1,000名" },
  { value: "1000+", label: "1,000名以上" },
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

function ContactForm() {
  const searchParams = useSearchParams();
  const lang = searchParams.get("lang") === "ja" ? "ja" : "en";
  const isJa = lang === "ja";

  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const companySizeOptions = isJa ? COMPANY_SIZE_OPTIONS_JA : COMPANY_SIZE_OPTIONS_EN;

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
      const message =
        err instanceof Error
          ? err.message
          : isJa
          ? "送信に失敗しました。もう一度お試しください。"
          : "Submission failed. Please try again.";
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-[640px] mx-auto px-6 py-20">
      <Link
        href={isJa ? "/ja" : "/"}
        className="inline-flex items-center gap-1.5 text-sm text-[#64748b] hover:text-white transition-colors mb-8"
      >
        <ArrowLeft size={14} />
        {isJa ? "トップページに戻る" : "Back to Home"}
      </Link>

      <div className="mb-10">
        <h1 className="text-[clamp(1.75rem,4vw,2.5rem)] font-bold tracking-tight mb-3">
          {isJa ? "お問い合わせ" : "Contact Us"}
        </h1>
        <p className="text-[#94a3b8] leading-relaxed">
          {isJa
            ? "インフラの課題をお聞かせください。1営業日以内にご返信いたします。"
            : "Tell us about your infrastructure challenges. We'll follow up within one business day."}
        </p>
      </div>

      {/* JP-03: 稟議決裁サポートバナー */}
      <div className="mb-6 p-4 rounded-xl border border-blue-500/20 bg-blue-500/[0.04] flex items-start gap-3">
        <span className="text-blue-400 text-lg mt-0.5">🗂</span>
        <div>
          <p className="text-sm font-semibold text-blue-300 mb-1">
            {isJa
              ? "日本企業向け：稟議書テンプレート提供中"
              : "For Japanese companies: Free Ringi (approval) template available"}
          </p>
          <p className="text-xs text-[#94a3b8]">
            {isJa
              ? "社内承認プロセス（稟議決裁）に必要なコスト・ROI・セキュリティをまとめたテンプレートを無償提供しています。導入検討段階でお気軽にご相談ください。"
              : "We provide a free template covering cost, ROI, and security for your internal approval process. Feel free to reach out at any stage."}
          </p>
          <Link
            href="/ringi"
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors mt-1 inline-block"
          >
            {isJa ? "稟議書テンプレートを見る →" : "View Ringi template →"}
          </Link>
        </div>
      </div>

      {/* COMP-04: Multiple demo formats */}
      <div className="mb-8 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <a
          href="/simulate"
          className="flex flex-col gap-2 p-5 rounded-xl border border-[#FFD700]/20 bg-[#FFD700]/[0.04] hover:bg-[#FFD700]/[0.08] transition-all"
        >
          <span className="text-[#FFD700] font-bold text-sm">
            {isJa ? "セルフサービスデモ" : "Self-Service Demo"}
          </span>
          <span className="text-xs text-[#94a3b8]">
            {isJa
              ? "アカウント不要で今すぐシミュレーション実行"
              : "Run a simulation instantly — no account required"}
          </span>
          <span className="text-xs text-[#64748b] mt-1">
            {isJa ? "今すぐ試す →" : "Available now →"}
          </span>
        </a>
        <div className="flex flex-col gap-2 p-5 rounded-xl border border-[#1e293b] bg-[#111827]">
          <span className="text-white font-bold text-sm">
            {isJa ? "ガイド付きデモ（30分）" : "Guided Demo (30 min)"}
          </span>
          <span className="text-xs text-[#94a3b8]">
            {isJa
              ? "FaultRayエンジニアによるビデオ通話でのライブ案内"
              : "Live walkthrough with a FaultRay engineer via video call"}
          </span>
          <span className="text-xs text-[#64748b] mt-1">
            {isJa ? "下のフォームから →" : "Fill the form below →"}
          </span>
        </div>
        <a
          href="mailto:sales@faultray.com?subject=PoC%20Request"
          className="flex flex-col gap-2 p-5 rounded-xl border border-[#1e293b] bg-[#111827] hover:border-[#64748b] transition-all"
        >
          <span className="text-white font-bold text-sm">
            {isJa ? "PoC（概念実証）" : "PoC (Proof of Concept)"}
          </span>
          <span className="text-xs text-[#94a3b8]">
            {isJa
              ? "実際のインフラを使った2週間無料トライアル"
              : "2-week free trial with your actual infrastructure"}
          </span>
          <span className="text-xs text-[#64748b] mt-1">
            {isJa ? "メールで問い合わせ →" : "Email us →"}
          </span>
        </a>
      </div>

      {submitted ? (
        <div className="p-8 rounded-2xl border border-emerald-500/30 bg-gradient-to-br from-[#111827] to-emerald-500/[0.04] text-center">
          <CheckCircle size={48} className="text-emerald-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold mb-2">
            {isJa ? "送信が完了しました" : "Message sent!"}
          </h2>
          <p className="text-[#94a3b8] mb-6">
            {isJa
              ? "お問い合わせありがとうございます。1営業日以内にご返信いたします。"
              : "Thank you for reaching out. We'll get back to you within one business day."}
          </p>
          <Link
            href={isJa ? "/ja" : "/"}
            className="inline-flex items-center gap-2 px-6 py-2.5 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] transition-colors"
          >
            {isJa ? "トップページへ戻る" : "Back to Home"}
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
              {isJa ? "会社名" : "Company Name"}{" "}
              <span className="text-red-400">*</span>
            </label>
            <input
              id="company"
              name="company"
              type="text"
              required
              maxLength={100}
              value={form.company}
              onChange={handleChange}
              placeholder={isJa ? "株式会社〇〇" : "Acme Corp"}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Name */}
          <div>
            <label
              htmlFor="name"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              {isJa ? "お名前" : "Your Name"}{" "}
              <span className="text-red-400">*</span>
            </label>
            <input
              id="name"
              name="name"
              type="text"
              required
              maxLength={100}
              value={form.name}
              onChange={handleChange}
              placeholder={isJa ? "山田 太郎" : "Jane Smith"}
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Email */}
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              {isJa ? "メールアドレス" : "Work Email"}{" "}
              <span className="text-red-400">*</span>
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              value={form.email}
              onChange={handleChange}
              placeholder={
                isJa ? "yamada@example.co.jp" : "jane@acmecorp.com"
              }
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm"
            />
          </div>

          {/* Company size */}
          <div>
            <label
              htmlFor="companySize"
              className="block text-sm font-medium text-[#94a3b8] mb-1.5"
            >
              {isJa ? "従業員数" : "Company Size"}{" "}
              <span className="text-red-400">*</span>
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
                {isJa ? "従業員数を選択" : "Select company size"}
              </option>
              {companySizeOptions.map((opt) => (
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
              {isJa ? "お問い合わせ内容" : "Challenges & Questions"}{" "}
              <span className="text-red-400">*</span>
            </label>
            <textarea
              id="message"
              name="message"
              required
              rows={5}
              maxLength={2000}
              value={form.message}
              onChange={handleChange}
              placeholder={
                isJa
                  ? "現在のインフラ構成や障害対策の課題、FaultRayで実現したいことをご記入ください..."
                  : "Describe your infrastructure, current reliability challenges, and what you hope to achieve with FaultRay..."
              }
              className="w-full px-4 py-2.5 rounded-xl bg-[#0d1117] border border-[#1e293b] text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50 transition-colors text-sm resize-none"
            />
          </div>

          {error && (
            <p
              role="alert"
              className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3"
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] disabled:opacity-60 disabled:cursor-not-allowed transition-all shadow-[0_0_20px_rgba(255,215,0,0.2)]"
          >
            <Send size={16} />
            {submitting
              ? isJa
                ? "送信中..."
                : "Sending..."
              : isJa
              ? "送信する"
              : "Send Message"}
          </button>
        </form>
      )}
    </div>
  );
}

export default function ContactPage() {
  return (
    <Suspense fallback={<div className="max-w-[640px] mx-auto px-6 py-20 text-[#64748b]">Loading...</div>}>
      <ContactForm />
    </Suspense>
  );
}
