"use client";

import Link from "next/link";
import { Logo } from "@/components/logo";
import { useLocale } from "@/lib/useLocale";
import {
  Activity,
  Boxes,
  Layers,
  Brain,
  FileCheck,
  Lock,
  LineChart,
  Cpu,
  Wrench,
  LayoutDashboard,
  Bot,
  Shield,
  AlertTriangle,
  Check,
  Zap,
  ExternalLink,
} from "lucide-react";

// Icons are locale-independent; text content lives in CONTENT below and is
// zipped with these by index at render time.
const CORE_ICONS = [
  Activity, Boxes, Layers, Brain, FileCheck,
  Lock, LineChart, Cpu, Wrench, LayoutDashboard,
];
const AGENT_ICONS = [Bot, Shield, Boxes, AlertTriangle];

interface FeatureCard {
  title: string;
  desc: string;
  details: string[];
}
interface AgentFeature {
  title: string;
  desc: string;
}
interface FeaturesContent {
  nav: { pricing: string; getStarted: string };
  hero: { badge: string; title: string; subtitle: string; getStarted: string; backHome: string };
  core: { heading: string; subheading: string };
  featureCards: FeatureCard[];
  agent: { badge: string; heading: string; subtitle: string };
  agentFeatures: AgentFeature[];
  cta: { heading: string; subtitle: string; getStarted: string; bookDemo: string };
  footer: { support: string; home: string; contact: string };
}

