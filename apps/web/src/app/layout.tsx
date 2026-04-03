import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import { AuthProvider } from "@/components/auth-provider";
import { Navbar } from "@/components/navbar";
import { LocaleProvider } from "@/lib/useLocale";
import { CookieConsent } from "@/components/cookie-consent";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

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

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "FaultRay",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Web",
  url: "https://faultray.com",
  description:
    "Pure simulation chaos engineering platform. Prove your system's availability ceiling mathematically without touching production.",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const gaId = process.env.NEXT_PUBLIC_GA_ID;

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        {/* Structured data — JSON-LD */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
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
        {/* Inline script runs before React hydration — prevents layout shift */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){
              var p=window.location.pathname;
              var skip=['/','/login','/pricing','/en','/ja','/de','/fr','/zh','/ko','/es','/pt'];
              var isApp=!skip.some(function(s){return p===s||p.startsWith(s+'/');});
              if(isApp)document.body.setAttribute('data-app-page','true');
            })();`,
          }}
        />
        <AuthProvider>
          <LocaleProvider>
            <Navbar />
            <main role="main" className="flex-1 pt-16">{children}</main>
            <CookieConsent />
          </LocaleProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
