import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "特定商取引法に基づく表記",
  description: "FaultRayの特定商取引法に基づく表記ページです。",
  alternates: { canonical: "https://faultray.com/tokushoho" },
};

interface Row {
  label: string;
  value: string | React.ReactNode;
}

const rows: Row[] = [
  { label: "販売業者", value: "前田 勇太郎（個人事業主）" },
  { label: "運営統括責任者", value: "前田 勇太郎" },
  { label: "所在地", value: "〒253-0044 神奈川県茅ヶ崎市新栄町（詳細はお問い合わせください）" },
  {
    label: "連絡先",
    value: (
      <a
        href="mailto:contact@faultray.com"
        className="text-[#FFD700] hover:underline"
      >
        contact@faultray.com
      </a>
    ),
  },
  {
    label: "電話番号",
    value: "メールにてお問い合わせください（contact@faultray.com）",
  },
  {
    label: "販売価格",
    value: (
      <ul className="space-y-1 list-disc list-inside">
        <li>Pro Plan: 月額 45,000円（税別）/ 年額 432,000円（税別）</li>
        <li>Business Plan: 月額 150,000円（税別）/ 年額 1,440,000円（税別）</li>
      </ul>
    ),
  },
  { label: "支払方法", value: "クレジットカード（Stripe経由：VISA / Mastercard / American Express 他）" },
  { label: "支払時期", value: "サービス利用開始時（サブスクリプション更新時は更新日）" },
  { label: "引渡時期", value: "決済完了後、即時利用可能" },
  {
    label: "返品・キャンセルについて",
    value:
      "サブスクリプションは次回更新日前であればいつでも解約可能です。解約後も現在の契約期間末日まではサービスをご利用いただけます。日割り計算による返金は行っておりません。なお、デジタルコンテンツの性質上、提供開始後の返金は原則としてお断りしております。",
  },
  {
    label: "動作環境",
    value: "最新バージョンのChrome / Firefox / Safari / Edge（JavaScript有効）",
  },
];

export default function TokushohoPage() {
  return (
    <div className="max-w-[860px] mx-auto px-6 py-20">
      <h1 className="text-2xl font-bold tracking-tight mb-2">
        特定商取引法に基づく表記
      </h1>
      <p className="text-sm text-[#64748b] mb-10">
        特定商取引に関する法律第11条に基づき、以下の事項を表示します。
      </p>

      <div className="rounded-2xl border border-[#1e293b] overflow-hidden">
        <table className="w-full border-collapse text-sm">
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.label}
                className={i < rows.length - 1 ? "border-b border-[#1e293b]" : ""}
              >
                <th scope="col" className="px-6 py-4 text-left font-semibold text-[#94a3b8] bg-[#141a2e] w-40 align-top whitespace-nowrap">
                  {row.label}
                </th>
                <td className="px-6 py-4 text-white bg-[#111827] leading-relaxed">
                  {row.value}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-8 text-xs text-[#64748b]">
        本表記は予告なく変更される場合があります。最新の情報はこのページをご確認ください。
      </p>

      <div className="mt-10 pt-8 border-t border-[#1e293b] flex flex-wrap gap-6 text-sm text-[#64748b]">
        <Link href="/privacy" className="hover:text-white transition-colors">
          プライバシーポリシー
        </Link>
        <Link href="/terms" className="hover:text-white transition-colors">
          利用規約
        </Link>
        <Link href="/pricing" className="hover:text-white transition-colors">
          料金プラン
        </Link>
        <Link href="/" className="hover:text-white transition-colors">
          ホーム
        </Link>
      </div>
    </div>
  );
}
