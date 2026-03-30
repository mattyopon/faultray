"use client";

import { useState, useEffect } from "react";
import { locales, type Locale, defaultLocale } from "@/i18n/config";

export function useLocale(): Locale {
  const [locale, setLocale] = useState<Locale>(defaultLocale);

  useEffect(() => {
    const match = document.cookie.match(/NEXT_LOCALE=(\w+)/);
    if (match && locales.includes(match[1] as Locale)) {
      setLocale(match[1] as Locale);
    } else {
      setLocale(defaultLocale);
    }
  }, []);

  return locale;
}
