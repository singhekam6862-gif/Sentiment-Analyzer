"use client";

import { useState } from "react";
import { Card } from "@/components/ui";
import { formatDate, stars } from "@/lib/format";
import type { Review } from "@/types/analysis";

const GROUP_LABEL: Record<Review["group"], string> = {
  product: "Product reviews",
  fulfillment: "Delivery issues",
  suspicious: "Set aside",
};

const SENTIMENT = {
  positive: { word: "Positive", dot: "bg-praise" },
  neutral: { word: "Neutral", dot: "bg-neutral" },
  negative: { word: "Negative", dot: "bg-complaint" },
};

function ReviewItem({ r, labels }: { r: Review; labels: Map<string, string> }) {
  const s = SENTIMENT[r.sentiment];
  return (
    <li className="rise py-4">
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
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
      <p className="mt-2 flex flex-wrap gap-2 text-sm">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5">
          <span aria-hidden="true" className={`size-2 rounded-full ${s.dot}`} />
          {s.word}
        </span>
        {r.aspects.map((key) => (
          <span key={key} className="rounded-full px-2.5 py-0.5 text-muted">
            {labels.get(key) ?? key.replace(/_/g, " ")}
          </span>
        ))}
      </p>
    </li>
  );
}

export function ReviewList({ reviews, labels }: { reviews: Review[]; labels: Map<string, string> }) {
  const [group, setGroup] = useState<Review["group"]>("product");
  const [all, setAll] = useState(false);
  const shown = reviews.filter((r) => r.group === group);
  return (
    <Card id="all-reviews" title="The reviews" className="mt-6">
      <div role="group" aria-label="Show reviews" className="flex flex-wrap gap-2">
        {(Object.keys(GROUP_LABEL) as Review["group"][]).map((g) => (
          <button
            key={g}
            type="button"
            aria-pressed={g === group}
            onClick={() => {
              setGroup(g);
              setAll(false);
            }}
            className={`h-11 rounded-full border px-4 font-medium ${g === group ? "border-selected bg-selected text-on-selected" : "border-line hover:bg-wash"}`}
          >
            {GROUP_LABEL[g]} {reviews.filter((r) => r.group === g).length}
          </button>
        ))}
      </div>
      {!shown.length && <p className="mt-4 text-muted">None in this group.</p>}
      <ul className="stagger mt-2 divide-y divide-line">
        {(all ? shown : shown.slice(0, 6)).map((r) => (
          <ReviewItem key={r.review_id} r={r} labels={labels} />
        ))}
      </ul>
      {!all && shown.length > 6 && (
        <button type="button" onClick={() => setAll(true)} className="mt-4 h-11 rounded-lg border border-ink px-5 font-semibold hover:bg-wash">
          Show all {shown.length}
        </button>
      )}
    </Card>
  );
}
