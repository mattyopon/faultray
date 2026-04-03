import Link from "next/link";
import { FileText } from "lucide-react";
import { RingiForm } from "@/components/ringi-form";

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

      <RingiForm />
    </div>
  );
}
