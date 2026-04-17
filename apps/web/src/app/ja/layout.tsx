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
      "DORA 研究プロトタイプ",
    ],
    alternates: {
      canonical: `${BASE}/ja`,
      languages: Object.fromEntries(
        LOCALES.map((locale) => [locale, `${BASE}/${locale}`])
      ) as Record<string, string>,
    },
    openGraph: {
      title: "FaultRay — 本番を止めずに構造的障害リスクを事前評価（研究プロトタイプ）",
      description:
        "本番を止めずに構造的な障害リスクを事前評価する研究プロトタイプSaaS。宣言されたインフラ定義から稼働率上限を推定。",
      url: `${BASE}/ja`,
      images: [
        {
          url: "/og-image.png",
          width: 1200,
          height: 630,
          alt: "FaultRay — 本番を止めずに構造的障害リスクを事前評価（研究プロトタイプ）",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: "FaultRay — 本番を止めずに構造的障害リスクを事前評価（研究プロトタイプ）",
      description:
        "本番を止めずに構造的な障害リスクを事前評価する研究プロトタイプSaaS。宣言されたインフラ定義から稼働率上限を推定。",
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
      "本番環境を触らずに構造的な弱点を事前評価する研究プロトタイプSaaS。宣言された拓ロジからおおよそ2,000のシナリオを自動生成し、稼働率上限を推定します（結果精度はトポロジー定義の完全性に依存）。",
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "JPY" },
      { "@type": "Offer", name: "Pro", price: "45000", priceCurrency: "JPY", eligibleQuantity: { "@type": "QuantitativeValue", unitText: "month" } },
    ],
    featureList: [
      "100以上のシミュレーションエンジン（研究プロトタイプ）",
      "DORAリサーチドラフト（研究プロトタイプ、監査認証ではありません）",
      "AI信頼性アドバイザー（実験的）",
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
