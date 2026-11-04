"use client";

import { useEffect, useRef, useState } from "react";
import type { Analysis, Aspect, Claim, Review, UseCase } from "@/types/analysis";

// Desktop follows mockup C, phones follow mockup E (SPEC/CLAUDE.md).

const VERDICT_STYLE: Record<UseCase["verdict"], { word: string; text: string; dot: string; bar: string; pips: number }> = {
  good: { word: "Good", text: "text-praise", dot: "rounded-full bg-praise", bar: "bg-praise", pips: 5 },
  okay: { word: "Okay", text: "text-muted", dot: "rounded-sm bg-muted", bar: "bg-muted", pips: 3 },
  poor: { word: "Poor", text: "text-complaint", dot: "bg-complaint", bar: "bg-complaint", pips: 1 },
  too_few: { word: "Too few reviews", text: "text-muted", dot: "rounded-full border-2 border-muted", bar: "", pips: 0 },
};

const GROUP_LABEL: Record<Review["group"], string> = {
  product: "Product reviews",
  fulfillment: "Delivery issues",
  suspicious: "Set aside",
};

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const stars = (n: number) => "★★★★★".slice(0, n) + "☆☆☆☆☆".slice(0, 5 - n);
const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function SectionTitle({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="mb-4 border-b-[3px] border-ink pb-2 font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
      {children}
    </h2>
  );
}

function VerdictBlock({ analysis }: { analysis: Analysis }) {
  const { product, verdict, rating, funnel } = analysis;
  return (
    <section aria-labelledby="product-name">
      <p className="text-sm text-muted">
        {product.category} · {product.data_source === "live_scrape" ? `Collected ${product.collected_on}` : "Flipkart reviews"}
      </p>
      <h1 id="product-name" className="mt-1 font-display text-4xl font-bold leading-none md:text-7xl">
        {product.name}
      </h1>
      <p className="mt-2 text-sm text-muted">
        <span className="font-semibold text-ink">{rating.average.toFixed(1)}★</span> · {plural(rating.count, "rating")} ·{" "}
        {funnel.analysed} product reviews analysed
      </p>
      <div className="mt-5 rounded-2xl bg-ink p-5 text-white md:rounded-none md:bg-transparent md:p-0 md:text-ink">
        <p className="mb-1 text-xs font-semibold uppercase tracking-widest text-neutral-300 md:hidden">Verdict</p>
        <p className="max-w-3xl text-xl font-semibold leading-snug md:text-2xl md:font-medium">{verdict.headline}</p>
        {verdict.warning && (
          <p className="mt-3 flex gap-2 text-base text-orange-200 md:text-complaint">
            <span aria-hidden="true">▲</span>
            {verdict.warning}
          </p>
        )}
      </div>
    </section>
  );
}

