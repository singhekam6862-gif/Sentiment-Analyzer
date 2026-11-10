"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AnalyseForm } from "@/components/AnalyseForm";
import { listProducts, listRecent } from "@/lib/api";
import { plural } from "@/lib/format";
import type { CatalogueProduct } from "@/types/analysis";

const STEPS = [
  { title: "Collect", text: "We read up to 50 reviews from the product’s Flipkart review pages." },
  { title: "Sort", text: "Suspicious reviews and delivery complaints are set aside, with the reason." },
  { title: "Count", text: "Praise and complaints are counted per feature, each linked to its reviews." },
];

export default function HomePage() {
  const [products, setProducts] = useState<CatalogueProduct[] | null>(null);
  const [recent, setRecent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Recent analyses first; the catalogue only when nothing was analysed this week.
  useEffect(() => {
    listRecent()
      .then((items) => {
        setRecent(items.length > 0);
        return items.length ? items : listProducts();
      })
      .then(setProducts, (err: Error) => setError(err.message));
  }, []);

  return (
    <main data-home className="stagger mx-auto max-w-6xl px-4 pb-20 pt-10 sm:px-6 md:pt-16">
      <h1 className="rise max-w-3xl font-display text-5xl font-bold leading-none sm:text-7xl">
        What do Flipkart buyers really think?
      </h1>
      <p className="rise mt-4 max-w-2xl text-lg text-muted">
        Paste a product link. You get what it is good for, what annoys owners, and the reviews behind every claim.
      </p>
      <div className="rise mt-8 max-w-2xl">
        <AnalyseForm large />
        <p className="mt-2 text-sm text-muted">Any flipkart.com product link. Takes about 20 seconds.</p>
      </div>

      <ol className="stagger mt-14 grid gap-4 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="rise-card lift rounded-xl border border-line bg-paper p-5 hover:border-ink">
            <p className="flex items-center gap-3 font-display text-xl font-bold uppercase tracking-wide">
              <span className="grid size-8 place-items-center rounded-full bg-ink text-base text-paper">{i + 1}</span>
              {s.title}
            </p>
            <p className="mt-2 text-muted">{s.text}</p>
          </li>
        ))}
      </ol>

      <h2 className="mt-14 font-display text-2xl font-bold uppercase tracking-wide">
        {recent ? "Recently analysed" : "Or try a product we already collected"}
      </h2>
      {error && (
        <p role="alert" className="rise mt-4 text-complaint">
          Could not load the products: {error}. Is the backend running?
        </p>
      )}
      {!products && !error && <p className="mt-4 text-muted">Loading products…</p>}
      <ul className="stagger mt-4 grid gap-4 sm:grid-cols-2 md:grid-cols-3">
        {products?.map((p) => (
          <li key={p.id} className="rise-card">
            <Link
              href={`/analysis/${p.id}`}
              className="lift flex h-full flex-col rounded-xl border border-line bg-paper p-5 hover:border-ink"
            >
              <span className="text-sm text-muted">{p.category}</span>
              <span className="mt-1 text-lg font-semibold">{p.name}</span>
              <span className="mt-auto pt-4 text-sm font-semibold">
                {plural(p.review_count, "review")} · <span className="underline underline-offset-4">See the analysis</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
