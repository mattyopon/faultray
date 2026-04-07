import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

const BASE = "https://faultray.com";

// I18N-03: hreflang alternates for all supported locales
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("en");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
    alternates: {
      canonical: `${BASE}/en`,
      languages: Object.fromEntries(
        LOCALES.map((locale) => [locale, `${BASE}/${locale}`])
      ) as Record<string, string>,
    },
  };
}

// JSON-LD for /en — USD pricing
const enJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "FaultRay",
    applicationCategory: "DeveloperApplication",
    operatingSystem: "Web",
    url: "https://faultray.com/en",
    inLanguage: "en",
    description:
      "Pure simulation chaos engineering platform. Prove your system's availability ceiling mathematically without touching production.",
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "USD" },
      { "@type": "Offer", name: "Pro", price: "299", priceCurrency: "USD", eligibleQuantity: { "@type": "QuantitativeValue", unitText: "month" } },
    ],
    featureList: [
      "100+ simulation engines (research prototype)",
      "DORA-aligned evidence drafts (research prototype, not audit-certified)",
      "AI reliability advisor (experimental)",
      "N-Layer availability model",
      "AWS/GCP/Azure cloud discovery",
    ],
  },
];

export default function EnLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div lang="en">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(enJsonLd)
            .replace(/</g, "\\u003c")
            .replace(/>/g, "\\u003e")
            .replace(/&/g, "\\u0026"),
        }}
      />
      {children}
    </div>
  );
}