function UseCases({ items }: { items: UseCase[] }) {
  if (!items.length) return null;
  return (
    <section aria-labelledby="good-for" className="mt-12">
      <SectionTitle id="good-for">Is it good for…</SectionTitle>
      <ul className="-mx-4 flex gap-3 overflow-x-auto px-4 pb-2 md:mx-0 md:grid md:grid-cols-3 md:gap-4 md:overflow-visible md:px-0">
        {items.map((u) => {
          const s = VERDICT_STYLE[u.verdict];
          return (
            <li key={u.name} className="min-w-32 shrink-0 rounded-xl border border-line p-3 md:rounded md:p-4">
              <div className="flex flex-col gap-1 md:flex-row md:items-baseline md:justify-between md:gap-3">
                <h3 className="text-sm text-muted md:text-lg md:font-semibold md:text-ink">{u.name}</h3>
                <p className={`flex items-center gap-1.5 font-display text-lg font-bold uppercase md:text-xl ${s.text}`}>
                  <span aria-hidden="true" className={`size-3 ${s.dot}`} />
                  {s.word}
                </p>
              </div>
              <div aria-hidden="true" className="mt-2 hidden gap-0.5 md:flex">
                {[0, 1, 2, 3, 4].map((i) => (
                  <span key={i} className={`h-1.5 flex-1 ${i < s.pips ? s.bar : "bg-wash"}`} />
                ))}
              </div>
              <p className="mt-2 hidden text-[15px] md:block">{u.reason}</p>
              <p className="mt-1 hidden text-sm text-muted md:block">Based on {plural(u.review_count, "review")}</p>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function AspectRows({ aspects, onOpen }: { aspects: Aspect[]; onOpen: (a: Aspect) => void }) {
  const max = Math.max(1, ...aspects.map((a) => a.praise + a.complaints));
  return (
    <section aria-labelledby="mentions" className="min-w-0 flex-[3_1_520px]">
      <SectionTitle id="mentions">What reviewers mention</SectionTitle>
      {!aspects.length && <p className="text-muted">No product reviews mention specific features yet.</p>}
      <p className="mb-2 text-sm text-muted">
        <span className="font-semibold text-praise">▲ praise</span> ·{" "}
        <span className="font-semibold text-complaint">▼ complaints</span> · select a row to read the reviews
      </p>
      <ul className="border-t border-line">
        {aspects.map((a) => (
          <li key={a.key} className="border-b border-line">
            <button
              type="button"
              onClick={() => onOpen(a)}
              className="flex min-h-14 w-full items-center gap-3 py-2 text-left hover:bg-wash"
            >
              <span className="flex-1 font-semibold">
                {a.label}
                {a.confidence === "low" && <span className="ml-2 text-sm font-normal text-muted">few mentions</span>}
              </span>
              <span className="w-10 text-right font-semibold text-praise">{a.praise ? `▲${a.praise}` : ""}</span>
              <span className="w-10 text-right font-semibold text-complaint">{a.complaints ? `▼${a.complaints}` : ""}</span>
              <span aria-hidden="true" className="hidden h-2.5 w-[30%] md:flex">
                <span className="bg-praise" style={{ width: `${(a.praise / max) * 100}%` }} />
                <span className="bg-complaint-bar" style={{ width: `${(a.complaints / max) * 100}%` }} />
              </span>
              <span aria-hidden="true" className="text-muted">›</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Funnel({ funnel }: { funnel: Analysis["funnel"] }) {
  const pct = (n: number) => `${funnel.collected ? (n / funnel.collected) * 100 : 0}%`;
  const rows = [
    { label: "Reviews collected", n: funnel.collected, bar: "bg-ink", note: "Everything on the product's Flipkart review pages." },
    { label: "Set aside as suspicious", n: funnel.suspicious.count, bar: "bg-complaint", note: funnel.suspicious.reason },
    { label: "About delivery, not the product", n: funnel.fulfillment.count, bar: "bg-muted", note: funnel.fulfillment.reason },
    { label: "Product reviews analysed", n: funnel.analysed, bar: "bg-praise", note: "Everything on this page comes from these." },
  ];
  return (
    <section aria-labelledby="funnel" className="min-w-0 flex-[2_1_320px]">
      <SectionTitle id="funnel">How we read {plural(funnel.collected, "review")}</SectionTitle>
      <ol className="flex flex-col gap-3">
        {rows.map((r) => (
          <li key={r.label}>
            <div className="flex justify-between gap-4">
              <span>{r.label}</span>
              <span className="font-semibold">{r.n}</span>
            </div>
            <div aria-hidden="true" className="mt-1 h-5 bg-wash">
              <div className={`h-full ${r.bar}`} style={{ width: pct(r.n) }} />
            </div>
            <p className="mt-1 text-sm text-muted">{r.note}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

function ClaimList({ title, items, tone }: { title: string; items: Claim[]; tone: string }) {
  if (!items.length) return null;
  return (
    <div className="min-w-0 flex-[1_1_320px]">
      <h3 className={`mb-2 font-display text-xl font-bold uppercase ${tone}`}>{title}</h3>
      <ul className="border-t border-line">
        {items.map((c) => (
          <li key={c.text} className="flex items-baseline justify-between gap-4 border-b border-line py-3">
            <span className="text-lg">{c.text}</span>
            <span className="shrink-0 text-sm text-muted">{plural(c.review_ids.length, "review")}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReviewList({ reviews }: { reviews: Review[] }) {
  const [group, setGroup] = useState<Review["group"]>("product");
  const [all, setAll] = useState(false);
  const shown = reviews.filter((r) => r.group === group);
  return (
    <section aria-labelledby="all-reviews" className="mt-12">
      <SectionTitle id="all-reviews">The reviews</SectionTitle>
      <div role="group" aria-label="Show reviews" className="mb-2 flex flex-wrap gap-2">
        {(Object.keys(GROUP_LABEL) as Review["group"][]).map((g) => (
          <button
            key={g}
            type="button"
            aria-pressed={g === group}
            onClick={() => {
              setGroup(g);
              setAll(false);
            }}
            className={`h-11 rounded-full border px-4 font-medium ${g === group ? "border-ink bg-ink text-white" : "border-line"}`}
          >
            {GROUP_LABEL[g]} {reviews.filter((r) => r.group === g).length}
          </button>
        ))}
      </div>
      <ul className="border-t border-line">
        {(all ? shown : shown.slice(0, 6)).map((r) => (
          <li key={r.review_id} className="border-b border-line py-4">
            <p className="flex flex-wrap gap-x-3 text-sm text-muted">
              <span className="tracking-wider text-ink" aria-label={`${r.rating} out of 5 stars`}>
                {stars(r.rating)}
              </span>
              <span>{r.author}</span>
              <span>{formatDate(r.review_date)}</span>
              <span>{r.verified_purchase ? "Certified Buyer" : "Unverified"}</span>
              {r.helpful_votes > 0 && <span>{r.helpful_votes} found helpful</span>}
            </p>
            {r.title && <p className="mt-1 font-semibold">{r.title}</p>}
            <p className="mt-1 max-w-[72ch]">{r.text}</p>
          </li>
        ))}
      </ul>
      {!all && shown.length > 6 && (
        <button type="button" onClick={() => setAll(true)} className="mt-4 h-11 rounded border border-ink px-5 font-semibold">
          Show all {shown.length}
        </button>
      )}
    </section>
  );
}

function AspectSheet({ aspect, reviews, onClose }: { aspect: Aspect | null; reviews: Map<string, Review>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (aspect) ref.current?.showModal();
  }, [aspect]);
  return (
    <dialog
      ref={ref}
      aria-labelledby="sheet-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
      className="mx-0 mb-0 mt-auto max-h-[85dvh] w-full max-w-none rounded-t-2xl bg-paper p-0 text-ink md:m-auto md:max-w-xl md:rounded-xl"
    >
      {aspect && (
        <div className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="sheet-title" className="text-2xl font-bold">
                {aspect.label}
              </h2>
              <p className="text-muted">
                <span className="font-semibold text-praise">▲ {aspect.praise} praise</span> ·{" "}
                <span className="font-semibold text-complaint">▼ {plural(aspect.complaints, "complaint")}</span>
                {aspect.mixed > 0 && ` · ${aspect.mixed} mixed`}
              </p>
            </div>
            <form method="dialog">
              <button aria-label="Close" className="size-11 text-2xl leading-none">
                ×
              </button>
            </form>
          </div>
          <ul className="mt-4 flex flex-col gap-3">
            {aspect.quotes.map((q) => {
              const r = reviews.get(q.review_id);
              return (
                <li key={q.review_id} className="rounded-xl border border-line p-4">
                  <p className={`text-sm font-semibold ${q.polarity === "complaint" ? "text-complaint" : q.polarity === "praise" ? "text-praise" : "text-muted"}`}>
                    {q.polarity === "praise" ? "Praise" : q.polarity === "complaint" ? "Complaint" : "Mixed"}
                  </p>
                  <blockquote className="mt-1 text-lg">“{q.text}”</blockquote>
                  {r && (
                    <p className="mt-2 text-sm text-muted">
                      {r.author} · {r.rating}★ · {formatDate(r.review_date)}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </dialog>
  );
}

export function Report({ analysis }: { analysis: Analysis }) {
  const [open, setOpen] = useState<Aspect | null>(null);
  const byId = new Map(analysis.reviews.map((r) => [r.review_id, r]));
  return (
    <main className="mx-auto max-w-6xl px-4 pb-20 pt-8 sm:px-6 md:pt-12">
      <VerdictBlock analysis={analysis} />
      <UseCases items={analysis.use_cases} />
      <div className="mt-12 flex flex-wrap gap-12">
        <AspectRows aspects={analysis.aspects} onOpen={setOpen} />
        <Funnel funnel={analysis.funnel} />
      </div>
      {(analysis.pros.length > 0 || analysis.cons.length > 0) && (
        <section aria-labelledby="worth-knowing" className="mt-12">
          <SectionTitle id="worth-knowing">Worth knowing</SectionTitle>
          <div className="flex flex-wrap gap-x-12 gap-y-8">
            <ClaimList title="Good" items={analysis.pros} tone="text-praise" />
            <ClaimList title="Not so good" items={analysis.cons} tone="text-complaint" />
          </div>
        </section>
      )}
      <ReviewList reviews={analysis.reviews} />
      <p className="mt-12 text-sm text-muted">
        Summary written {analysis.verdict.generated_by === "rule_based" ? "by rules from the review counts" : `by ${analysis.verdict.generated_by}`}.
        Every quote is copied from a real review.
      </p>
      <AspectSheet aspect={open} reviews={byId} onClose={() => setOpen(null)} />
    </main>
  );
}
