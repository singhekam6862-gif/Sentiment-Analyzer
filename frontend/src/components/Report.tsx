"use client";

import { useEffect, useRef, useState } from "react";
import { AspectSheet } from "@/components/AspectSheet";
import { AspectChart, FunnelBar, RatingBars, SentimentTimeline, hasTimeline, sentimentBuckets } from "@/components/charts";
import { ProductGallery } from "@/components/ProductGallery";
import { ReviewList } from "@/components/ReviewList";
import { Card, CountUp } from "@/components/ui";
import { percent, plural } from "@/lib/format";
import type { Analysis, Aspect, Claim, SpecGroup } from "@/types/analysis";

// Desktop follows mockup C, phones follow mockup E (SPEC/CLAUDE.md): the same cards, stacked on phones.

/**
 * Marks [data-reveal] cards and [data-chart] charts once they scroll into view; globals.css does the motion.
 * Fires once, never on the way back up. Charts wait until a quarter is visible, so the bars aren't missed.
 */
function useReveal() {
  const root = useRef<HTMLElement>(null);
  useEffect(() => {
    const mark: IntersectionObserverCallback = (entries, observer) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        e.target.setAttribute("data-seen", "");
        observer.unobserve(e.target);
      }
    };
    const rootMargin = "0px 0px -40px 0px"; // less than <main>'s bottom padding, so the last card always triggers
    const cards = new IntersectionObserver(mark, { rootMargin });
    const charts = new IntersectionObserver(mark, { rootMargin, threshold: 0.25 });
    root.current?.querySelectorAll("[data-reveal]").forEach((el) => cards.observe(el));
    root.current?.querySelectorAll("[data-chart]").forEach((el) => charts.observe(el));
    return () => {
      cards.disconnect();
      charts.disconnect();
    };
  }, []);
  return root;
}

function VerdictCard({ analysis }: { analysis: Analysis }) {
  const { verdict, funnel } = analysis;
  const by = verdict.generated_by === "rule_based" ? "rules from the counts" : verdict.generated_by;
  return (
    <section data-reveal aria-labelledby="verdict" className="stagger lines flex min-w-0 flex-col rounded-xl border border-verdict-line bg-verdict p-5 text-on-verdict @2xl:col-span-3">
      <h2 id="verdict" className="font-display text-xl font-bold uppercase tracking-wide md:text-2xl">Verdict</h2>
      <p className="mt-3 max-w-3xl text-pretty text-xl font-semibold leading-snug @md:text-lg @2xl:text-xl">{verdict.headline}</p>
      {verdict.warning && (
        <p className="mt-3 flex gap-2 text-base text-verdict-warn">
          <span aria-hidden="true">▲</span>
          {verdict.warning}
        </p>
      )}
      <p className="mt-auto pt-4 text-sm text-verdict-muted">
        Based on {funnel.analysed} of {plural(funnel.collected, "review")}, written by {by}.
      </p>
    </section>
  );
}

function RatingCard({ rating }: { rating: Analysis["rating"] }) {
  return (
    // Not a Card: in the hero's narrow column the heading sits beside the bars, which keeps this card short.
    <section data-reveal aria-labelledby="ratings" className="flex min-w-0 flex-col gap-4 rounded-xl border border-line bg-paper p-5 transition-colors duration-200 hover:border-muted @md:flex-row @md:items-center @md:gap-6 @2xl:col-span-2 @2xl:flex-col @2xl:items-stretch">
      <div className="shrink-0">
        <h2 id="ratings" className="font-display text-xl font-bold uppercase tracking-wide md:text-2xl">Ratings</h2>
        <p className="mt-2 flex items-baseline gap-2">
          <span className="font-display text-5xl font-bold leading-none"><CountUp value={rating.average} decimals={1} /></span>
          <span className="pop-late text-2xl" aria-hidden="true">★</span>
        </p>
        <p className="mt-1 text-sm text-muted">from {plural(rating.count, "rating")}</p>
      </div>
      <div className="min-w-0 flex-1">
        <RatingBars distribution={rating.distribution} />
      </div>
    </section>
  );
}

function StatTiles({ analysis }: { analysis: Analysis }) {
  const { funnel, reviews } = analysis;
  const product = reviews.filter((r) => r.group === "product");
  const tiles = [
    { n: funnel.analysed, of: funnel.collected, label: "analysed" },
    { n: product.filter((r) => r.sentiment === "positive").length, of: funnel.analysed, label: "positive" },
    { n: funnel.suspicious.count + funnel.fulfillment.count, of: funnel.collected, label: "set aside: suspicious or about delivery" },
    { n: reviews.filter((r) => r.verified_purchase).length, of: funnel.collected, label: "from certified buyers" },
  ];
  return (
    <ul className="stagger mt-10 grid grid-cols-2 gap-4 md:grid-cols-4 md:gap-6">
      {tiles.map((t) => {
        const share = percent(t.n, t.of);
        return (
          <li data-reveal key={t.label} className="lift rounded-xl border border-line bg-paper p-4 hover:border-ink">
            <p className="font-display text-3xl font-bold leading-none">
              {share === null ? <><CountUp value={t.n} /> of {t.of}</> : <><CountUp value={share} />%</>}
            </p>
            <p className="mt-1 text-sm font-semibold">{t.label}</p>
            {share !== null && <p className="text-sm text-muted">{t.n} of {plural(t.of, "review")}</p>}
          </li>
        );
      })}
    </ul>
  );
}

