import "server-only";
import { defaultLocale, isValidLocale, type Locale } from "./config";

const dictionaries = {
  en: () => import("./dictionaries/en.json").then((m) => m.default),
  ja: () => import("./dictionaries/ja.json").then((m) => m.default),
  de: () => import("./dictionaries/de.json").then((m) => m.default),
  fr: () => import("./dictionaries/fr.json").then((m) => m.default),
  zh: () => import("./dictionaries/zh.json").then((m) => m.default),
  ko: () => import("./dictionaries/ko.json").then((m) => m.default),
  es: () => import("./dictionaries/es.json").then((m) => m.default),
  pt: () => import("./dictionaries/pt.json").then((m) => m.default),
};

export const getDictionary = async (locale: Locale) => {
  // The `Locale` type is not enforced at runtime; if an invalid value reaches
  // here (e.g. via a future dynamic route segment) `dictionaries[locale]` is
  // undefined and calling it throws an opaque "is not a function". Fall back to
  // the default locale's loader instead of crashing with a 500.
  const loader = dictionaries[isValidLocale(locale) ? locale : defaultLocale];
  return loader();
};
export type Dictionary = Awaited<ReturnType<typeof getDictionary>>;
