"use client";

import { useState, useCallback } from "react";

const STORAGE_KEY = "faultray_cookie_consent";

function hasConsent(): boolean {
  if (typeof localStorage === "undefined") return true;
  return localStorage.getItem(STORAGE_KEY) !== null;
}

export function CookieConsent() {
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

  return (
    <div
      role="region"
      aria-label="Cookie consent"
      aria-live="polite"
      className="fixed bottom-0 left-0 right-0 z-50 bg-[var(--bg-card)] border-t border-[var(--border-color)] px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
    >
      <p className="text-sm text-[var(--text-secondary)] max-w-xl">
        We use cookies to analyze traffic and improve your experience. Analytics cookies are
        only loaded with your consent.{" "}
        <a href="/privacy" className="text-[var(--gold)] hover:underline">
          Privacy Policy
        </a>
      </p>
      <div className="flex gap-3 shrink-0">
        <button
          onClick={decline}
          className="px-4 py-2 text-sm rounded-lg border border-[var(--border-color)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--text-muted)] transition-colors"
          aria-label="Decline non-essential cookies"
        >
          Decline
        </button>
        <button
          onClick={accept}
          className="px-4 py-2 text-sm rounded-lg bg-[var(--gold)] text-white font-semibold hover:bg-[#044a99] transition-colors"
          aria-label="Accept all cookies"
        >
          Accept
        </button>
      </div>
    </div>
  );
}
