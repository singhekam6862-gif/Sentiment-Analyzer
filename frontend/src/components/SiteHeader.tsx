import Link from "next/link";
import { AnalyseForm } from "@/components/AnalyseForm";
import { ThemeSwitch } from "@/components/ThemeSwitch";

export function SiteHeader() {
  return (
    // See-through only over content: at the top of the page there's nothing under it, so it blurs once you scroll.
    <header className="sticky top-0 z-40 border-b border-line bg-masthead/80 text-on-masthead backdrop-blur-md backdrop-saturate-150 print:static">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-3 gap-y-3 px-4 py-3 sm:gap-x-6 sm:px-6">
        <Link href="/" className="flex items-center gap-1.5 font-display text-base font-bold uppercase tracking-wide text-brand sm:gap-2 sm:text-2xl">
          {/* Same drawing as app/icon.svg, in theme colours */}
          <svg aria-hidden="true" viewBox="0 0 32 32" className="size-6 shrink-0 sm:size-7">
            <rect width="32" height="32" rx="7" className="fill-selected" />
            <path d="M9 6h14a4 4 0 0 1 4 4v8a4 4 0 0 1-4 4h-9l-5 5v-5a4 4 0 0 1-4-4v-8a4 4 0 0 1 4-4z" className="fill-on-selected" />
            <path d="M10.5 14l4 4 7-7.5" fill="none" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="stroke-selected" />
          </svg>
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
