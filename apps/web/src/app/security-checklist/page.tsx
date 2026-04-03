import Link from "next/link";
import type { Metadata } from "next";
import { ShieldCheck, Download, CheckCircle2, Lock, FileText } from "lucide-react";

// MATERIAL-04: 日本企業向けセキュリティチェックシート
export const metadata: Metadata = {
  title: "Security Checklist — FaultRay Enterprise",
  description: "FaultRay security questionnaire for enterprise IT departments. ISMS, SOC 2, and ISO 27001 aligned.",
  alternates: { canonical: "https://faultray.com/security-checklist" },
};

const CHECKLIST = [
  {
    category: { en: "Data Management", ja: "データ管理" },
    items: [
      {
        en: "Is customer data encrypted at rest (AES-256)?",
        ja: "顧客データは保存時に暗号化（AES-256）されていますか？",
        answer: { en: "Yes — all user data is encrypted at rest using AES-256-GCM.", ja: "はい。すべての顧客データはAES-256-GCMで暗号化されています。" },
      },
      {
        en: "Is data encrypted in transit?",
        ja: "データは転送時に暗号化されていますか？",
        answer: { en: "Yes — TLS 1.3 enforced for all connections.", ja: "はい。すべての通信でTLS 1.3を強制しています。" },
      },
      {
        en: "What is the data retention policy?",
        ja: "データ保存期間のポリシーはありますか？",
        answer: { en: "Simulation data: 2 years. Audit logs: 7 years. Account data: deleted within 30 days of account closure.", ja: "シミュレーションデータ: 2年。監査ログ: 7年。アカウントデータ: 退会後30日以内に削除。" },
      },
      {
        en: "Where is data stored (data residency)?",
        ja: "データはどこに保管されますか（データレジデンシー）？",
        answer: { en: "Primary: Supabase (AWS Tokyo ap-northeast-1). Backups: AWS US-East-1. Enterprise customers may request Japan-only residency.", ja: "プライマリ: Supabase（AWSアジアパシフィック東京 ap-northeast-1）。バックアップ: AWS US-East-1。エンタープライズのお客様はJapanのみのレジデンシーをご要望いただけます。" },
      },
    ],
  },
  {
    category: { en: "Access Control", ja: "アクセス制御" },
    items: [
      {
        en: "Is multi-factor authentication (MFA) supported?",
        ja: "多要素認証（MFA）に対応していますか？",
        answer: { en: "Yes — MFA is supported via TOTP apps. Enterprise plans support SAML SSO with your IdP's MFA.", ja: "はい。TOTPアプリでのMFAに対応しています。エンタープライズプランでは、IdPのMFAを使ったSAML SSOも利用できます。" },
      },
      {
        en: "Is role-based access control (RBAC) available?",
        ja: "ロールベースアクセス制御（RBAC）は利用できますか？",
        answer: { en: "Yes — Owner, Admin, Member, and Viewer roles. Project-level permissions available on Business plan.", ja: "はい。Owner、Admin、Member、Viewerの4ロールがあります。BusinessプランではプロジェクトレベルのRBACも利用できます。" },
      },
      {
        en: "Are privileged accounts audited?",
        ja: "特権アカウントの操作は監査されますか？",
        answer: { en: "Yes — all administrative actions are logged in the audit log with timestamp, IP, and user ID.", ja: "はい。すべての管理操作が監査ログに記録されます（タイムスタンプ、IP、ユーザーID含む）。" },
      },
    ],
  },
  {
    category: { en: "Business Continuity", ja: "事業継続性" },
    items: [
      {
        en: "What is the target uptime SLA?",
        ja: "稼働率SLAはどのくらいですか？",
        answer: { en: "99.9% monthly uptime for Pro and Business plans. See our SLA page for credit terms.", ja: "ProおよびBusinessプランの月間稼働率は99.9%保証です。クレジット条件はSLAページをご確認ください。" },
      },
      {
        en: "What is the RTO/RPO in case of disaster?",
        ja: "災害時のRTO/RPOは？",
        answer: { en: "RTO: 4 hours. RPO: 1 hour. Daily automated backups with point-in-time recovery.", ja: "RTO: 4時間。RPO: 1時間。毎日の自動バックアップとポイントインタイムリカバリに対応。" },
      },
      {
        en: "Is there a status page?",
        ja: "ステータスページはありますか？",
        answer: { en: "Yes — real-time status at faultray.com/status", ja: "はい。faultray.com/statusでリアルタイムの稼働状況を公開しています。" },
      },
    ],
  },
  {
    category: { en: "Compliance & Certifications", ja: "コンプライアンスと認証" },
    items: [
      {
        en: "Is FaultRay GDPR compliant?",
        ja: "GDPRに準拠していますか？",
        answer: { en: "Yes — GDPR-compliant data processing, DPA available upon request, right to erasure implemented.", ja: "はい。GDPR準拠のデータ処理、DPAの締結対応、消去権の実装済みです。" },
      },
      {
        en: "Is a Data Processing Agreement (DPA) available?",
        ja: "データ処理契約（DPA）の締結は可能ですか？",
        answer: { en: "Yes — available at faultray.com/dpa", ja: "はい。faultray.com/dpaで確認できます。" },
      },
      {
        en: "Does FaultRay have SOC 2 certification?",
        ja: "SOC 2認証を取得していますか？",
        answer: { en: "SOC 2 audit in progress. Expected completion: Q4 2026. ISO 27001 planned for 2027.", ja: "SOC 2監査を進めています。完了予定: 2026年Q4。ISO 27001は2027年予定。" },
      },
    ],
  },
  {
    category: { en: "Vulnerability Management", ja: "脆弱性管理" },
    items: [
      {
        en: "How are security vulnerabilities disclosed?",
        ja: "セキュリティ脆弱性はどのように開示されますか？",
        answer: { en: "Responsible disclosure via security@faultray.com. We respond within 48 hours.", ja: "security@faultray.comへの責任ある開示をお願いしています。48時間以内に対応します。" },
      },
      {
        en: "How frequently are dependencies updated?",
        ja: "依存関係の更新頻度は？",
        answer: { en: "Automated dependency updates weekly via Dependabot. Critical CVEs patched within 24 hours.", ja: "Dependabotによる週次自動更新。重大なCVEは24時間以内にパッチ対応。" },
      },
    ],
  },
];

