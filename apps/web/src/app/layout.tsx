import type { Metadata } from "next";
import { Inter, Noto_Sans_JP, Geist_Mono } from "next/font/google";
import Script from "next/script";
import { AuthProvider } from "@/components/auth-provider";
import { Navbar } from "@/components/navbar";
import { Breadcrumb } from "@/components/breadcrumb";
import { LocaleProvider } from "@/lib/useLocale";
import { CookieConsent } from "@/components/cookie-consent";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  display: "swap",
});

const notoSansJP = Noto_Sans_JP({
  variable: "--font-noto-sans-jp",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// I18N-03: hreflang alternates for root layout
const BASE = "https://faultray.com";
const LOCALE_MAP: Record<string, string> = {
  en: `${BASE}/en`,
  ja: `${BASE}/ja`,
  de: `${BASE}/de`,
  fr: `${BASE}/fr`,
  zh: `${BASE}/zh`,
  ko: `${BASE}/ko`,
  es: `${BASE}/es`,
  pt: `${BASE}/pt`,
};

export const metadata: Metadata = {
  title: {
    default: "FaultRay — Zero-Risk Infrastructure Chaos Engineering",
    template: "%s | FaultRay",
  },
  description:
    "Prove your system's availability ceiling mathematically — without touching production. Pure simulation chaos engineering with 2,000+ scenarios.",
  keywords: [
    "chaos engineering",
    "infrastructure testing",
    "availability",
    "SRE",
    "DevOps",
    "simulation",
    "DORA compliance",
  ],
  metadataBase: new URL("https://faultray.com"),
  // HTTP-05: robots metaタグを明示的に設定
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  alternates: {
    canonical: BASE,
    languages: LOCALE_MAP,
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "32x32", type: "image/x-icon" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    title: "FaultRay — Zero-Risk Infrastructure Chaos Engineering",
    description:
      "Prove your system's availability ceiling mathematically — without touching production.",
    type: "website",
    url: "https://faultray.com",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: "FaultRay — Zero-Risk Infrastructure Chaos Engineering",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "FaultRay — Zero-Risk Infrastructure Chaos Engineering",
    description:
      "Prove your system's availability ceiling mathematically — without touching production.",
    images: ["/og-image.png"],
  },
};

// SEO-01: Enhanced structured data — WebSite + Organization + SoftwareApplication
const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "FaultRay",
    applicationCategory: "DeveloperApplication",
    operatingSystem: "Web",
    url: "https://faultray.com",
    description:
      "Pure simulation chaos engineering platform. Prove your system's availability ceiling mathematically without touching production.",
    offers: [
      { "@type": "Offer", name: "Free", price: "0", priceCurrency: "USD" },
      { "@type": "Offer", name: "Pro",  price: "299", priceCurrency: "USD", eligibleQuantity: { "@type": "QuantitativeValue", unitText: "month" } },
    ],
    featureList: [
      "100+ simulation engines",
      "DORA compliance reports",
      "AI reliability advisor",
      "N-Layer availability model",
      "AWS/GCP/Azure cloud discovery",
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "FaultRay",
    url: "https://faultray.com",
    logo: "https://faultray.com/og-image.png",
    contactPoint: { "@type": "ContactPoint", contactType: "customer support", email: "support@faultray.com" },
    sameAs: ["https://github.com/mattyopon/faultray"],
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "FaultRay",
    url: "https://faultray.com",
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: "https://faultray.com/simulate?sample={search_term_string}" },
      "query-input": "required name=search_term_string",
    },
  },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const gaId = process.env.NEXT_PUBLIC_GA_ID;
  // ANALYTICS-04: Hotjar ID — set NEXT_PUBLIC_HOTJAR_ID env var to enable heatmap/session recording
  // Validate as numeric-only to prevent XSS via env var injection
  const rawHotjarId = process.env.NEXT_PUBLIC_HOTJAR_ID;
  const hotjarId = rawHotjarId && /^\d+$/.test(rawHotjarId) ? rawHotjarId : undefined;

  // I18N-04: Detect locale from cookie/Accept-Language for html lang attribute
  // Falls back to "en" for root layout; locale-specific layouts override via their own html element
  return (
    <html
      lang="en"
      className={`${inter.variable} ${notoSansJP.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* HTTP-03: Resource hints for external domains — improve connection latency */}
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="preconnect" href="https://www.googletagmanager.com" />
        <link rel="dns-prefetch" href="https://www.googletagmanager.com" />
        <link rel="preconnect" href="https://js.stripe.com" />
        <link rel="dns-prefetch" href="//js.stripe.com" />
        {/* Structured data — JSON-LD */}
        {/* SEC-01: Escape </script> injection — replace <, >, & with Unicode escapes so an
            attacker-controlled value in jsonLd can never terminate the script tag early. */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify(jsonLd)
              .replace(/</g, "\\u003c")
              .replace(/>/g, "\\u003e")
              .replace(/&/g, "\\u0026"),
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
        {/* Google Analytics 4 — only injected when NEXT_PUBLIC_GA_ID is set and user consented */}
        {gaId && (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${gaId}`}
              strategy="afterInteractive"
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`
                (function(){
                  var consent = typeof localStorage !== 'undefined'
                    ? localStorage.getItem('faultray_cookie_consent')
                    : null;
                  if (consent !== 'accepted') return;
                  window.dataLayer = window.dataLayer || [];
                  function gtag(){dataLayer.push(arguments);}
                  gtag('js', new Date());
                  gtag('config', '${gaId}');
                })();
              `}
            </Script>
          </>
        )}
        {/* ANALYTICS-04: Hotjar — heatmap & session recording (consent-gated) */}
        {hotjarId && (
          <Script id="hotjar-init" strategy="afterInteractive">
            {`(function(){
              var consent=typeof localStorage!=='undefined'?localStorage.getItem('faultray_cookie_consent'):null;
              if(consent!=='accepted')return;
              (function(h,o,t,j,a,r){
                h.hj=h.hj||function(){(h.hj.q=h.hj.q||[]).push(arguments)};
                h._hjSettings={hjid:${hotjarId},hjsv:6};
                a=o.getElementsByTagName('head')[0];
                r=o.createElement('script');r.async=1;
                r.src=t+h._hjSettings.hjid+j+h._hjSettings.hjsv;
                a.appendChild(r);
              })(window,document,'https://static.hotjar.com/c/hotjar-','.js?sv=');
            })();`}
          </Script>
        )}
        {/* Inline script runs before React hydration — prevents layout shift */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
              var p=window.location.pathname;
              var pub=['/','/login','/pricing','/en','/ja','/de','/fr','/zh','/ko','/es','/pt',
                '/terms','/privacy','/dpa','/tokushoho','/contact','/demo','/help','/support',
                '/status','/features','/case-studies','/ringi','/changelog'];
              var isApp=!pub.some(function(s){return p===s||p.startsWith(s+'/');});
              if(isApp){
                document.body.setAttribute('data-app-page','true');
                document.documentElement.setAttribute('data-theme','dark');
              }
            })();`,
          }}
        />
        <AuthProvider>
          <LocaleProvider>
            <Navbar />
            <Breadcrumb />
            <main role="main" className="flex-1 pt-16">{children}</main>
            <CookieConsent />
          </LocaleProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
