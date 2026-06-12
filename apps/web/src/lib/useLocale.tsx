"use client";

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { locales, type Locale, defaultLocale } from "@/i18n/config";

interface LocaleContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextType>({
  locale: defaultLocale,
  setLocale: () => {},
});

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);

  useEffect(() => {
    // I18N-05: パス先頭のロケール（/ja 等）は「いま表示している言語」なので
    // cookie より優先する。cookie はロケール無しページでのフォールバック。
    // render 中の usePathname は rewrite 環境で hydration mismatch を
    // 起こしうるため、effect 内で window.location を読む（Next docs 準拠）。
    const seg = window.location.pathname.split("/")[1];
    if (locales.includes(seg as Locale)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLocaleState(seg as Locale);
      return;
    }
    // LIB-06: ロケールcookieのパース — (\w+)ではハイフン等が含まれないため[^;,\s]+に拡張
    const match = document.cookie.match(/(?:^|;\s*)NEXT_LOCALE=([^;,\s]+)/);
    if (match && locales.includes(match[1] as Locale)) {
      setLocaleState(match[1] as Locale);
    }
  }, []);

  // I18N-04: html lang属性をlocaleに合わせて動的に更新
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    document.cookie = `NEXT_LOCALE=${newLocale};path=/;max-age=31536000`;
    setLocaleState(newLocale);
  }, []);

  return (
    <LocaleContext.Provider value={{ locale, setLocale }}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): Locale {
  return useContext(LocaleContext).locale;
}

export function useSetLocale(): (locale: Locale) => void {
  return useContext(LocaleContext).setLocale;
}
