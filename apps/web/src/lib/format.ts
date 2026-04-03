/**
 * I18N-02: Localized date and currency formatting utilities.
 *
 * Wraps the native Intl API to provide consistent, locale-aware formatting
 * across all pages. Import these helpers instead of calling Intl directly.
 */

import type { Locale } from "@/i18n/config";

// ---------------------------------------------------------------------------
// Locale → BCP 47 tag
// ---------------------------------------------------------------------------

const LOCALE_BCP47: Record<Locale, string> = {
  en: "en-US",
  ja: "ja-JP",
  de: "de-DE",
  fr: "fr-FR",
  zh: "zh-CN",
  ko: "ko-KR",
  es: "es-ES",
  pt: "pt-BR",
};

// ---------------------------------------------------------------------------
// Currency mapping per locale (reasonable defaults)
// ---------------------------------------------------------------------------

const LOCALE_CURRENCY: Record<Locale, string> = {
  en: "USD",
  ja: "JPY",
  de: "EUR",
  fr: "EUR",
  zh: "CNY",
  ko: "KRW",
  es: "EUR",
  pt: "BRL",
};

// ---------------------------------------------------------------------------
// Date formatting
// ---------------------------------------------------------------------------

/**
 * Format a Date (or ISO string) as a short localized date.
 * Example: en → "Apr 1, 2026", ja → "2026年4月1日"
 */
export function formatDate(
  value: Date | string | number,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" }
): string {
  const date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat(LOCALE_BCP47[locale] ?? "en-US", options).format(date);
}

/**
 * Format a Date (or ISO string) as a localized date-time string.
 * Example: en → "Apr 1, 2026, 10:00 AM"
 */
export function formatDateTime(
  value: Date | string | number,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }
): string {
  return formatDate(value, locale, options);
}

/**
 * Format a relative time string (e.g. "3 days ago").
 * Falls back to formatDate when Intl.RelativeTimeFormat is unavailable.
 */
export function formatRelativeTime(value: Date | string | number, locale: Locale): string {
  const date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return String(value);

  const diffMs = date.getTime() - Date.now();
  const diffSec = Math.round(diffMs / 1000);
  const diffMin = Math.round(diffSec / 60);
  const diffHour = Math.round(diffMin / 60);
  const diffDay = Math.round(diffHour / 24);

  const rtf = new Intl.RelativeTimeFormat(LOCALE_BCP47[locale] ?? "en-US", { numeric: "auto" });

  if (Math.abs(diffDay) >= 1) return rtf.format(diffDay, "day");
  if (Math.abs(diffHour) >= 1) return rtf.format(diffHour, "hour");
  if (Math.abs(diffMin) >= 1) return rtf.format(diffMin, "minute");
  return rtf.format(diffSec, "second");
}

// ---------------------------------------------------------------------------
// Currency formatting
// ---------------------------------------------------------------------------

/**
 * Format a number as a localized currency string.
 *
 * @param amount - Amount in the currency's minor unit (e.g. cents for USD, yen for JPY).
 *                 Pass the raw number; this function does NOT divide by 100.
 * @param locale - UI locale to determine currency and number format.
 * @param currencyOverride - Explicit ISO 4217 currency code (e.g. "USD") to override locale default.
 */
export function formatCurrency(
  amount: number,
  locale: Locale,
  currencyOverride?: string
): string {
  const currency = currencyOverride ?? LOCALE_CURRENCY[locale] ?? "USD";
  return new Intl.NumberFormat(LOCALE_BCP47[locale] ?? "en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 0,
    maximumFractionDigits: currency === "JPY" || currency === "KRW" ? 0 : 2,
  }).format(amount);
}

/**
 * Format a number as a localized currency string, where the input is in cents (USD/EUR/etc.)
 * or the smallest sub-unit. Divides by 100 for non-zero-decimal currencies.
 */
export function formatCurrencyFromCents(
  cents: number,
  locale: Locale,
  currencyOverride?: string
): string {
  const currency = currencyOverride ?? LOCALE_CURRENCY[locale] ?? "USD";
  // JPY and KRW have no sub-units — do not divide
  const zeroDemicalCurrencies = ["JPY", "KRW", "VND", "IDR"];
  const amount = zeroDemicalCurrencies.includes(currency) ? cents : cents / 100;
  return formatCurrency(amount, locale, currency);
}

/**
 * Format a plain number with locale-aware thousand separators.
 */
export function formatNumber(
  value: number,
  locale: Locale,
  options?: Intl.NumberFormatOptions
): string {
  return new Intl.NumberFormat(LOCALE_BCP47[locale] ?? "en-US", options).format(value);
}

/**
 * Format a percentage (0–100 scale) as a localized percentage string.
 * Example: en → "72%", de → "72 %"
 */
export function formatPercent(value: number, locale: Locale, fractionDigits = 0): string {
  return new Intl.NumberFormat(LOCALE_BCP47[locale] ?? "en-US", {
    style: "percent",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value / 100);
}
