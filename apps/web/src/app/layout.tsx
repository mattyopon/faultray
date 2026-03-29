import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "@/components/auth-provider";
import { Navbar } from "@/components/navbar";
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
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <Navbar />
          <main className="flex-1 pt-16">{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
