import type { Metadata } from "next";
import { Barlow, Barlow_Condensed } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import "./globals.css";

const barlow = Barlow({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-barlow" });
const condensed = Barlow_Condensed({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-barlow-condensed" });

export const metadata: Metadata = {
  title: "Review Analyser",
  description: "What Flipkart buyers actually say about a product, with the reviews to prove it.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${barlow.variable} ${condensed.variable}`}>
      <body className="min-h-dvh bg-paper font-sans text-ink antialiased">
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
