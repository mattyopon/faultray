"use client";

import Link from "next/link";
import { useLocale } from "@/lib/useLocale";

export default function NotFound() {
  const locale = useLocale();
  const isJa = locale === "ja";

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)]">
      <div className="text-center">
        <p className="text-xs font-semibold text-[var(--gold)] uppercase tracking-widest mb-4">
          FaultRay
        </p>
        <h1 className="text-8xl font-bold text-[var(--gold)] mb-4 leading-none">
          404
        </h1>
        <p className="text-[var(--text-secondary)] text-lg mb-8">
          {isJa ? "ページが見つかりません" : "Page not found"}
        </p>
        <Link
          href="/"
          className="inline-block px-6 py-3 bg-[var(--gold)] text-white rounded-lg font-semibold hover:opacity-90 transition-opacity"
        >
          {isJa ? "トップへ戻る" : "Back to Home"}
        </Link>
      </div>
    </div>
  );
}
