"use client";

/* eslint-disable @next/next/no-img-element -- next/image would proxy every Flipkart image through our server */
import { useState } from "react";

/** The selected photo with a strip to switch photos. A photo that fails to load drops out of both. */
export function ProductGallery({ images, name }: { images: string[]; name: string }) {
  const [failed, setFailed] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const shown = images.filter((url) => !failed.includes(url));
  if (!shown.length) return null;
  const main = selected && shown.includes(selected) ? selected : shown[0];
  const drop = (url: string) => setFailed((f) => [...f, url]);
  return (
    <div className={`rise flex w-full max-w-64 flex-col gap-1 md:max-w-sm hero:col-start-2 hero:row-span-2 hero:row-start-1 hero:ml-10 hero:max-w-none hero:flex-row hero:gap-2 ${shown.length > 1 ? "hero:w-[min(32rem,42vw)]" : "hero:w-[min(26rem,34vw)]"}`}>
      <img
        src={main}
        alt={`${name}, photo ${shown.indexOf(main) + 1} of ${shown.length}`}
        referrerPolicy="no-referrer"
        onError={() => drop(main)}
        className="aspect-square w-full min-w-0 rounded-lg bg-photo object-contain hero:w-0 hero:flex-1"
      />
      {shown.length > 1 && (
        // p-1 keeps focus rings inside the scroller. Two columns past 7, so all 12 photos show without a scrollbar on desktop.
        <ul className={`flex shrink-0 gap-1 overflow-x-auto p-1 hero:grid hero:content-start hero:overflow-visible hero:p-0 ${shown.length > 7 ? "hero:grid-cols-2" : ""}`}>
          {shown.map((url, i) => (
            <li key={url} className="shrink-0">
              <button
                type="button"
                aria-label={`Show photo ${i + 1} of ${shown.length}`}
                aria-pressed={url === main}
                onClick={() => setSelected(url)}
                className={`block overflow-hidden rounded-md border-2 ${url === main ? "border-selected" : "border-transparent hover:border-muted"}`}
              >
                <img src={url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => drop(url)} className="size-12 bg-photo object-contain hero:size-10" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
