import Link from "next/link";
import { Logo } from "@/components/logo";
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

const featureCards = [
  {
    Icon: Activity,
    title: "100種以上のシミュレーションエンジン",
    desc: "ネットワーク遅延・プロセス障害・リソース枯渇・依存関係の連鎖停止・レイテンシ・影響範囲・SLA契約検証など。モンテカルロ法・マルコフ連鎖・待ち行列理論で駆動します。",
    details: [
      "ネットワーク遅延・パケットロスシミュレーション",
      "プロセス障害・クラッシュシミュレーション",
      "リソース枯渇（CPU・メモリ・ディスク）",
      "依存関係の連鎖停止シミュレーション",
      "SLA契約の検証と違反予測",
    ],
  },
  {
    Icon: Boxes,
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
    Icon: Layers,
    title: "5層稼働率モデル（N-Layer Model）",
    desc: "稼働率の上限を5つの独立した制約層に分解する唯一のツール。どの層がボトルネックになっているかを特定し、投資すべき場所を明示します。",
    details: [
      "層1: ハードウェア（ディスク・ネットワーク・電源）",
      "層2: ソフトウェア（デプロイ・設定ミス・人的ミス）",
      "層3: 理論値（GC停止・OSスケジューリング）",
      "層4: 運用（障害対応時間・オンコール体制）",
      "層5: 外部SLA（AWS・GCP・Stripe等）",
    ],
  },
  {
    Icon: Brain,
    title: "AI分析（Claude powered）",
    desc: "Claudeによる根本原因分析と、影響度・コスト順に並んだ改善提案を自動生成。エンジニアが気づきにくいボトルネックを自然言語で説明します。",
    details: [
      "根本原因の自動特定と説明",
      "影響度・修正コスト順の改善提案",
      "シミュレーション結果の要約レポート",
      "技術的でない経営者向けサマリー",
      "改善前後の稼働率変化の予測",
    ],
  },
  {
    Icon: FileCheck,
    title: "DORAコンプライアンスレポート",
    desc: "Digital Operational Resilience Act（EU金融規制）への対応を証跡付きで自動証明。監査官が求める形式のレポートをワンクリックで生成します。",
    details: [
      "DORA 52項目への自動適合チェック",
      "監査証跡（エビデンストレイル）の自動生成",
      "リスク評価マトリクスの自動作成",
      "PDF・API形式でのエクスポート",
      "SOC 2対応レポートも生成可能",
    ],
  },
  {
    Icon: Lock,
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
    Icon: LineChart,
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
    Icon: Cpu,
    title: "AIガバナンス（経産省・ISO 42001）",
    desc: "経済産業省のAIガイドラインとISO 42001 要件への自動適合チェック。責任あるAI運用を監査エビデンスで証明します。",
    details: [
      "経産省AIガイドライン全項目チェック",
      "ISO 42001 要件への自動適合確認",
      "AIモデルのリスク評価レポート",
      "監査対応エビデンスの自動生成",
      "AIガバナンス改善提案の出力",
    ],
  },
  {
    Icon: Wrench,
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
    Icon: LayoutDashboard,
    title: "35画面以上のフルダッシュボード",
    desc: "構成エディタ・シナリオ一覧・5層ドリルダウン・ヒートマップ・DORAレポート・経営サマリーを一つのWebダッシュボードで提供します。",
    details: [
      "インタラクティブなトポロジエディタ",
      "シナリオエクスプローラーと詳細分析",
      "N-Layer ドリルダウンビュー",
      "障害ヒートマップとタイムライン",
      "経営者向けサマリーと月次レポート",
    ],
  },
];

const agentFeatures = [
  {
    Icon: Bot,
    title: "連鎖障害の横断分析",
    desc: "インフラ障害（データベースダウン、キャッシュ障害）がAIエージェントの誤回答にどう連鎖するかを追跡。正常に見えて誤った結果を出す「サイレント劣化」を事前に検出。",
  },
  {
    Icon: Shield,
    title: "予測・評価・管理の3ステップ",
    desc: "AIエージェント耐久性の3つの柱: 障害シナリオのシミュレーション、影響範囲分析によるリリースリスク評価、監視ルールの自動生成。",
  },
  {
    Icon: Boxes,
    title: "4種類の新コンポーネントタイプ",
    desc: "AIエージェント・LLMエンドポイント・ツールサービス・エージェントオーケストレーターを従来のインフラと同じ依存関係グラフに組み込んで分析。",
  },
  {
    Icon: AlertTriangle,
    title: "10種類のAIエージェント障害モード",
    desc: "誤回答・コンテキスト超過・レート制限・トークン枯渇・ツール障害・無限ループ・プロンプトインジェクション・確信度ズレ・推論崩壊・エラー増幅の10パターンを網羅。",
  },
];

