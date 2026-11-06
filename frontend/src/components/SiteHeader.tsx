import Link from "next/link";
import { AnalyseForm } from "@/components/AnalyseForm";
import { ThemeSwitch } from "@/components/ThemeSwitch";

export function SiteHeader() {
  return (
    <header className="border-b border-line bg-masthead text-on-masthead [--color-focus:var(--color-accent)]">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-3 px-4 py-3 sm:gap-x-6 sm:px-6">
        <Link href="/" className="font-display text-xl font-bold uppercase tracking-wide sm:text-2xl">
          Review Analyser
        </Link>
        {/* Hidden on the home page, which has the large link box ([data-home]); CSS, so the layout stays static. */}
        <div className="order-last w-full sm:order-none sm:w-auto sm:max-w-xl sm:flex-1 [body:has([data-home])_&]:hidden">
          <AnalyseForm />
        </div>
        <div className="ml-auto">
          <ThemeSwitch />
        </div>
      </div>
    </header>
  );
}
