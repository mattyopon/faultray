import type { Metadata } from "next";
import Link from "next/link";
import { FileText, Download, CheckCircle2, ArrowRight } from "lucide-react";

export const metadata: Metadata = {
  title: "稟議書テンプレート | FaultRay",
  description:
    "FaultRay導入のための稟議書テンプレート。コスト、ROI、セキュリティ、コンプライアンス対応をまとめた日本語テンプレートを無償提供します。",
  alternates: { canonical: "https://faultray.com/ringi" },
};

/* ============================================================
 * Page — MATERIAL-02: 稟議書テンプレート（日本向け）
 * ============================================================ */
export default function RingiPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      {/* Back */}
      <div className="mb-10">
        <Link href="/ja" className="text-sm text-[#64748b] hover:text-white transition-colors">
          &larr; トップへ戻る
        </Link>
      </div>

      {/* Header */}
      <div className="flex items-center gap-4 mb-4">
        <FileText size={28} className="text-[#FFD700]" />
        <h1 className="text-3xl font-bold tracking-tight">FaultRay 導入稟議書テンプレート</h1>
      </div>
      <p className="text-[#94a3b8] mb-2">
        社内承認を円滑に進めるための稟議書テンプレートです。コスト・ROI・セキュリティ・コンプライアンスの各観点をまとめています。
      </p>
      <p className="text-sm text-[#475569] mb-12">
        このテンプレートをベースに、貴社の状況に合わせて数値や文言を編集してご利用ください。
        PoC支援や追加資料が必要な場合は{" "}
        <Link href="mailto:sales@faultray.com" className="text-[#FFD700] hover:underline">
          sales@faultray.com
        </Link>{" "}
        までご連絡ください。
      </p>

      {/* Template body */}
      <div className="space-y-8 text-[#94a3b8] leading-relaxed">
        {/* 1. 件名 */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">1. 件名</h2>
          <div className="p-4 rounded-lg bg-[#0d1117] border border-[#1e293b] font-mono text-sm">
            インフラ信頼性シミュレーションSaaS「FaultRay」導入の件
          </div>
        </section>

        {/* 2. 目的 */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">2. 目的・背景</h2>
          <div className="space-y-3 text-sm">
            <p>
              近年、クラウドインフラの複雑化に伴い、障害時の影響範囲が拡大しています。
              現状は本番環境で障害テストを実施できず、システムの可用性を定量的に証明する手段がありません。
            </p>
            <p>
              FaultRayは<strong className="text-white">本番環境を一切操作せずに</strong>、
              2,048以上のシナリオをシミュレーションし、可用性の上限値を数学的に算出するSaaSです。
              これにより、監査対応・障害予防・SLA達成の根拠資料を迅速に取得できます。
            </p>
          </div>
        </section>

        {/* 3. 導入効果 */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">3. 期待される導入効果</h2>
          <div className="space-y-3">
            {[
              { label: "可用性の定量証明", desc: "N-Layer分析により稼働率の上限値（例: 99.9991%）を算出し、顧客・投資家への説明資料として活用できます。" },
              { label: "障害コストの削減", desc: "本番障害の平均コストは1時間あたり数百万円。事前にボトルネックを特定し、高優先度の改善を実施できます。" },
              { label: "DORA/SOC2対応の加速", desc: "コンプライアンスレポートをPDF出力し、監査対応時間を大幅に削減します。" },
              { label: "エンジニアの工数削減", desc: "手動によるカオスエンジニアリングに比べ、90%以上の時間削減が見込まれます。" },
            ].map((item) => (
              <div key={item.label} className="flex gap-3">
                <CheckCircle2 size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-white">{item.label}</p>
                  <p className="text-sm text-[#94a3b8]">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 4. コスト・ROI */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">4. コスト・ROI試算</h2>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#1e293b] bg-[#0d1117]">
                  <th className="px-4 py-3 text-left text-[#64748b] font-semibold">項目</th>
                  <th className="px-4 py-3 text-right text-[#64748b] font-semibold">Proプラン</th>
                  <th className="px-4 py-3 text-right text-[#64748b] font-semibold">Businessプラン</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                <tr>
                  <td className="px-4 py-3 text-[#94a3b8]">月額費用（月払い）</td>
                  <td className="px-4 py-3 text-right">$299（約¥45,000）</td>
                  <td className="px-4 py-3 text-right">$999（約¥150,000）</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 text-[#94a3b8]">年間費用（年払い・20%割引）</td>
                  <td className="px-4 py-3 text-right">$2,869（約¥430,000）</td>
                  <td className="px-4 py-3 text-right">$9,590（約¥1,440,000）</td>
                </tr>
                <tr>
                  <td className="px-4 py-3 text-[#94a3b8]">14日間無料トライアル</td>
                  <td className="px-4 py-3 text-right text-emerald-400">あり（クレカ不要）</td>
                  <td className="px-4 py-3 text-right text-[#64748b]">要相談</td>
                </tr>
                <tr className="bg-[#FFD700]/[0.04]">
                  <td className="px-4 py-3 text-white font-semibold">障害1件回避時の期待コスト削減</td>
                  <td className="px-4 py-3 text-right text-[#FFD700] font-bold" colSpan={2}>¥500万〜¥5,000万（規模による）</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[#475569] mt-3">
            ※ 為替レートは1USD=150円で計算。実際の為替に合わせて修正してください。
          </p>
        </section>

        {/* 5. セキュリティ・データ管理 */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">5. セキュリティ・データ管理</h2>
          <div className="space-y-2 text-sm">
            {[
              "入力するインフラ情報は「トポロジー構造（コンポーネント名と接続関係）」のみです。実際のIPアドレス・認証情報・ソースコードは不要です。",
              "データは暗号化の上、シミュレーション処理にのみ使用されます。第三者への提供・海外移転は行いません。",
              "DPA（Data Processing Agreement）を締結できます。詳細はfaultray.com/dpaをご参照ください。",
              "GDPR Article 28 準拠のデータ処理体制を整えています。",
            ].map((text, i) => (
              <div key={i} className="flex gap-3">
                <CheckCircle2 size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                <p>{text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 6. スケジュール */}
        <section className="p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="text-lg font-bold text-white mb-4">6. 導入スケジュール（案）</h2>
          <div className="space-y-3 text-sm">
            {[
              { phase: "Week 1", action: "14日間無料トライアル開始、既存インフラのYAMLトポロジーを作成" },
              { phase: "Week 2", action: "シミュレーション実行、初回レポート生成、ボトルネック確認" },
              { phase: "Week 3–4", action: "結果を基に改善案策定、関係部署への共有" },
              { phase: "Month 2–", action: "正式契約、定期的なシミュレーション運用開始" },
            ].map((item) => (
              <div key={item.phase} className="flex gap-4">
                <span className="text-[#FFD700] font-mono w-20 shrink-0">{item.phase}</span>
                <span className="text-[#94a3b8]">{item.action}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 7. 決裁依頼 */}
        <section className="p-6 rounded-2xl border border-[#FFD700]/20 bg-[#FFD700]/[0.04]">
          <h2 className="text-lg font-bold text-white mb-4">7. 決裁依頼内容</h2>
          <div className="space-y-2 text-sm">
            <p><strong className="text-white">申請金額:</strong> Proプラン年払い $2,869/年（約¥430,000/年）</p>
            <p><strong className="text-white">申請期間:</strong> 202X年X月〜202X年X月（1年間）</p>
            <p><strong className="text-white">担当部署:</strong> [部署名]</p>
            <p><strong className="text-white">申請者:</strong> [氏名]</p>
            <p className="mt-4 text-[#94a3b8]">
              上記内容にてご承認いただけますよう、よろしくお願いいたします。
              ご不明な点はsales@faultray.comまでお問い合わせください。
            </p>
          </div>
        </section>
      </div>

      {/* Actions */}
      <div className="mt-12 flex flex-wrap items-center gap-4">
        <a
          href="/pricing"
          className="inline-flex items-center gap-2 px-6 py-3 bg-[#FFD700] text-[#0a0e1a] font-bold rounded-xl hover:bg-[#ffe44d] transition-colors"
        >
          <Download size={16} />
          プランを確認する
        </a>
        <Link
          href="mailto:sales@faultray.com?subject=稟議書について相談したい"
          className="inline-flex items-center gap-2 px-6 py-3 border border-[#FFD700]/30 text-[#FFD700] font-semibold rounded-xl hover:bg-[#FFD700]/10 transition-colors"
        >
          導入支援の相談
          <ArrowRight size={16} />
        </Link>
      </div>
    </div>
  );
}
