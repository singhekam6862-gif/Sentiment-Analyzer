"use client";

import { useEffect, useRef } from "react";
import { percent } from "@/lib/format";
import type { Aspect, UseCase } from "@/types/analysis";

/**
 * Counts up to `value` when scrolled into view. The real number stays in the DOM until then,
 * so printing, reduced motion and a failed observer all show the true count.
 */
export function CountUp({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const final = value.toFixed(decimals);
  useEffect(() => {
    const el = ref.current;
    const text = el?.firstChild; // the text node React owns: replacing it would break later updates
    if (!el || !text || !value || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      const start = performance.now();
      const tick = (now: number) => {
        const p = Math.min((now - start) / 800, 1);
        text.nodeValue = (value * (1 - (1 - p) ** 3)).toFixed(decimals);
        if (p < 1) frame = requestAnimationFrame(tick);
      };
      tick(start);
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      text.nodeValue = final;
    };
  }, [value, decimals, final]);
  return <span ref={ref}>{final}</span>;
}

export const VERDICT_STYLE: Record<UseCase["verdict"], { word: string; text: string; dot: string }> = {
  good: { word: "Good", text: "text-praise", dot: "rounded-full bg-praise" },
  okay: { word: "Average", text: "text-muted", dot: "rounded-sm bg-neutral" },
  poor: { word: "Poor", text: "text-complaint", dot: "bg-complaint" },
  too_few: { word: "Too few reviews", text: "text-muted", dot: "rounded-full border-2 border-muted" },
};

// Same cutoffs as the use-case verdicts (SPEC §A.6), from the counts the API already sends.
export function aspectGrade(a: Aspect): UseCase["verdict"] {
  if (a.praise + a.complaints + a.mixed < 2 || a.praise + a.complaints === 0) return "too_few";
  const share = a.praise / (a.praise + a.complaints);
  return share >= 0.75 ? "good" : share >= 0.4 ? "okay" : "poor";
}

export function Grade({ aspect }: { aspect: Aspect }) {
  const grade = aspectGrade(aspect);
  if (grade === "too_few") return <span className="text-sm text-muted">Too few</span>;
  const s = VERDICT_STYLE[grade];
  const share = percent(aspect.praise, aspect.praise + aspect.complaints);
  return (
    <span className={`inline-flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide ${s.text}`}>
      <span aria-hidden="true" className={`size-2.5 ${s.dot}`} />
      {s.word}
      {share !== null && <span className="font-normal normal-case tracking-normal">· {share}% positive</span>}
    </span>
  );
}

export function Card({
  id,
  title,
  note,
  className = "",
  children,
}: {
  id: string;
  title: string;
  note?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section data-reveal aria-labelledby={id} className={`min-w-0 rounded-xl border border-line bg-paper p-5 transition-colors duration-200 hover:border-muted md:p-6 ${className}`}>
      <h2 id={id} className="font-display text-xl font-bold uppercase tracking-wide md:text-2xl">
        {title}
      </h2>
      {note && <p className="mt-1 text-sm text-muted">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

/** Colour swatch for legends: identity is never colour alone, the label sits next to it. */
export function Swatch({ className }: { className: string }) {
  return <span aria-hidden="true" className={`inline-block size-3 shrink-0 rounded-sm ${className}`} />;
}