export default function FeaturesPage() {
  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white">
      {/* Nav */}
      <nav className="sticky top-0 z-50 border-b border-[#1e293b] bg-[#0a0e1a]/95 backdrop-blur-sm">
        <div className="max-w-[1200px] mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/ja" className="flex items-center gap-2 font-bold">
            <Logo size={24} />
            FaultRay
          </Link>
          <div className="flex items-center gap-4">
            <Link href="/ja#pricing" className="text-sm text-[#94a3b8] hover:text-white transition-colors">
              料金
            </Link>
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl text-sm hover:bg-[#ffe44d] transition-all"
            >
              <Zap size={14} />
              無料で始める
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="py-20 text-center">
        <div className="max-w-[800px] mx-auto px-6">
          <div className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-6">
            機能一覧
          </div>
          <h1 className="text-[clamp(2rem,5vw,3.5rem)] font-extrabold tracking-tight mb-4">
            FaultRayの全機能
          </h1>
          <p className="text-lg text-[#94a3b8] leading-relaxed mb-8">
            本番環境を壊さず、2,000件以上のシナリオでシステムの弱点を自動診断するための機能をすべて網羅しています。
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-6 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] transition-all"
            >
              <Zap size={16} />
              無料で始める
            </Link>
            <Link
              href="/ja"
              className="inline-flex items-center gap-2 px-6 py-3 border border-[#1e293b] text-white rounded-xl hover:border-[#64748b] hover:bg-white/[0.03] transition-all"
            >
              トップページに戻る
            </Link>
          </div>
        </div>
      </section>

      {/* Core Features */}
      <section className="py-16">
        <div className="max-w-[1200px] mx-auto px-6">
          <h2 className="text-2xl font-bold mb-2 text-center">コア機能</h2>
          <p className="text-[#94a3b8] text-center mb-12">ゼロリスク診断の10の柱</p>
          <div className="grid md:grid-cols-2 gap-8">
            {featureCards.map((f) => {
              const Icon = f.Icon;
              return (
                <div
                  key={f.title}
                  className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] hover:border-[#FFD700]/30 hover:bg-[#1a2035] transition-all duration-200"
                >
                  <div className="w-12 h-12 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={22} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed mb-5">{f.desc}</p>
                  <ul className="space-y-2">
                    {f.details.map((detail) => (
                      <li key={detail} className="flex items-start gap-2.5 text-sm text-[#64748b]">
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
      <section className="py-16 bg-[#0f1424] border-t border-[#FFD700]/15">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="text-center mb-12">
            <span className="inline-block px-4 py-1.5 text-[0.8125rem] font-medium text-[#FFD700] border border-[#FFD700]/25 rounded-full bg-[#FFD700]/5 mb-4">
              v11.0 新機能
            </span>
            <h2 className="text-2xl font-bold mb-2">AIエージェント障害シミュレーション</h2>
            <p className="text-[#94a3b8] max-w-[600px] mx-auto">
              インフラ障害がAIエージェントの誤回答にどう連鎖するかを、本番環境で発生する前にシミュレーションします。
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-6">
            {agentFeatures.map((f) => {
              const Icon = f.Icon;
              return (
                <div
                  key={f.title}
                  className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] hover:border-[#FFD700]/30 transition-all duration-200"
                >
                  <div className="w-12 h-12 flex items-center justify-center rounded-xl bg-[#FFD700]/[0.06] border border-[#FFD700]/10 mb-5">
                    <Icon size={22} className="text-[#FFD700]" />
                  </div>
                  <h3 className="text-lg font-bold mb-2">{f.title}</h3>
                  <p className="text-[0.9375rem] text-[#94a3b8] leading-relaxed">{f.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 text-center">
        <div className="max-w-[600px] mx-auto px-6">
          <h2 className="text-2xl font-bold mb-4">今すぐ試す</h2>
          <p className="text-[#94a3b8] mb-8 leading-relaxed">
            無料プランでFaultRayの主要機能をすべて体験できます。クレジットカード不要。
          </p>
          <div className="flex gap-4 justify-center flex-wrap">
            <Link
              href="/login"
              className="inline-flex items-center gap-2 px-7 py-3 bg-[#FFD700] text-[#0a0e1a] font-semibold rounded-xl hover:bg-[#ffe44d] shadow-[0_0_20px_rgba(255,215,0,0.2)] hover:shadow-[0_0_30px_rgba(255,215,0,0.35)] transition-all"
            >
              <Zap size={16} />
              無料で始める
            </Link>
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 px-7 py-3 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-semibold rounded-xl hover:bg-emerald-500/20 transition-all"
            >
              <ExternalLink size={16} />
              デモを予約する
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 border-t border-[#1e293b] text-center">
        <p className="text-sm text-[#64748b]">
          <span className="mr-2">🇯🇵 日本語でのサポートに対応しています</span>
          ·{" "}
          <Link href="/ja" className="hover:text-white transition-colors">
            トップページ
          </Link>
          {" · "}
          <Link href="/contact" className="hover:text-white transition-colors">
            お問い合わせ
          </Link>
        </p>
      </footer>
    </div>
  );
}
