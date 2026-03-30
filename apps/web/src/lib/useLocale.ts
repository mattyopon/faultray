"use client";

import { useState, useEffect } from "react";

export function useLocale(): "ja" | "en" {
  const [locale, setLocale] = useState<"ja" | "en">("en");

  useEffect(() => {
    const match = document.cookie.match(/NEXT_LOCALE=(\w+)/);
    if (match && match[1] === "ja") {
      setLocale("ja");
    } else {
      setLocale("en");
    }
  }, []);

  return locale;
}
