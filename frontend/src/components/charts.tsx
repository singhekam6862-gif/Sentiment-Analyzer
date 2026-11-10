"use client";

// Plain CSS charts: at most 50 reviews and 8 aspects, so no chart library.
// Every chart prints its numbers (or reads them out on hover/focus), and colour is never the only cue.

import { useState } from "react";
import { CountUp, Grade, Swatch } from "@/components/ui";
import { percent, plural } from "@/lib/format";
import type { Analysis, Aspect, Review } from "@/types/analysis";

export function RatingBars({ distribution }: { distribution: number[] }) {
  const total = distribution.reduce((sum, n) => sum + n, 0);
  return (
    <ol data-chart className="stagger chart-dim flex flex-col gap-1" aria-label="Ratings by star">
      {[5, 4, 3, 2, 1].map((star) => {
        const n = distribution[star - 1];
        const share = percent(n, total);
        return (
          <li key={star} className="chart-row flex items-center gap-3 text-sm">
            <span className="w-7 shrink-0 font-semibold">{star}★</span>
            <span aria-hidden="true" className="rail h-2.5 flex-1 rounded-full bg-wash">
              <span className="bar-right block h-full rounded-full bg-data" style={{ width: `${total ? (n / total) * 100 : 0}%` }} />
            </span>
            <span className="w-10 shrink-0 text-right text-muted">
              {share === null ? <CountUp value={n} /> : <><CountUp value={share} />%</>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function Half({ n, max, side }: { n: number; max: number; side: "praise" | "complaint" }) {
  const bar = (
    <span
      className={`h-3.5 shrink-0 ${side === "praise" ? "bar-right rounded-r bg-praise" : "bar-left rounded-l bg-complaint"}`}
      style={{ width: `${(n / max) * 80}%` }}
    />
  );
  const count = <span className="text-sm font-semibold">{n ? <CountUp value={n} /> : ""}</span>;
  return side === "praise" ? (
    <span className="flex items-center gap-1.5 border-l border-muted pl-0.5">{bar}{count}</span>
  ) : (
    <span className="flex items-center justify-end gap-1.5 pr-0.5">{count}{bar}</span>
  );
}

/** Diverging bars: complaints left of the centre line, praise right. Rows open the reviews sheet. */
export function AspectChart({ aspects, onOpen }: { aspects: Aspect[]; onOpen: (a: Aspect) => void }) {
  if (!aspects.length) return <p className="text-muted">No product reviews mention specific features yet.</p>;
  const max = Math.max(1, ...aspects.map((a) => Math.max(a.praise, a.complaints)));
  const columns = "md:grid md:grid-cols-[minmax(0,15rem)_1fr] md:items-center md:gap-4";
  return (
    <div>
      <div aria-hidden="true" className={`mb-1 px-2 text-sm text-muted ${columns}`}>
        <span className="hidden md:block" />
        <span className="grid grid-cols-2">
          <span className="flex items-center justify-end gap-1.5 pr-2"><Swatch className="bg-complaint" />Complaints</span>
          <span className="flex items-center gap-1.5 pl-2">Praise<Swatch className="bg-praise" /></span>
        </span>
      </div>
      <ul data-chart className="stagger chart-dim divide-y divide-line border-y border-line">
        {aspects.map((a) => (
          <li key={a.key} className="chart-row">
            <button type="button" onClick={() => onOpen(a)} className={`no-press flex w-full flex-col gap-2 rounded-md px-2 py-3 text-left hover:bg-wash ${columns}`}>
              <span className="min-w-0">
                <span className="block font-semibold">{a.label}</span>
                <span className="flex flex-wrap items-baseline gap-x-2 text-sm text-muted">
                  <Grade aspect={a} />
                  {a.mixed > 0 && <span>{a.mixed} mixed</span>}
                  {a.confidence === "low" && <span>few mentions</span>}
                </span>
              </span>
              <span aria-hidden="true" className="grid grid-cols-2">
                <Half n={a.complaints} max={max} side="complaint" />
                <Half n={a.praise} max={max} side="praise" />
              </span>
              <span className="sr-only">
                {plural(a.praise, "praise")}, {plural(a.complaints, "complaint")}. Open the reviews.
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FunnelBar({ funnel }: { funnel: Analysis["funnel"] }) {
  const parts = [
    { label: "Product reviews analysed", n: funnel.analysed, fill: "bg-data", note: "Everything on this page comes from these." },
    { label: "Set aside as suspicious", n: funnel.suspicious.count, fill: "bg-complaint", note: funnel.suspicious.reason },
    { label: "About delivery, not the product", n: funnel.fulfillment.count, fill: "bg-neutral", note: funnel.fulfillment.reason },
  ].map((p) => ({ ...p, share: percent(p.n, funnel.collected) }));
  const [hot, setHot] = useState<string | null>(null); // legend row under the pointer lights its segment
  return (
    <div data-chart>
      <div aria-hidden="true" className="grow-right flex h-3 gap-0.5 overflow-hidden rounded-full">
        {parts.filter((p) => p.n > 0).map((p) => (
          <span key={p.label} className={`${p.fill} transition-opacity duration-200 ${hot && hot !== p.label ? "opacity-30" : ""}`} style={{ flexGrow: p.n }} />
        ))}
      </div>
      <ul className="stagger chart-dim mt-4 flex flex-col gap-3">
        {parts.map((p) => (
          <li key={p.label} onMouseEnter={() => setHot(p.label)} onMouseLeave={() => setHot(null)} className="chart-row flex gap-3">
            <Swatch className={`mt-1.5 ${p.fill}`} />
            <span className="min-w-0 flex-1">
              <span className="flex justify-between gap-4">
                <span>{p.label}</span>
                <span className="shrink-0 font-semibold">
                  {p.share === null ? (
                    <CountUp value={p.n} />
                  ) : (
                    <><CountUp value={p.share} />% <span className="font-normal text-muted">· {p.n}</span></>
                  )}
                </span>
              </span>
              <span className="block text-sm text-muted">{p.note}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

type Bucket = { label: string; positive: number; neutral: number; negative: number };
const SENTIMENTS = [
  { key: "negative", label: "Negative", fill: "bg-complaint" },
  { key: "neutral", label: "Neutral", fill: "bg-neutral" },
  { key: "positive", label: "Positive", fill: "bg-praise" },
] as const;

/** Continuous months (≤ 18), quarters (≤ 48 months) or years from the first review to the last. */
export function sentimentBuckets(reviews: Review[]): Bucket[] {
  const dated = reviews.filter((r) => r.group === "product" && /^\d{4}-\d{2}/.test(r.review_date));
  if (!dated.length) return [];
  const index = (iso: string) => Number(iso.slice(0, 4)) * 12 + Number(iso.slice(5, 7)) - 1;
  const months = dated.map((r) => index(r.review_date));
  const first = Math.min(...months);
  const span = Math.max(...months) - first + 1;
  const size = span <= 18 ? 1 : span <= 48 ? 3 : 12;
  const start = first - (first % size);
  const buckets: Bucket[] = [];
  for (let m = start; m <= Math.max(...months); m += size) {
    const year = Math.floor(m / 12);
    const label =
      size === 1
        ? new Date(year, m % 12).toLocaleDateString("en-IN", { month: "short", year: "2-digit" })
        : size === 3
          ? `Q${Math.floor((m % 12) / 3) + 1} ’${String(year).slice(2)}`
          : String(year);
    buckets.push({ label, positive: 0, neutral: 0, negative: 0 });
  }
  dated.forEach((r) => buckets[Math.floor((index(r.review_date) - start) / size)][r.sentiment]++);
  return buckets;
}

const total = (b: Bucket) => b.positive + b.neutral + b.negative;

/** Shown only when at least 3 periods hold 3+ reviews each; otherwise the trend would be noise. */
export function hasTimeline(buckets: Bucket[]) {
  return buckets.filter((b) => total(b) >= 3).length >= 3;
}

export function SentimentTimeline({ buckets }: { buckets: Bucket[] }) {
  const [active, setActive] = useState<number | null>(null);
  const max = Math.max(1, ...buckets.map(total));
  const shown = active === null ? null : buckets[active];
  const ticks = new Set([0, Math.floor((buckets.length - 1) / 2), buckets.length - 1]);
  return (
    <div>
      <ul aria-hidden="true" className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {[...SENTIMENTS].reverse().map((s) => (
          <li key={s.key} className="flex items-center gap-1.5"><Swatch className={s.fill} />{s.label}</li>
        ))}
      </ul>
      <p aria-live="polite" className="mt-2 min-h-6 text-sm">
        {shown
          ? `${shown.label}: ${shown.positive} positive, ${shown.neutral} neutral, ${shown.negative} negative`
          : <span className="text-muted">Point at or tab to a bar to read its counts.</span>}
      </p>
      <div data-chart className="chart-dim mt-2 flex h-40 items-end gap-0.5 border-b border-muted" onMouseLeave={() => setActive(null)}>
        {buckets.map((b, i) => (
          <button
            key={b.label}
            type="button"
            aria-label={`${b.label}: ${b.positive} positive, ${b.neutral} neutral, ${b.negative} negative`}
            onMouseEnter={() => setActive(i)}
            onFocus={() => setActive(i)}
            onBlur={() => setActive(null)}
            className={`no-press flex h-full min-w-0 flex-1 flex-col justify-end rounded-t ${active === i ? "bg-wash" : ""}`}
          >
            <span className="bar-up flex flex-col gap-0.5 overflow-hidden rounded-t" style={{ height: `${(total(b) / max) * 100}%`, animationDelay: `${i * 40}ms` }}>
              {SENTIMENTS.map((s) => b[s.key] > 0 && <span key={s.key} className={s.fill} style={{ flexGrow: b[s.key] }} />)}
            </span>
          </button>
        ))}
      </div>
      <div aria-hidden="true" className="mt-1 flex justify-between gap-2 text-xs text-muted">
        {[...ticks].map((i) => (
          <span key={i}>{buckets[i].label}</span>
        ))}
      </div>
    </div>
  );
}
