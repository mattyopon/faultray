"use client";

/**
 * DOC-02: サポートチャネルがメールのみ →
 * Community / Documentation / Email support の複数チャネルを提供。
 * プラン別 SLA（Free: community, Pro: email 24h, Business: Slack 4h）を明示。
 */

import Link from "next/link";
import {
  MessageCircle,
  BookOpen,
  Mail,
  GitBranch,
  MessagesSquare,
  Clock,
  CheckCircle2,
  ExternalLink,
  Zap,
  HelpCircle,
  FileText,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/useLocale";

const T = {
  en: {
    title: "Support Center",
    subtitle: "Multiple ways to get help — choose the channel that suits you best.",
    channels: "Support Channels",
    faq: "Quick Answers",
    planSla: "Response Time by Plan",
    communityTitle: "Community Forum",
    communityDesc: "Ask questions, share ideas, and learn from other FaultRay users on GitHub Discussions.",
    communityBadge: "Free",
    communityLink: "Open GitHub Discussions",
    docsTitle: "Documentation",
    docsDesc: "YAML reference, API spec, tutorials, and integration guides.",
    docsLink: "Browse Docs",
    emailTitle: "Email Support",
    emailDesc: "Send us a detailed question and receive a response from our engineering team.",
    emailBadge: "Pro+",
    emailLink: "Email support@faultray.com",
    slackTitle: "Dedicated Slack Channel",
    slackDesc: "Real-time support with guaranteed 4-hour response. Shared channel with FaultRay engineers.",
    slackBadge: "Business",
    slackLink: "Request Slack Access",
    helpTitle: "In-App Help",
    helpDesc: "Browse the built-in help center with feature guides and walkthroughs.",
    helpLink: "Open Help",
    contactTitle: "Sales & Enterprise",
    contactDesc: "Security reviews, custom MSA, multi-year pricing, and dedicated success manager.",
    contactLink: "Talk to Sales",
    faqs: [
      {
        q: "How do I import my AWS topology?",
        a: "Go to Simulate → click \"Import from Cloud\" → connect your AWS account via read-only IAM role. FaultRay will auto-discover EC2, RDS, ELB, and Lambda services.",
      },
      {
        q: "Can I export reports as PDF?",
        a: "Yes. On the Reports page, click the PDF export button (top right). PDF export is available on Pro and Business plans.",
      },
      {
        q: "How is availability score calculated?",
        a: "FaultRay uses a 5-layer model: Hardware, Software, Theoretical, Operations, and External SLA. Each layer is multiplied to produce the composite N-nine score.",
      },
      {
        q: "Is my topology data stored?",
        a: "YAML topologies are processed in-memory and not persisted by default. Saved simulations are encrypted at rest in your account storage.",
      },
      {
        q: "How do I qualify for DORA compliance reporting?",
        a: "DORA applies to EU-regulated financial entities. Go to the DORA page and follow the entity classification guide. The report is generated automatically once your topology is complete.",
      },
    ],
    slaRows: [
      { plan: "Free", channel: "Community (GitHub)", sla: "Best-effort", badge: "free" },
      { plan: "Pro", channel: "Email", sla: "24 business hours", badge: "pro" },
      { plan: "Business", channel: "Email + Slack", sla: "4 hours", badge: "business" },
      { plan: "Enterprise", channel: "Dedicated CSM + Phone", sla: "1 hour", badge: "enterprise" },
    ] as Array<{ plan: string; channel: string; sla: string; badge: string }>,
    upgradePrompt: "Need faster support?",
    upgradeLink: "Upgrade your plan →",
  },
  ja: {
    title: "サポートセンター",
    subtitle: "複数のサポートチャネルから、最適な方法でお問い合わせください。",
    channels: "サポートチャネル",
    faq: "よくある質問",
    planSla: "プラン別 対応時間",
    communityTitle: "コミュニティフォーラム",
    communityDesc: "GitHub Discussions でFaultRayユーザーと質問・アイデアを共有できます。",
    communityBadge: "無料",
    communityLink: "GitHub Discussions を開く",
    docsTitle: "ドキュメント",
    docsDesc: "YAML リファレンス・API仕様・チュートリアル・連携ガイド。",
    docsLink: "ドキュメントを見る",
    emailTitle: "メールサポート",
    emailDesc: "詳細なご質問をお送りいただくと、エンジニアチームが回答します。",
    emailBadge: "Pro以上",
    emailLink: "support@faultray.com にメール",
    slackTitle: "専用 Slack チャンネル",
    slackDesc: "4時間以内の対応を保証するリアルタイムサポート。FaultRayエンジニアと直接連携。",
    slackBadge: "Business",
    slackLink: "Slack アクセスを申請",
    helpTitle: "アプリ内ヘルプ",
    helpDesc: "機能ガイドやチュートリアルをアプリ内ヘルプセンターで確認できます。",
    helpLink: "ヘルプを開く",
    contactTitle: "法人・エンタープライズ",
    contactDesc: "セキュリティ審査・独自 MSA・マルチイヤー価格・専任サクセスマネージャー。",
    contactLink: "営業に相談する",
    faqs: [
      {
        q: "AWS トポロジーを取り込むには？",
        a: "Simulate → 「クラウドからインポート」→ 読み取り専用 IAM ロールで AWS アカウントを接続。EC2、RDS、ELB、Lambda が自動検出されます。",
      },
      {
        q: "レポートを PDF に出力できますか？",
        a: "はい。レポートページ右上の PDF エクスポートボタンをクリックします。Pro・Business プランでご利用いただけます。",
      },
      {
        q: "可用性スコアはどのように計算されますか？",
        a: "FaultRay は5層モデル（ハードウェア・ソフトウェア・理論値・運用・外部 SLA）を使用します。各層を掛け合わせて N ナイン スコアを算出します。",
      },
      {
        q: "トポロジーデータは保存されますか？",
        a: "YAML トポロジーはデフォルトではメモリ内で処理され、永続化されません。保存済みシミュレーションはアカウントストレージに暗号化して保管されます。",
      },
      {
        q: "DORA コンプライアンスレポートの利用要件は？",
        a: "DORA は EU 規制対象の金融機関に適用されます。DORA ページのエンティティ分類ガイドに従ってください。トポロジーが完成すると自動的にレポートが生成されます。",
      },
    ],
    slaRows: [
      { plan: "Free", channel: "コミュニティ（GitHub）", sla: "ベストエフォート", badge: "free" },
      { plan: "Pro", channel: "メール", sla: "24営業時間以内", badge: "pro" },
      { plan: "Business", channel: "メール + Slack", sla: "4時間以内", badge: "business" },
      { plan: "Enterprise", channel: "専任 CSM + 電話", sla: "1時間以内", badge: "enterprise" },
    ] as Array<{ plan: string; channel: string; sla: string; badge: string }>,
    upgradePrompt: "より迅速なサポートが必要ですか？",
    upgradeLink: "プランをアップグレード →",
  },
} as const;

const BADGE_STYLES: Record<string, string> = {
  free: "bg-[#1e293b] text-[#94a3b8]",
  pro: "bg-blue-500/20 text-blue-300",
  business: "bg-[#FFD700]/20 text-[#FFD700]",
  enterprise: "bg-purple-500/20 text-purple-300",
};

export default function SupportPage() {
  const rawLocale = useLocale();
  const locale = rawLocale in T ? (rawLocale as keyof typeof T) : "en";
  const t = T[locale];

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-3xl font-bold mb-2 flex items-center gap-3">
          <HelpCircle size={28} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8]">{t.subtitle}</p>
      </div>

      {/* Support channel cards */}
      <h2 className="text-sm font-semibold text-[#64748b] uppercase tracking-wide mb-4">
        {t.channels}
      </h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
        {/* Community */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <GitBranch size={20} className="text-[#94a3b8]" />
            <Badge variant="default" className="text-xs">{t.communityBadge}</Badge>
          </div>
          <h3 className="font-semibold mb-2">{t.communityTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.communityDesc}</p>
          <a
            href="https://github.com/mattyopon/faultray/discussions"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.communityLink} <ExternalLink size={12} />
          </a>
        </Card>

        {/* Docs */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <BookOpen size={20} className="text-blue-400" />
          </div>
          <h3 className="font-semibold mb-2">{t.docsTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.docsDesc}</p>
          <a
            href="https://github.com/mattyopon/faultray/blob/main/docs/"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.docsLink} <ExternalLink size={12} />
          </a>
        </Card>

        {/* In-app help */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <MessageCircle size={20} className="text-emerald-400" />
          </div>
          <h3 className="font-semibold mb-2">{t.helpTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.helpDesc}</p>
          <Link
            href="/help"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.helpLink} <ExternalLink size={12} />
          </Link>
        </Card>

        {/* Email */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <Mail size={20} className="text-purple-400" />
            <Badge variant="default" className="text-xs">{t.emailBadge}</Badge>
          </div>
          <h3 className="font-semibold mb-2">{t.emailTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.emailDesc}</p>
          <a
            href="mailto:support@faultray.com"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.emailLink} <ExternalLink size={12} />
          </a>
        </Card>

        {/* Slack */}
        <Card className="flex flex-col border-[#FFD700]/20">
          <div className="flex items-center justify-between mb-3">
            <MessagesSquare size={20} className="text-[#FFD700]" />
            <Badge variant="gold" className="text-xs">{t.slackBadge}</Badge>
          </div>
          <h3 className="font-semibold mb-2">{t.slackTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.slackDesc}</p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.slackLink} <ExternalLink size={12} />
          </Link>
        </Card>

        {/* Enterprise */}
        <Card className="flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <FileText size={20} className="text-red-400" />
          </div>
          <h3 className="font-semibold mb-2">{t.contactTitle}</h3>
          <p className="text-sm text-[#94a3b8] mb-4 flex-1">{t.contactDesc}</p>
          <Link
            href="/contact"
            className="inline-flex items-center gap-1.5 text-sm text-[#FFD700] hover:underline"
          >
            {t.contactLink} <ExternalLink size={12} />
          </Link>
        </Card>
      </div>

      {/* SLA table by plan */}
      <Card className="mb-12">
        <div className="flex items-center gap-2 mb-4">
          <Clock size={18} className="text-[#FFD700]" />
          <h2 className="font-bold">{t.planSla}</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b]">
                <th className="text-left py-2 pr-4 text-[#64748b] font-medium">Plan</th>
                <th className="text-left py-2 pr-4 text-[#64748b] font-medium">Channel</th>
                <th className="text-left py-2 text-[#64748b] font-medium">
                  <Clock size={12} className="inline mr-1" />
                  Response SLA
                </th>
              </tr>
            </thead>
            <tbody>
              {t.slaRows.map((row) => (
                <tr key={row.plan} className="border-b border-[#1e293b] last:border-0">
                  <td className="py-3 pr-4">
                    <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${BADGE_STYLES[row.badge] ?? ""}`}>
                      {row.plan}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-[#94a3b8]">{row.channel}</td>
                  <td className="py-3">
                    <span className="flex items-center gap-1.5">
                      <CheckCircle2 size={13} className="text-emerald-400 shrink-0" />
                      {row.sla}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[#64748b] mt-4">
          {t.upgradePrompt}{" "}
          <Link href="/pricing" className="text-[#FFD700] hover:underline">
            {t.upgradeLink}
          </Link>
        </p>
      </Card>

      {/* FAQ */}
      <Card>
        <div className="flex items-center gap-2 mb-5">
          <Zap size={18} className="text-[#FFD700]" />
          <h2 className="font-bold">{t.faq}</h2>
        </div>
        <div className="space-y-4">
          {t.faqs.map((item) => (
            <div key={item.q} className="border-b border-[#1e293b] pb-4 last:border-0 last:pb-0">
              <p className="text-sm font-semibold text-[#e2e8f0] mb-1.5">{item.q}</p>
              <p className="text-sm text-[#94a3b8] leading-relaxed">{item.a}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
