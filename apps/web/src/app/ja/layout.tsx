import { getDictionary } from "@/i18n/get-dictionary";
import type { Metadata } from "next";

const BASE = "https://faultray.com";

// I18N-03: hreflang alternates for all supported locales
const LOCALES = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"] as const;

export async function generateMetadata(): Promise<Metadata> {
  const dict = await getDictionary("ja");
  return {
    title: dict.metadata.title,
    description: dict.metadata.description,
    keywords: [
      "障害リスク診断",
      "インフラ診断",
      "可用性テスト",
      "SRE",
      "DevOps",
      "シミュレーション",
      "DORA コンプライアンス",
    ],
    alternates: {
      canonical: `${BASE}/ja`,
      languages: Object.fromEntries(
        LOCALES.map((locale) => [locale, `${BASE}/${locale}`])
      ) as Record<string, string>,
    },
    openGraph: {
      title: "FaultRay — 本番環境を壊さずシステムの弱点を自動診断",
      description:
        "本番を止めずにシステムの弱点を発見し、稼働率の上限を数学的に証明するSaaS。",
      url: `${BASE}/ja`,
      images: [
        {
          url: "/og-image.png",
          width: 1200,
          height: 630,
          alt: "FaultRay — 本番環境を壊さずシステムの弱点を自動診断",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "FaultRay — 本番環境を壊さずシステムの弱点を自動診断",
      description:
        "本番を止めずにシステムの弱点を発見し、稼働率の上限を数学的に証明するSaaS。",
      images: ["/og-image.png"],
    },
  };
}

// JSON-LD for /ja — JPY pricing (overrides root layout's USD version for Google)
const jaJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "FaultRay",
    applicationCategory: "DeveloperApplication",
    operatingSystem: "Web",
    url: "https://faultray.com/ja",
    inLanguage: "ja",
    description:
      "本番環境を触らずにシステムの弱点を自動発見。2,000以上のシナリオでシステムの稼働率上限を数学的に証明するSaaS。",
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "JPY" },
      { "@type": "Offer", name: "Pro", price: "45000", priceCurrency: "JPY", eligibleQuantity: { "@type": "QuantitativeValue", unitText: "month" } },
    ],
    featureList: [
      "100以上のシミュレーションエンジン",
      "DORAコンプライアンスレポート",
      "AI信頼性アドバイザー",
      "N-Layer可用性モデル",
      "AWS/GCP/Azureクラウドディスカバリー",
    ],
  },
];

export default function JaLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div lang="ja">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jaJsonLd)
            .replace(/</g, "\\u003c")
            .replace(/>/g, "\\u003e")
            .replace(/&/g, "\\u0026"),
        }}
      />
      {children}
    </div>
  );
}
