import { landingMetadata } from "@/i18n/landing-metadata";

export function generateMetadata() {
  return landingMetadata("en");
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
      "Research-prototype pre-deployment resilience simulation platform. Estimates structural availability limits from declared infrastructure topology; complements runtime chaos engineering.",
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "USD" },
      { "@type": "Offer", name: "Pro", price: "299", priceCurrency: "USD", eligibleQuantity: { "@type": "QuantitativeValue", unitText: "month" } },
    ],
    featureList: [
      "Multiple simulation engines (Cascade, Dynamic, Ops, What-If, Capacity — research prototype)",
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