export default function SecurityChecklistPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <div className="mb-10">
        <Link href="/" className="text-sm text-[#64748b] hover:text-white transition-colors">
          ← Back to Home
        </Link>
      </div>

      <div className="flex items-center gap-3 mb-2">
        <ShieldCheck size={28} className="text-[#FFD700]" />
        <h1 className="text-3xl font-bold tracking-tight">Security Questionnaire</h1>
      </div>
      <p className="text-sm text-[#64748b] mb-2">セキュリティチェックシート</p>
      <p className="text-sm text-[#94a3b8] mb-10 max-w-xl">
        Standard answers for enterprise IT departments, procurement teams, and compliance officers.
        For ISMS / SOC 2 / ISO 27001 review processes.
      </p>

      <div className="flex gap-3 mb-10">
        <a
          href="/contact?subject=security-review"
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#FFD700] text-[#0a0e1a] text-sm font-semibold hover:bg-yellow-400 transition-colors"
        >
          <FileText size={14} />
          Request Full Security Package
        </a>
        <a
          href="mailto:security@faultray.com"
          className="flex items-center gap-2 px-4 py-2 rounded-lg border border-[#1e293b] text-sm text-[#94a3b8] hover:text-white hover:border-[#64748b] transition-colors"
        >
          <Lock size={14} />
          security@faultray.com
        </a>
      </div>

      <div className="space-y-8">
        {CHECKLIST.map((section) => (
          <section key={section.category.en}>
            <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
              <CheckCircle2 size={18} className="text-[#FFD700]" />
              {section.category.en}
              <span className="text-sm font-normal text-[#64748b] ml-1">/ {section.category.ja}</span>
            </h2>
            <div className="space-y-4">
              {section.items.map((item, i) => (
                <div key={i} className="p-5 rounded-xl border border-[#1e293b] bg-[#111827]">
                  <p className="text-sm font-semibold text-[#e2e8f0] mb-1">Q: {item.en}</p>
                  <p className="text-xs text-[#64748b] mb-3">Q（日本語）: {item.ja}</p>
                  <div className="border-t border-[#1e293b] pt-3">
                    <p className="text-sm text-[#94a3b8]"><span className="text-emerald-400 font-semibold">A:</span> {item.answer.en}</p>
                    <p className="text-sm text-[#64748b] mt-1">A（日本語）: {item.answer.ja}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="mt-12 p-6 rounded-xl border border-[#1e293b] bg-[#0d1117]">
        <div className="flex items-center gap-2 mb-3">
          <Download size={16} className="text-[#FFD700]" />
          <h3 className="text-sm font-bold text-white">Need a signed copy for your vendor assessment?</h3>
        </div>
        <p className="text-sm text-[#94a3b8] mb-4">
          We can provide a signed PDF version of this questionnaire, NDA, and our DPA for formal procurement processes.
        </p>
        <a
          href="/contact?subject=vendor-assessment"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-[#FFD700] text-[#0a0e1a] text-sm font-semibold hover:bg-yellow-400 transition-colors"
        >
          Request Signed Documents
        </a>
      </div>

      <div className="mt-12 pt-8 border-t border-[#1e293b] flex flex-wrap gap-6 text-sm text-[#64748b]">
        <Link href="/terms" className="hover:text-white transition-colors">Terms of Service</Link>
        <Link href="/privacy" className="hover:text-white transition-colors">Privacy Policy</Link>
        <Link href="/dpa" className="hover:text-white transition-colors">DPA</Link>
        <Link href="/service-level-agreement" className="hover:text-white transition-colors">SLA</Link>
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
      </div>
    </div>
  );
}
