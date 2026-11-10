import type { Metadata, Viewport } from "next";
import { Barlow, Barlow_Condensed } from "next/font/google";
import { SiteHeader } from "@/components/SiteHeader";
import { THEME_SCRIPT } from "@/lib/theme";
import "./globals.css";

const barlow = Barlow({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-barlow" });
const condensed = Barlow_Condensed({ subsets: ["latin"], weight: ["600", "700"], variable: "--font-barlow-condensed" });

export const metadata: Metadata = {
  title: "Review Analyser",
  description: "What Flipkart buyers actually say about a product, with the reviews to prove it.",
};

// shortcut: the light masthead colour until ThemeSwitch hydrates and syncs it, so dark users may see a white toolbar briefly.
export const viewport: Viewport = { themeColor: "#ffffff" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // suppressHydrationWarning: THEME_SCRIPT sets data-theme before React hydrates
    <html lang="en" data-theme="light" suppressHydrationWarning className={`${barlow.variable} ${condensed.variable}`}>
      {/* suppressHydrationWarning: extensions such as Grammarly add attributes to <body> */}
      <body suppressHydrationWarning className="min-h-dvh bg-page font-sans text-ink antialiased">
        {/* Not in <head>: browser extensions inject scripts there and React would hydrate this tag against theirs */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <SiteHeader />
        {children}
      </body>
    </html>
  );
}