// i18n acceptance fix: this page used to be hardcoded Japanese, so English (and
// every other non-JA) locale saw a wall of Japanese. Content is now keyed by
// locale; non-JA locales fall back to English so they never see raw Japanese.
const CONTENT: Record<"en" | "ja", FeaturesContent> = {
  ja: {
    nav: { pricing: "料金", getStarted: "無料で始める" },
    hero: {
      badge: "機能一覧",
      title: "FaultRayの全機能",
      subtitle:
        "本番環境を壊さず、2,000件以上のシナリオでシステムの弱点を自動診断するための機能をすべて網羅しています。",
      getStarted: "無料で始める",
      backHome: "トップページに戻る",
    },
    core: { heading: "コア機能", subheading: "リスクゼロ診断を支える10のコア機能" },
    featureCards: [
      {
        title: "100種以上のシミュレーションエンジン",
        desc: "ネットワーク遅延・プロセス障害・リソース枯渇・依存関係の連鎖停止・レイテンシ・影響範囲・SLA契約検証など。モンテカルロ法・マルコフ連鎖・待ち行列理論を活用しています。",
        details: [
          "ネットワーク遅延・パケットロスシミュレーション",
          "プロセス障害・クラッシュシミュレーション",
          "リソース枯渇（CPU・メモリ・ディスク）",
          "依存関係の連鎖停止シミュレーション",
          "SLA契約の検証と違反予測",
        ],
      },
      {
        title: "2,000件以上の自動生成シナリオ",
        desc: "単一ノードの障害から複数リージョンにまたがる連鎖障害まで。システム構成のYAMLファイルから自動生成。10コンポーネント構成で2,000件以上のユニークシナリオを生成します。",
        details: [
          "YAML構成ファイルから自動生成",
          "単一障害点から複合障害まで網羅",
          "マルチリージョン連鎖障害シナリオ",
          "カスタムシナリオの手動追加も可能",
          "シナリオの重要度・影響度でフィルタリング",
        ],
      },
      {
        title: "5層稼働率モデル（N-Layer Model）",
        desc: "N-Layer Model（エヌレイヤーモデル）は、稼働率の上限を5つの独立した制約層に分解して可視化する分析フレームワークです。どの層がボトルネックになっているかを特定し、投資すべき場所を明示します。",
        details: [
          "層1: ハードウェア（ディスク・ネットワーク・電源）",
          "層2: ソフトウェア（デプロイ・設定ミス・人的ミス）",
          "層3: 理論値（GC停止・OSスケジューリング）",
          "層4: 運用（障害対応時間・オンコール体制）",
          "層5: 外部SLA（AWS・GCP・Stripe等）",
        ],
      },
      {
        title: "AI分析（Claude powered）",
        desc: "Anthropic社の大規模言語モデル「Claude」を活用し、シミュレーション結果から根本原因を自動特定。影響度・修正コスト順に並んだ改善提案をエンジニアにも経営者にも分かる言葉で生成します。",
        details: [
          "根本原因の自動特定と説明",
          "影響度・修正コスト順の改善提案",
          "シミュレーション結果の要約レポート",
          "技術的でない経営者向けサマリー",
          "改善前後の稼働率変化の予測",
        ],
      },
      {
        title: "DORA リサーチドラフト（研究プロトタイプ）",
        desc: "Digital Operational Resilience Act（EU金融規制）への研究プロトタイプマッピング。証跡とリスク評価を含むエビデンスドラフトを生成しますが、監査認証ではなく、独立した法務・技術レビューなしには規制対応の証明に使用できません。",
        details: [
          "DORA RTS（規制技術基準）への研究プロトタイプマッピング",
          "研究用エビデンストレイルの生成",
          "リスク評価マトリクスのドラフト作成",
          "PDF・API形式でのエクスポート",
          "SOC 2向け研究ドラフトも生成可能",
        ],
      },
      {
        title: "セキュリティ脆弱性フィード連携",
        desc: "CVEデータベースとNVDフィードを自動取り込み。既知の脆弱性がシステムの連鎖障害にどう影響するかをシミュレーションします。",
        details: [
          "CVE・NVDフィードの自動取り込み",
          "脆弱性を起点とした連鎖障害シミュレーション",
          "修正優先度の自動ランキング",
          "脆弱性スコア（CVSS）との統合分析",
          "修正コストと影響度のトレードオフ分析",
        ],
      },
      {
        title: "リアルタイム監視（APM統合）",
        desc: "本番環境のライブパフォーマンス指標・トレース相関・異常検知をシミュレーション結果と統合。35種以上の監視ビューを備えたダッシュボードを提供します。",
        details: [
          "Prometheus・Grafana・Datadog連携",
          "分散トレーシングの相関分析",
          "異常検知とアラート自動生成",
          "パフォーマンス劣化の早期発見",
          "SLOブリーチの予測と通知",
        ],
      },
      {
        title: "AIガバナンス（経産省・ISO 42001）",
        desc: "経済産業省のAIガイドラインとISO 42001 要件への研究プロトタイプマッピング。AIガバナンスの検討材料としてエビデンスドラフトを生成しますが、監査認証ではなく独立した法務レビューが必要です。",
        details: [
          "経産省AIガイドライン全項目チェック",
          "ISO 42001 要件への自動適合確認",
          "AIモデルのリスク評価レポート",
          "研究用エビデンストレイルの生成",
          "AIガバナンス改善提案の出力",
        ],
      },
      {
        title: "自動復旧スクリプト生成",
        desc: "シミュレーション結果から手順書・復旧スクリプト・Terraformパッチを自動生成。障害時の対応時間を数時間から数分に短縮します。",
        details: [
          "障害別ランブック（手順書）の自動生成",
          "Bash・Python復旧スクリプトの生成",
          "Terraformパッチの自動提案",
          "PagerDuty・Slack連携での自動配布",
          "ゲームデイ（障害訓練）シナリオの自動生成",
        ],
      },
      {
        title: "35画面以上のフルダッシュボード",
        desc: "構成エディタ・シナリオ一覧・5層ドリルダウン・ヒートマップ・DORAリサーチドラフト・経営サマリーを一つのWebダッシュボードで提供します。",
        details: [
          "インタラクティブなトポロジエディタ",
          "シナリオエクスプローラーと詳細分析",
          "N-Layer ドリルダウンビュー",
          "障害ヒートマップとタイムライン",
          "経営者向けサマリーと月次レポート",
        ],
      },
    ],
    agent: {
      badge: "v11.0 新機能",
      heading: "AIエージェント障害シミュレーション",
      subtitle:
        "インフラ障害がAIエージェントの誤回答にどう連鎖するかを、本番環境で発生する前にシミュレーションします。",
    },
    agentFeatures: [
      {
        title: "連鎖障害の横断分析",
        desc: "インフラ障害（データベースダウン、キャッシュ障害）がAIエージェントの誤回答にどう連鎖するかを追跡。正常に見えて誤った結果を出す「サイレント劣化」を事前に検出。",
      },
      {
        title: "予測・評価・管理の3ステップ",
        desc: "AIエージェント耐久性の3つの柱: 障害シナリオのシミュレーション、影響範囲分析によるリリースリスク評価、監視ルールの自動生成。",
      },
      {
        title: "4種類の新コンポーネントタイプ",
        desc: "AIエージェント・LLMエンドポイント・ツールサービス・エージェントオーケストレーターを従来のインフラと同じ依存関係グラフに組み込んで分析。",
      },
      {
        title: "10種類のAIエージェント障害モード",
        desc: "誤回答・コンテキスト超過・レート制限・トークン枯渇・ツール障害・無限ループ・プロンプトインジェクション・確信度ズレ・推論崩壊・エラー増幅の10パターンを網羅。",
      },
    ],
    cta: {
      heading: "今すぐ試す",
      subtitle: "無料プランでFaultRayの主要機能をすべて体験できます。クレジットカード不要。",
      getStarted: "無料で始める",
      bookDemo: "デモを予約する",
    },
    footer: { support: "🌐 日本語・英語でのサポートに対応しています", home: "トップページ", contact: "お問い合わせ" },
  },
  en: {
    nav: { pricing: "Pricing", getStarted: "Get Started Free" },
    hero: {
      badge: "All Features",
      title: "Everything FaultRay Does",
      subtitle:
        "A complete toolkit for automatically pinpointing your system's weak points across 2,000+ scenarios — without ever touching production.",
      getStarted: "Get Started Free",
      backHome: "Back to Home",
    },
    core: { heading: "Core Features", subheading: "The 10 core capabilities behind zero-risk diagnosis" },
    featureCards: [
      {
        title: "100+ Simulation Engines",
        desc: "Network latency, process failures, resource exhaustion, cascading dependency outages, latency, blast radius, SLA validation, and more — powered by Monte Carlo methods, Markov chains, and queueing theory.",
        details: [
          "Network latency & packet-loss simulation",
          "Process failure & crash simulation",
          "Resource exhaustion (CPU / memory / disk)",
          "Cascading dependency-failure simulation",
          "SLA validation & breach prediction",
        ],
      },
      {
        title: "2,000+ Auto-Generated Scenarios",
        desc: "From a single-node failure to cascading multi-region outages. Auto-generated from your system's YAML topology — a 10-component setup produces 2,000+ unique scenarios.",
        details: [
          "Auto-generated from a YAML config file",
          "Single points of failure through compound failures",
          "Multi-region cascading-failure scenarios",
          "Add custom scenarios manually",
          "Filter scenarios by severity & impact",
        ],
      },
      {
        title: "5-Layer Availability Model (N-Layer Model)",
        desc: "The N-Layer Model is an analytical framework that decomposes your availability ceiling into 5 independent constraint layers. It pinpoints which layer is the bottleneck and shows exactly where to invest.",
        details: [
          "Layer 1: Hardware (disk / network / power)",
          "Layer 2: Software (deploys / misconfig / human error)",
          "Layer 3: Theoretical (GC pauses / OS scheduling)",
          "Layer 4: Operations (incident response / on-call)",
          "Layer 5: External SLA (AWS / GCP / Stripe, etc.)",
        ],
      },
      {
        title: "AI Analysis (Claude-powered)",
        desc: "Uses Anthropic's large language model, Claude, to automatically identify root causes from simulation results and generate improvement proposals — ranked by impact and remediation cost — in language both engineers and executives understand.",
        details: [
          "Automatic root-cause identification & explanation",
          "Improvement proposals ranked by impact & cost",
          "Summary reports of simulation results",
          "Non-technical executive summaries",
          "Predicted availability change before vs. after fixes",
        ],
      },
      {
        title: "DORA Research Draft (Research Prototype)",
        desc: "A research-prototype mapping to the Digital Operational Resilience Act (EU financial regulation). Generates evidence drafts with audit trails and risk assessments — but it is not an audit certification and cannot prove regulatory compliance without independent legal and technical review.",
        details: [
          "Research-prototype mapping to DORA RTS",
          "Research evidence-trail generation",
          "Risk-assessment matrix drafts",
          "Export to PDF / API",
          "SOC 2 research drafts also available",
        ],
      },
      {
        title: "Security Vulnerability Feed Integration",
        desc: "Automatically ingests the CVE database and NVD feeds, then simulates how known vulnerabilities propagate into cascading system failures.",
        details: [
          "Automatic CVE / NVD feed ingestion",
          "Vulnerability-triggered cascading-failure simulation",
          "Automatic remediation-priority ranking",
          "Integrated analysis with CVSS scores",
          "Remediation cost vs. impact trade-off analysis",
        ],
      },
      {
        title: "Real-Time Monitoring (APM Integration)",
        desc: "Integrates live production performance metrics, trace correlation, and anomaly detection with your simulation results. Ships with a dashboard of 35+ monitoring views.",
        details: [
          "Prometheus / Grafana / Datadog integration",
          "Distributed-tracing correlation analysis",
          "Anomaly detection & automatic alerting",
          "Early detection of performance degradation",
          "SLO-breach prediction & notification",
        ],
      },
      {
        title: "AI Governance (METI / ISO 42001)",
        desc: "A research-prototype mapping to Japan METI's AI guidelines and ISO 42001 requirements. Generates evidence drafts as input for AI-governance review — but it is not an audit certification and requires independent legal review.",
        details: [
          "Full checklist against METI AI guidelines",
          "Automatic conformance checks against ISO 42001",
          "AI-model risk-assessment reports",
          "Research evidence-trail generation",
          "AI-governance improvement proposals",
        ],
      },
      {
        title: "Automatic Recovery Script Generation",
        desc: "Auto-generates runbooks, recovery scripts, and Terraform patches from simulation results — cutting incident response time from hours to minutes.",
        details: [
          "Auto-generated per-failure runbooks",
          "Bash / Python recovery-script generation",
          "Automatic Terraform-patch suggestions",
          "Auto-distribution via PagerDuty / Slack",
          "Auto-generated game-day (failure-drill) scenarios",
        ],
      },
      {
        title: "35+ Screen Full Dashboard",
        desc: "A topology editor, scenario explorer, 5-layer drill-down, heatmaps, DORA research drafts, and executive summaries — all in one web dashboard.",
        details: [
          "Interactive topology editor",
          "Scenario explorer with detailed analysis",
          "N-Layer drill-down views",
          "Failure heatmaps & timelines",
          "Executive summaries & monthly reports",
        ],
      },
    ],
    agent: {
      badge: "v11.0 New",
      heading: "AI Agent Failure Simulation",
      subtitle:
        "Simulate how infrastructure failures cascade into AI-agent misfires — before they ever happen in production.",
    },
    agentFeatures: [
      {
        title: "Cross-Cutting Cascade Analysis",
        desc: "Tracks how infrastructure failures (database down, cache outage) cascade into wrong answers from AI agents. Detect 'silent degradation' — output that looks fine but is wrong — before it ships.",
      },
      {
        title: "Predict, Assess, Manage — 3 Steps",
        desc: "The three pillars of AI-agent resilience: simulate failure scenarios, assess release risk via blast-radius analysis, and auto-generate monitoring rules.",
      },
      {
        title: "4 New Component Types",
        desc: "Bring AI agents, LLM endpoints, tool services, and agent orchestrators into the same dependency graph you already use for conventional infrastructure.",
      },
      {
        title: "10 AI-Agent Failure Modes",
        desc: "Covers wrong answers, context overflow, rate limiting, token exhaustion, tool failures, infinite loops, prompt injection, confidence drift, reasoning collapse, and error amplification.",
      },
    ],
    cta: {
      heading: "Try It Now",
      subtitle: "Experience all of FaultRay's core features on the free plan. No credit card required.",
      getStarted: "Get Started Free",
      bookDemo: "Book a Demo",
    },
    footer: { support: "🌐 Support available in English and Japanese", home: "Home", contact: "Contact" },
  },
};

