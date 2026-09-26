import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TopBar } from "@/components/top-bar";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
});

const TITLE = "VERDICT ANALYST · Causal Analytics Agent";
const DESCRIPTION = "Ask anything. When you ask WHY, get a defensible answer.";
const OG_IMAGE = {
  url: "/og.png",
  width: 1200,
  height: 630,
  alt: "VERDICT ANALYST, causal analytics agent",
};

export const metadata: Metadata = {
  // Basis URL absolut untuk og:image dan og:url (domain produksi Vercel).
  metadataBase: new URL("https://agentic-verdict-sand.vercel.app"),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    url: "/",
    siteName: "VERDICT ANALYST",
    title: TITLE,
    description: DESCRIPTION,
    images: [OG_IMAGE],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: [OG_IMAGE.url],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-bg font-sans text-ink antialiased">
        <div className="flex min-h-screen flex-col">
          <TopBar />
          <main className="flex min-h-0 flex-1 flex-col">{children}</main>
        </div>
      </body>
    </html>
  );
}