function ClaimCard({ id, title, items, tone }: { id: string; title: string; items: Claim[]; tone: string }) {
  return (
    <Card id={id} title={title}>
      {!items.length && <p className="text-muted">Nothing stood out.</p>}
      <ul data-chart className="stagger flex flex-col gap-3">
        {items.map((c) => (
          <li key={c.text} className={`chart-row border-l-4 pl-3 ${tone}`}>
            <p className="text-lg text-ink">{c.text}</p>
            <p className="text-sm text-muted">{plural(c.review_ids.length, "review")}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SpecsCard({ specs }: { specs: SpecGroup[] }) {
  return (
    <Card id="specs" title="Specifications" note="As listed on Flipkart, not checked against reviews." className="mt-6">
      {specs.map((group, i) => (
        <details key={i} open={i === 0} className="border-t border-line py-3 first:border-t-0 first:pt-0">
          <summary className="cursor-pointer font-semibold">
            {group.name} <span className="text-sm font-normal text-muted">· {group.items.length}</span>
          </summary>
          <dl className="mt-3 grid gap-x-6 gap-y-2 md:grid-cols-[14rem_minmax(0,1fr)]">
            {group.items.map((item, j) => (
              <div key={j} className="md:contents">
                <dt className="text-sm text-muted">{item.name}</dt>
                <dd className="break-words">{item.value}</dd>
              </div>
            ))}
          </dl>
        </details>
      ))}
    </Card>
  );
}

export function Report({ analysis }: { analysis: Analysis }) {
  const [open, setOpen] = useState<Aspect | null>(null);
  const byId = new Map(analysis.reviews.map((r) => [r.review_id, r]));
  const labels = new Map(analysis.aspects.map((a) => [a.key, a.label]));
  const buckets = sentimentBuckets(analysis.reviews);
  const timeline = hasTimeline(buckets);
  const { product, funnel } = analysis;
  const root = useReveal();
  return (
    <main ref={root} className="mx-auto max-w-6xl px-4 pb-20 pt-8 sm:px-6 md:pt-12">
      {/* Flat on purpose: phones read title, photo, cards. The auto column collapses when there are no photos. */}
      <div className="grid gap-y-6 hero:grid-cols-[minmax(0,1fr)_auto] hero:grid-rows-[auto_1fr]">
        <header className="rise min-w-0">
          <p className="text-sm text-muted">
            {product.category} · {product.collected_on ? `Collected ${product.collected_on}` : "Flipkart reviews"}
          </p>
          <h1 className="mt-1 font-display text-3xl font-bold capitalize leading-tight md:text-4xl">{product.name}</h1>
        </header>
        <ProductGallery images={product.images} name={product.name} />
        <div className="@container min-w-0 hero:col-start-1">
          <div className="stagger grid h-full grid-rows-[1fr_auto] gap-6 @2xl:grid-cols-5 @2xl:grid-rows-1">
            <VerdictCard analysis={analysis} />
            <RatingCard rating={analysis.rating} />
          </div>
        </div>
      </div>
      <StatTiles analysis={analysis} />
      <Card id="mentions" title="What reviewers mention" note="Bars count the reviews that praise or complain about each feature. The percentage is the share of those that praise it, leaving out mixed reviews. Select a row to read them." className="mt-8">
        <AspectChart aspects={analysis.aspects} onOpen={setOpen} />
      </Card>
      <div className="stagger mt-6 grid gap-6 md:grid-cols-2">
        <Card id="funnel" title={`How we read ${plural(funnel.collected, "review")}`} className={timeline ? "" : "md:col-span-2"}>
          <FunnelBar funnel={funnel} />
        </Card>
        {timeline && (
          <Card id="over-time" title="Sentiment over time" note="Product reviews collected. Flipkart lists the most helpful first, so this is not every review.">
            <SentimentTimeline buckets={buckets} />
          </Card>
        )}
      </div>
      <div className="stagger mt-6 grid gap-6 md:grid-cols-2">
        <ClaimCard id="pros" title="What buyers like" items={analysis.pros} tone="border-praise" />
        <ClaimCard id="cons" title="What buyers don’t like" items={analysis.cons} tone="border-complaint" />
      </div>
      {product.specs.length > 0 && <SpecsCard specs={product.specs} />}
      <ReviewList reviews={analysis.reviews} labels={labels} />
      <AspectSheet aspect={open} reviews={byId} onClose={() => setOpen(null)} />
    </main>
  );
}
