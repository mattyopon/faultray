"use client";

import { usePathname, useRouter } from "next/navigation";
import { locales, type Locale } from "@/i18n/config";
import { useLocale, useSetLocale } from "@/lib/useLocale";

const languageNames: Record<Locale, string> = {
  en: "English",
  ja: "日本語",
  de: "Deutsch",
  fr: "Français",
  zh: "中文",
  ko: "한국어",
  es: "Español",
  pt: "Português",
};

export function LanguageSwitcher() {
  const locale = useLocale();
  const setLocale = useSetLocale();
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(newLocale: string) {
    setLocale(newLocale as Locale);

    // If on a locale-prefixed LP page, update the URL
    for (const loc of locales) {
      if (pathname.startsWith(`/${loc}/`) || pathname === `/${loc}`) {
        const newPath = pathname.replace(`/${loc}`, `/${newLocale}`);
        router.push(newPath);
        return;
      }
    }
    // App pages — no URL change needed, Context handles it
  }

  return (
    <div className="relative inline-block">
      <select
        value={locale}
        onChange={(e) => switchLocale(e.target.value)}
        className="appearance-none bg-[var(--bg-card)] border border-[var(--border-color)] text-[var(--text-secondary)] text-sm rounded-lg px-3 py-1.5 pr-8 cursor-pointer hover:border-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus:outline-none focus:border-[var(--gold)]/50"
      >
        {locales.map((l) => (
          <option key={l} value={l} className="bg-[var(--bg-card)] text-[var(--text-primary)]">
            {languageNames[l]}
          </option>
        ))}
      </select>
      <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
        <svg className="w-4 h-4 text-[var(--text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

export function NavLanguageSwitcher() {
  const locale = useLocale();
  const setLocale = useSetLocale();
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(newLocale: string) {
    setLocale(newLocale as Locale);

    for (const loc of locales) {
      if (pathname.startsWith(`/${loc}/`) || pathname === `/${loc}`) {
        router.push(pathname.replace(`/${loc}`, `/${newLocale}`));
        return;
      }
    }
  }

  return (
    <select
      value={locale}
      onChange={(e) => switchLocale(e.target.value)}
      className="appearance-none bg-transparent border border-[var(--border-color)] text-[var(--text-secondary)] text-xs rounded-md px-2 py-1 pr-6 cursor-pointer hover:border-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus:outline-none focus:border-[var(--gold)]/50"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Cpath d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 4px center",
      }}
    >
      {locales.map((l) => (
        <option key={l} value={l} className="bg-[var(--bg-card)] text-[var(--text-primary)]">
          {languageNames[l]}
        </option>
      ))}
    </select>
  );
}