export default function FeaturesPage() {
  const locale = useLocale();
  const t = CONTENT[locale === "ja" ? "ja" : "en"];
  const homeHref = `/${locale === "ja" ? "ja" : "en"}`;

  return (
    <div className="min-h-screen text-white">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-[var(--border-color)]/95 backdrop-blur-sm">
        <div className="w-full px-6 h-16 flex items-center justify-between">
          <Link href={homeHref} className="flex items-center gap-2 font-bold">
            <Logo size={24} />
            FaultRay
          </Link>
          <div className="flex items-center gap-4">
            <Link href={`${homeHref}#pricing`} className="text-sm text-[var(--text-secondary)] hover:text-white transition-colors">
              {t.nav.pricing}
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl text-sm hover:bg-[#ffe44d] transition-all"
            >
              <Zap size={14} />
              {t.nav.getStarted}
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="py-20 text-center">
        <div className="w-full px-6">
          <div className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[var(--gold)] border border-[var(--gold)]/25 rounded-full bg-[var(--gold)]/5 mb-6">
            {t.hero.badge}
          </div>
          <h1 className="text-[clamp(2rem,5vw,3.5rem)] font-extrabold tracking-tight mb-4">
            {t.hero.title}
          </h1>
          <p className="text-lg text-[var(--text-secondary)] leading-relaxed mb-8">
            {t.hero.subtitle}
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] transition-all"
            >
              <Zap size={16} />
              {t.hero.getStarted}
            </Link>
            <Link
              href={homeHref}
              className="inline-flex items-center gap-2 px-6 py-3 border border-[var(--border-color)] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] transition-all"
            >
              {t.hero.backHome}
            </Link>
          </div>
        </div>
      </section>

      {/* Core Features */}
      <section className="py-16">
        <div className="w-full px-6">
          <h2 className="text-2xl font-bold mb-2 text-center">{t.core.heading}</h2>
          <p className="text-[var(--text-secondary)] text-center mb-12">{t.core.subheading}</p>
          <div className="grid md:grid-cols-2 gap-8">
            {t.featureCards.map((f, i) => {
              const Icon = CORE_ICONS[i] ?? Activity;
              return (
                <div
                  key={f.title}
                  className="p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--gold)]/30 hover:bg-[var(--bg-card-hover)] transition-all duration-200"
                >
                  <div className="w-12 h-12 flex items-center justify-center rounded-xl bg-[var(--gold)]/[0.06] border border-[var(--gold)]/10 mb-5">
                    <Icon size={22} className="text-[var(--gold)]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[var(--text-secondary)] leading-relaxed mb-5">{f.desc}</p>
                  <ul className="space-y-2">
                    {f.details.map((detail) => (
                      <li key={detail} className="flex items-start gap-2.5 text-sm text-[var(--text-muted)]">
                        <Check size={14} className="text-emerald-400 mt-0.5 shrink-0" />
                        {detail}
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* AI Agent Section */}
      <section className="py-16 border-t border-[var(--gold)]/15">
        <div className="w-full px-6">
          <div className="text-center mb-12">
            <span className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[var(--gold)] border border-[var(--gold)]/25 rounded-full bg-[var(--gold)]/5 mb-4">
              {t.agent.badge}
            </span>
            <h2 className="text-2xl font-bold mb-2">{t.agent.heading}</h2>
            <p className="text-[var(--text-secondary)] max-w-[600px] mx-auto">
              {t.agent.subtitle}
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            {t.agentFeatures.map((f, i) => {
              const Icon = AGENT_ICONS[i] ?? Bot;
              return (
                <div
                  key={f.title}
                  className="p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] hover:border-[var(--gold)]/30 transition-all duration-200"
                >
                  <div className="w-12 h-12 flex items-center justify-center rounded-xl bg-[var(--gold)]/[0.06] border border-[var(--gold)]/10 mb-5">
                    <Icon size={22} className="text-[var(--gold)]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[var(--text-secondary)] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 text-center">
        <div className="max-w-[600px] mx-auto px-6">
          <h2 className="text-2xl font-bold mb-4">{t.cta.heading}</h2>
          <p className="text-[var(--text-secondary)] mb-8 leading-relaxed">
            {t.cta.subtitle}
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-7 py-3 bg-[var(--gold)] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] transition-all"
            >
              <Zap size={16} />
              {t.cta.getStarted}
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-7 py-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-semibold rounded-xl hover:bg-emerald-500/20 transition-all"
            >
              <ExternalLink size={16} />
              {t.cta.bookDemo}
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t border-[var(--border-color)] text-center">
        <p className="text-sm text-[var(--text-muted)]">
          <span className="mr-2">{t.footer.support}</span>
          ·{" "}
          <Link href={homeHref} className="hover:text-white transition-colors">
            {t.footer.home}
          </Link>
          {" · "}
          <Link href="/contact" className="hover:text-white transition-colors">
            {t.footer.contact}
          </Link>
        </p>
      </footer>
    </div>
  );
}
