import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Script from "next/script";
import { AuthProvider } from "@/components/auth-provider";
import { Navbar } from "@/components/navbar";
import { LocaleProvider } from "@/lib/useLocale";
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
  openGraph: {
    title: "FaultRay — Zero-Risk Infrastructure Chaos Engineering",
    description:
      "Prove your system's availability ceiling mathematically — without touching production.",
    type: "website",
    url: "https://faultray.com",
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
      <body className="min-h-full flex flex-col">
        {/* Google Analytics 4 — only injected when NEXT_PUBLIC_GA_ID is set */}
        {gaId && (
          <>
            <Script
              src={`https://www.googletagmanager.com/gtag/js?id=${gaId}`}
              strategy="afterInteractive"
            />
            <Script id="ga4-init" strategy="afterInteractive">
              {`
                window.dataLayer = window.dataLayer || [];
                function gtag(){dataLayer.push(arguments);}
                gtag('js', new Date());
                gtag('config', '${gaId}');
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
            <main className="flex-1 pt-16">{children}</main>
          </LocaleProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
