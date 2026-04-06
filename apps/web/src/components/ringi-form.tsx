"use client";

import { useState } from "react";
import { FileText, Download, CheckCircle2, ArrowRight } from "lucide-react";
import Link from "next/link";

type Plan = "starter" | "pro" | "business";

const PLAN_MONTHLY: Record<Plan, string> = {
  starter: "¥15,000",
  pro: "¥45,000",
  business: "¥150,000",
};

const PLAN_ANNUAL: Record<Plan, string> = {
  starter: "¥143,000",
  pro: "¥430,000",
  business: "¥1,440,000",
};

const PLAN_USD_MONTHLY: Record<Plan, string> = {
  starter: "$99",
  pro: "$299",
  business: "$999",
};

const PLAN_USD_ANNUAL: Record<Plan, string> = {
  starter: "$949",
  pro: "$2,869",
  business: "$9,590",
};

export function RingiForm() {
  const [companyName, setCompanyName] = useState("");
  const [plan, setPlan] = useState<Plan>("pro");

  const displayCompany = companyName.trim() || "貴社";

  function handlePrint() {
    window.print();
  }

  return (
    <>
      {/* Print styles */}
      <style>{`
        @media print {
          .ringi-no-print { display: none !important; }
          nav, header { display: none !important; }
          body { background: #fff !important; color: #000 !important; }
          .ringi-section {
            border: 1px solid #ccc !important;
            background: #fff !important;
            break-inside: avoid;
          }
          .ringi-section h2 { color: #000 !important; }
          .ringi-table-header { background: #f5f5f5 !important; }
          .ringi-gold { color: #b8860b !important; }
          .ringi-muted { color: #555 !important; }
          .ringi-white { color: #000 !important; }
          .ringi-emerald { color: #166534 !important; }
        }
      `}</style>

      {/* Input form + Download button */}
      <div className="ringi-no-print mb-10 p-5 rounded-2xl border border-[#1e293b] bg-[#0d1117] flex flex-wrap gap-4 items-end">
        <div className="flex flex-col gap-1 min-w-[200px]">
          <label className="text-xs text-[#64748b] font-semibold" htmlFor="companyName">
            会社名
          </label>
          <input
            id="companyName"
            type="text"
            placeholder="株式会社〇〇"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            className="px-3 py-2 rounded-lg bg-[#111827] border border-[#1e293b] text-white text-sm placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b] font-semibold" htmlFor="planSelect">
            選択プラン
          </label>
          <select
            id="planSelect"
            value={plan}
            onChange={(e) => setPlan(e.target.value as Plan)}
            className="px-3 py-2 rounded-lg bg-[#111827] border border-[#1e293b] text-white text-sm focus:outline-none focus:border-[#FFD700]/50"
          >
            <option value="starter">Starter（¥15,000/月）</option>
            <option value="pro">Pro（¥45,000/月）</option>
            <option value="business">Business（¥150,000/月）</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label className="text-xs text-[#64748b] font-semibold">月額費用</label>
          <div className="px-3 py-2 rounded-lg bg-[#0a0e1a] border border-[#1e293b] text-[#FFD700] text-sm font-mono">
            {PLAN_MONTHLY[plan]}
          </div>
        </div>

        <button
          onClick={handlePrint}
          className="ml-auto inline-flex items-center gap-2 px-5 py-2.5 bg-[#FFD700] text-[#0a0e1a] font-bold rounded-xl hover:bg-[#ffe44d] transition-colors text-sm whitespace-nowrap"
        >
          <FileText size={15} />
          <Download size={15} />
          稟議書PDFをダウンロード
        </button>
      </div>

      {/* Template body */}
      <div className="space-y-8 text-[#94a3b8] leading-relaxed">
        {/* 1. 件名 */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">1. 件名</h2>
          <div className="p-4 rounded-lg bg-[#0d1117] border border-[#1e293b] font-mono text-sm">
            {displayCompany}におけるインフラ信頼性シミュレーションSaaS「FaultRay」導入の件
          </div>
        </section>

        {/* 2. 目的 */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">2. 目的・背景</h2>
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
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">3. 期待される導入効果</h2>
          <div className="space-y-3">
            {[
              { label: "可用性の定量証明", desc: "N-Layer分析により稼働率の上限値（例: 99.9991%）を算出し、顧客・投資家への説明資料として活用できます。" },
              { label: "障害コストの削減", desc: "本番障害の平均コストは1時間あたり数百万円。事前にボトルネックを特定し、高優先度の改善を実施できます。" },
              { label: "DORA/SOC2対応の加速", desc: "コンプライアンスレポートをPDF出力し、監査対応時間を大幅に削減します。" },
              { label: "エンジニアの工数削減", desc: "手動によるカオスエンジニアリングに比べ、90%以上の時間削減が見込まれます。" },
            ].map((item) => (
              <div key={item.label} className="flex gap-3">
                <CheckCircle2 size={16} className="ringi-emerald text-emerald-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-white">{item.label}</p>
                  <p className="ringi-muted text-sm text-[#94a3b8]">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 4. コスト・ROI */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">4. コスト・ROI試算</h2>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
            <table className="w-full text-sm">
              <thead>
                <tr className="ringi-table-header border-b border-[#1e293b] bg-[#0d1117]">
                  <th scope="col" className="px-4 py-3 text-left text-[#64748b] font-semibold">項目</th>
                  <th scope="col" className="px-4 py-3 text-right text-[#64748b] font-semibold">Proプラン</th>
                  <th scope="col" className="px-4 py-3 text-right text-[#64748b] font-semibold">Businessプラン</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                <tr>
                  <td className="ringi-muted px-4 py-3 text-[#94a3b8]">月額費用（月払い）</td>
                  <td className={`px-4 py-3 text-right font-semibold ${plan === "pro" ? "text-[#FFD700] ringi-gold" : ""}`}>
                    {PLAN_USD_MONTHLY.pro}（約{PLAN_MONTHLY.pro}）
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${plan === "business" ? "text-[#FFD700] ringi-gold" : ""}`}>
                    {PLAN_USD_MONTHLY.business}（約{PLAN_MONTHLY.business}）
                  </td>
                </tr>
                <tr>
                  <td className="ringi-muted px-4 py-3 text-[#94a3b8]">年間費用（年払い・20%割引）</td>
                  <td className={`px-4 py-3 text-right ${plan === "pro" ? "text-[#FFD700] ringi-gold" : ""}`}>
                    {PLAN_USD_ANNUAL.pro}（約{PLAN_ANNUAL.pro}）
                  </td>
                  <td className={`px-4 py-3 text-right ${plan === "business" ? "text-[#FFD700] ringi-gold" : ""}`}>
                    {PLAN_USD_ANNUAL.business}（約{PLAN_ANNUAL.business}）
                  </td>
                </tr>
                <tr>
                  <td className="ringi-muted px-4 py-3 text-[#94a3b8]">14日間無料トライアル</td>
                  <td className="ringi-emerald px-4 py-3 text-right text-emerald-400">あり（クレカ不要）</td>
                  <td className="ringi-muted px-4 py-3 text-right text-[#64748b]">要相談</td>
                </tr>
                <tr className="bg-[#FFD700]/[0.04]">
                  <td className="ringi-white px-4 py-3 text-white font-semibold">障害1件回避時の期待コスト削減</td>
                  <td className="ringi-gold px-4 py-3 text-right text-[#FFD700] font-bold" colSpan={2}>¥500万〜¥5,000万（規模による）</td>
                </tr>
                <tr className="bg-[#FFD700]/[0.08]">
                  <td className="ringi-white px-4 py-3 text-white font-semibold">申請プランの月額費用</td>
                  <td className="ringi-gold px-4 py-3 text-right text-[#FFD700] font-bold text-base" colSpan={2}>
                    {PLAN_MONTHLY[plan]}／月（{plan === "pro" ? "Pro" : "Business"}プラン）
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[#475569] mt-3">
            ※ 為替レートは1USD=150円で計算。実際の為替に合わせて修正してください。
          </p>
        </section>

        {/* 4.5 競合比較 */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">5. 競合ツールとの比較</h2>
          <div className="overflow-x-auto rounded-xl border border-[#1e293b]">
            <table className="w-full text-sm">
              <thead>
                <tr className="ringi-table-header border-b border-[#1e293b] bg-[#0d1117]">
                  <th scope="col" className="px-4 py-3 text-left text-[#64748b] font-semibold">項目</th>
                  <th scope="col" className="px-4 py-3 text-center text-[#FFD700] font-semibold">FaultRay</th>
                  <th scope="col" className="px-4 py-3 text-center text-[#64748b] font-semibold">Gremlin</th>
                  <th scope="col" className="px-4 py-3 text-center text-[#64748b] font-semibold">Datadog</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1e293b]">
                {[
                  { item: "方式", fr: "純シミュレーション", gr: "実障害注入", dd: "監視+テスト" },
                  { item: "本番リスク", fr: "なし（安全）", gr: "あり（実注入）", dd: "低〜中" },
                  { item: "初期費用", fr: "¥0（無料プランあり）", gr: "要見積（年¥150万〜）", dd: "要見積（年¥100万〜）" },
                  { item: "導入期間", fr: "即日（YAML貼付のみ）", gr: "数日〜数週間", dd: "数日〜数週間" },
                  { item: "日本語サポート", fr: "あり", gr: "英語のみ", dd: "一部あり" },
                  { item: "稟議書支援", fr: "テンプレート提供", gr: "なし", dd: "なし" },
                ].map((row) => (
                  <tr key={row.item}>
                    <td className="ringi-muted px-4 py-3 text-[#94a3b8]">{row.item}</td>
                    <td className="px-4 py-3 text-center text-[#FFD700] font-semibold ringi-gold">{row.fr}</td>
                    <td className="px-4 py-3 text-center text-[#94a3b8]">{row.gr}</td>
                    <td className="px-4 py-3 text-center text-[#94a3b8]">{row.dd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* 6. セキュリティ・データ管理 */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">6. セキュリティ・データ管理</h2>
          <div className="space-y-2 text-sm">
            {[
              "入力するインフラ情報は「トポロジー構造（コンポーネント名と接続関係）」のみです。実際のIPアドレス・認証情報・ソースコードは不要です。",
              "データは暗号化の上、シミュレーション処理にのみ使用されます。第三者への提供・海外移転は行いません。",
              "DPA（Data Processing Agreement）を締結できます。詳細はfaultray.com/dpaをご参照ください。",
              "GDPR Article 28 準拠のデータ処理体制を整えています。",
            ].map((text, i) => (
              <div key={i} className="flex gap-3">
                <CheckCircle2 size={14} className="ringi-emerald text-emerald-400 shrink-0 mt-0.5" />
                <p>{text}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 6. スケジュール */}
        <section className="ringi-section p-6 rounded-2xl border border-[#1e293b] bg-[#111827]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">7. 導入スケジュール（案）</h2>
          <div className="space-y-3 text-sm">
            {[
              { phase: "Week 1", action: "14日間無料トライアル開始、既存インフラのYAMLトポロジーを作成" },
              { phase: "Week 2", action: "シミュレーション実行、初回レポート生成、ボトルネック確認" },
              { phase: "Week 3–4", action: "結果を基に改善案策定、関係部署への共有" },
              { phase: "Month 2–", action: "正式契約、定期的なシミュレーション運用開始" },
            ].map((item) => (
              <div key={item.phase} className="flex gap-4">
                <span className="ringi-gold text-[#FFD700] font-mono w-20 shrink-0">{item.phase}</span>
                <span className="ringi-muted text-[#94a3b8]">{item.action}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 7. 決裁依頼 */}
        <section className="ringi-section p-6 rounded-2xl border border-[#FFD700]/20 bg-[#FFD700]/[0.04]">
          <h2 className="ringi-white text-lg font-bold text-white mb-4">8. 決裁依頼内容</h2>
          <div className="space-y-2 text-sm">
            <p>
              <strong className="ringi-white text-white">申請金額:</strong>{" "}
              {plan === "starter"
                ? `Starterプラン年払い ${PLAN_USD_ANNUAL.starter}/年（約${PLAN_ANNUAL.starter}/年）`
                : plan === "pro"
                ? `Proプラン年払い ${PLAN_USD_ANNUAL.pro}/年（約${PLAN_ANNUAL.pro}/年）`
                : `Businessプラン年払い ${PLAN_USD_ANNUAL.business}/年（約${PLAN_ANNUAL.business}/年）`}
            </p>
            <p><strong className="ringi-white text-white">申請期間:</strong> 202X年X月〜202X年X月（1年間）</p>
            <p><strong className="ringi-white text-white">導入会社:</strong> {displayCompany}</p>
            <p><strong className="ringi-white text-white">担当部署:</strong> [部署名]</p>
            <p><strong className="ringi-white text-white">申請者:</strong> [氏名]</p>
            <p className="mt-4 ringi-muted text-[#94a3b8]">
              上記内容にてご承認いただけますよう、よろしくお願いいたします。
              ご不明な点はsales@faultray.comまでお問い合わせください。
            </p>
          </div>
        </section>
      </div>

      {/* JP-06: IT導入補助金との相性 */}
      <div className="ringi-section mt-12 p-6 rounded-2xl border border-blue-500/20 bg-blue-500/[0.04]">
        <h3 className="ringi-white text-base font-bold text-white mb-2 flex items-center gap-2">
          <CheckCircle2 size={16} className="ringi-emerald text-blue-400" />
          IT導入補助金の活用について
        </h3>
        <p className="ringi-muted text-sm text-[#94a3b8] mb-3">
          FaultRayはITツールとしてIT導入補助金の対象となる可能性がありますが、
          補助金申請には以下の条件確認が必要です：
        </p>
        <ul className="space-y-2 text-sm text-[#94a3b8]">
          {[
            "FaultRayがITツール登録業者のリストに掲載されていることが条件となります（現在申請手続き中）",
            "補助金申請の際は、FaultRayの「プロセス改善への寄与」と「生産性向上効果」を定量的に示す必要があります",
            "当社のレポート機能（可用性スコア改善率、インシデント削減数）が効果測定書類として活用できます",
          ].map((text, i) => (
            <li key={i} className="flex items-start gap-2">
              <span className="text-blue-400 shrink-0">•</span>
              <span>{text}</span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-[#64748b] mt-3">
          詳細はsales@faultray.comまでお問い合わせください。申請サポートも承っております。
        </p>
      </div>

      {/* Actions */}
      <div className="ringi-no-print mt-12 flex flex-wrap items-center gap-4">
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
    </>
  );
}
