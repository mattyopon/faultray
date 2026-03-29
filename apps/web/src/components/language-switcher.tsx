"use client";

import { useRouter, usePathname } from "next/navigation";
import { locales, type Locale } from "@/i18n/config";

const languageNames: Record<Locale, string> = {
  en: "English",
  ja: "日本語",
  de: "Deutsch",
  fr: "Français",
};

export function LanguageSwitcher({ currentLang }: { currentLang: string }) {
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(newLocale: string) {
    // Set cookie for persistence
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;

    // Replace the locale segment in the current path
    let newPath = pathname;
    for (const locale of locales) {
      if (pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`) {
        newPath = pathname.replace(`/${locale}`, `/${newLocale}`);
        break;
      }
    }

    // If no locale prefix found in path, add one
    if (newPath === pathname) {
      newPath = `/${newLocale}${pathname}`;
    }

    router.push(newPath);
  }

  return (
    <div className="relative inline-block">
      <select
        value={currentLang}
        onChange={(e) => switchLocale(e.target.value)}
        className="appearance-none bg-[#111827] border border-[#1e293b] text-[#94a3b8] text-sm rounded-lg px-3 py-1.5 pr-8 cursor-pointer hover:border-[#64748b] hover:text-white transition-colors focus:outline-none focus:border-[#FFD700]/50"
      >
        {locales.map((locale) => (
          <option key={locale} value={locale}>
            {languageNames[locale]}
          </option>
        ))}
      </select>
      <div className="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none">
        <svg className="w-4 h-4 text-[#64748b]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
}

export function NavLanguageSwitcher({ currentLang }: { currentLang: string }) {
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(newLocale: string) {
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;

    let newPath = pathname;
    for (const locale of locales) {
      if (pathname.startsWith(`/${locale}/`) || pathname === `/${locale}`) {
        newPath = pathname.replace(`/${locale}`, `/${newLocale}`);
        break;
      }
    }

    if (newPath === pathname) {
      newPath = `/${newLocale}`;
    }

    router.push(newPath);
  }

  return (
    <select
      value={currentLang}
      onChange={(e) => switchLocale(e.target.value)}
      className="appearance-none bg-transparent border border-[#1e293b] text-[#94a3b8] text-xs rounded-md px-2 py-1 pr-6 cursor-pointer hover:border-[#64748b] hover:text-white transition-colors focus:outline-none focus:border-[#FFD700]/50"
      style={{
        backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Cpath d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 4px center",
      }}
    >
      {locales.map((locale) => (
        <option key={locale} value={locale}>
          {languageNames[locale]}
        </option>
      ))}
    </select>
  );
}
