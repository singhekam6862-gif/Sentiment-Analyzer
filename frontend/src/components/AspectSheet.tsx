"use client";

import { useEffect, useRef, useState } from "react";
import { Grade } from "@/components/ui";
import { formatDate, plural } from "@/lib/format";
import type { Aspect, Review } from "@/types/analysis";

const POLARITY = {
  praise: { word: "Praise", text: "text-praise" },
  complaint: { word: "Complaint", text: "text-complaint" },
  mixed: { word: "Mixed", text: "text-muted" },
};

/** Bottom sheet on phones (mockup E), centred dialog on desktop: the quotes behind one aspect. */
export function AspectSheet({ aspect: selected, reviews, onClose }: { aspect: Aspect | null; reviews: Map<string, Review>; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  // Keeps the last aspect after closing, so the sheet isn't empty while it animates out.
  const [aspect, setAspect] = useState(selected);
  if (selected && selected !== aspect) setAspect(selected);
  useEffect(() => {
    if (selected) ref.current?.showModal();
  }, [selected]);
  return (
    <dialog
      ref={ref}
      aria-labelledby="sheet-title"
      onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()}
      className="mx-0 mb-0 mt-auto max-h-[85dvh] w-full max-w-none rounded-t-2xl border border-line bg-paper p-0 text-ink md:m-auto md:max-w-xl md:rounded-xl"
    >
      {aspect && (
        <div className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 id="sheet-title" className="text-2xl font-bold">
                {aspect.label}
              </h2>
              <Grade aspect={aspect} />
              <p className="text-muted">
                <span className="font-semibold text-praise">▲ {aspect.praise} praise</span> ·{" "}
                <span className="font-semibold text-complaint">▼ {plural(aspect.complaints, "complaint")}</span>
                {aspect.mixed > 0 && ` · ${aspect.mixed} mixed`}
              </p>
            </div>
            <form method="dialog">
              <button aria-label="Close" className="size-11 rounded-full text-2xl leading-none hover:bg-wash">
                ×
              </button>
            </form>
          </div>
          <ul className="mt-4 flex flex-col gap-3">
            {aspect.quotes.map((q) => {
              const r = reviews.get(q.review_id);
              return (
                <li key={q.review_id} className="rounded-xl border border-line p-4">
                  <p className={`text-sm font-semibold ${POLARITY[q.polarity].text}`}>{POLARITY[q.polarity].word}</p>
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
