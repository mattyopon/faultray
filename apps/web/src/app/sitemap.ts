import type { MetadataRoute } from "next";

const BASE = "https://faultray.com";

// SEO-05: Comprehensive sitemap including all public pages
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  // Localized landing pages
  const locales = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;
  const localizedPages = locales.map((locale) => ({
    url: `${BASE}/${locale}`,
    lastModified: now,
    changeFrequency: "weekly" as const,
    priority: 1.0,
  }));

  // Core product pages
  const productPages = [
    { path: "/simulate",      priority: 0.9, changeFrequency: "weekly" as const },
    { path: "/dashboard",     priority: 0.9, changeFrequency: "weekly" as const },
    { path: "/pricing",       priority: 0.9, changeFrequency: "monthly" as const },
    { path: "/features",      priority: 0.8, changeFrequency: "monthly" as const },
    { path: "/demo",          priority: 0.8, changeFrequency: "weekly" as const },
    { path: "/case-studies",  priority: 0.8, changeFrequency: "monthly" as const },
    { path: "/dora",          priority: 0.7, changeFrequency: "monthly" as const },
    { path: "/reports",       priority: 0.7, changeFrequency: "monthly" as const },
    { path: "/onboarding",    priority: 0.7, changeFrequency: "monthly" as const },
  ].map(({ path, priority, changeFrequency }) => ({
    url: `${BASE}${path}`,
    lastModified: now,
    changeFrequency,
    priority,
  }));

  // Marketing & trust pages
  const marketingPages = [
    { path: "/contact",       priority: 0.7 },
    { path: "/ringi",         priority: 0.6 },
    { path: "/status",        priority: 0.6 },
    { path: "/support",       priority: 0.6 },
    { path: "/help",          priority: 0.6 },
  ].map(({ path, priority }) => ({
    url: `${BASE}${path}`,
    lastModified: now,
    changeFrequency: "monthly" as const,
    priority,
  }));

  // Legal pages
  const legalPages = [
    "/privacy",
    "/terms",
    "/dpa",
    "/tokushoho",
  ].map((path) => ({
    url: `${BASE}${path}`,
    lastModified: now,
    changeFrequency: "yearly" as const,
    priority: 0.3,
  }));

  return [
    // Root
    { url: BASE, lastModified: now, changeFrequency: "weekly", priority: 1.0 },
    ...localizedPages,
    ...productPages,
    ...marketingPages,
    ...legalPages,
  ];
}
