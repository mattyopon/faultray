"use client";

import Link from "next/link";
import { useLocale } from "@/lib/useLocale";

export default function NotFound() {
  const locale = useLocale();
  const isJa = locale === "ja";

  return (
    <div className="min-h-screen bg-[#0a0e1a] flex items-center justify-center">
      <div className="text-center">
        <p className="text-xs font-semibold text-[#FFD700] uppercase tracking-widest mb-4">
          FaultRay
        </p>
        <h1 className="text-8xl font-bold text-[#FFD700] mb-4 leading-none">
          404
        </h1>
        <p className="text-[#94a3b8] text-lg mb-8">
          {isJa ? "ページが見つかりません" : "Page not found"}
        </p>
        <Link
          href="/dashboard"
          className="inline-block px-6 py-3 bg-[#FFD700] text-black rounded-lg font-semibold hover:bg-yellow-400 transition-colors"
        >
          {isJa ? "ダッシュボードへ戻る" : "Back to Dashboard"}
        </Link>
      </div>
    </div>
  );
}
