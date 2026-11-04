"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listProducts } from "@/lib/api";
import type { CatalogueProduct } from "@/types/analysis";

export default function HomePage() {
  const [products, setProducts] = useState<CatalogueProduct[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listProducts().then(setProducts, (err: Error) => setError(err.message));
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-4 pb-20 pt-10 sm:px-6">
      <h1 className="max-w-3xl font-display text-5xl font-bold leading-none sm:text-7xl">
        What do Flipkart buyers really think?
      </h1>
      <p className="mt-4 max-w-2xl text-lg text-muted">
        Paste a product link above. We read its reviews, set aside the suspicious ones and the delivery complaints, and
        tell you what the product is good for, with the reviews to prove it.
      </p>

      <h2 className="mt-12 border-b-[3px] border-ink pb-2 font-display text-2xl font-bold uppercase tracking-wide">
        Or pick a product we already collected
      </h2>
      {error && (
        <p role="alert" className="mt-4 text-complaint">
          Could not load the catalogue: {error}. Is the backend running?
        </p>
      )}
      {!products && !error && <p className="mt-4 text-muted">Loading products…</p>}
      <ul className="divide-y divide-line">
        {products?.map((p) => (
          <li key={p.id}>
            <Link
              href={`/analysis/${p.id}`}
              className="flex min-h-14 flex-wrap items-baseline justify-between gap-x-6 py-4 hover:bg-wash"
            >
              <span className="text-lg font-semibold">{p.name}</span>
              <span className="text-sm text-muted">
                {p.category} · {p.review_count} reviews
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
