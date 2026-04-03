"use client";

import { useState, useCallback } from "react";
import { useLocale } from "@/lib/useLocale";

const STORAGE_KEY = "faultray_cookie_consent";

function hasConsent(): boolean {
  if (typeof localStorage === "undefined") return true;
  return localStorage.getItem(STORAGE_KEY) !== null;
}

export function CookieConsent() {
  const locale = useLocale();
  // Lazy initializer reads localStorage once at mount — avoids effect-based setState
  const [visible, setVisible] = useState(() => !hasConsent());

  const accept = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "accepted");
    setVisible(false);
  }, []);

  const decline = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, "declined");
    setVisible(false);
  }, []);

  if (!visible) return null;

  const isJa = locale === "ja";

  return (
    <div
      role="region"
      aria-label={isJa ? "クッキーの同意" : "Cookie consent"}
      aria-live="polite"
      className="fixed bottom-0 left-0 right-0 z-50 bg-[#111827] border-t border-[#1e293b] px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
    >
      <p className="text-sm text-[#94a3b8] max-w-xl">
        {isJa ? (
          <>
            トラフィック分析とエクスペリエンス向上のためにCookieを使用しています。
            分析用Cookieはご同意をいただいた場合のみ読み込まれます。{" "}
            <a href="/privacy" className="text-[#FFD700] hover:underline">
              プライバシーポリシー
            </a>
          </>
        ) : (
          <>
            We use cookies to analyze traffic and improve your experience. Analytics cookies are
            only loaded with your consent.{" "}
            <a href="/privacy" className="text-[#FFD700] hover:underline">
              Privacy Policy
            </a>
          </>
        )}
      </p>
      <div className="flex gap-3 shrink-0">
        <button
          onClick={decline}
          className="px-4 py-2 text-sm rounded-lg border border-[#1e293b] text-[#94a3b8] hover:text-white hover:border-[#334155] transition-colors"
          aria-label={isJa ? "必須以外のCookieを拒否する" : "Decline non-essential cookies"}
        >
          {isJa ? "拒否" : "Decline"}
        </button>
        <button
          onClick={accept}
          className="px-4 py-2 text-sm rounded-lg bg-[#FFD700] text-[#0a0e1a] font-semibold hover:bg-[#FFC700] transition-colors"
          aria-label={isJa ? "すべてのCookieを受け入れる" : "Accept all cookies"}
        >
          {isJa ? "同意する" : "Accept"}
        </button>
      </div>
    </div>
  );
}
