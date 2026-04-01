"use client";

import { useState } from "react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: { title: "DORA Compliance Dashboard", subtitle: "Test version" },
  ja: { title: "DORA コンプライアンスダッシュボード", subtitle: "テスト版" },
};

export default function DoraPage() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;
  const [count, setCount] = useState(0);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <h1 className="text-2xl font-bold mb-1 text-white">{t.title}</h1>
      <p className="text-[#94a3b8] text-sm mb-4">{t.subtitle}</p>
      <p className="text-white">Counter: {count}</p>
      <button onClick={() => setCount(c => c + 1)} className="px-4 py-2 bg-[#FFD700] text-black rounded mt-2">
        Click me
      </button>
    </div>
  );
}
