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
    <div className="w-full max-w-64 shrink-0 md:w-72 md:max-w-none">
      <img
        src={main}
        alt={`${name}, photo ${shown.indexOf(main) + 1} of ${shown.length}`}
        referrerPolicy="no-referrer"
        onError={() => drop(main)}
        className="aspect-square w-full rounded-lg border border-line bg-photo object-contain"
      />
      {shown.length > 1 && (
        <ul className="mt-2 flex gap-2 overflow-x-auto pb-1">
          {shown.map((url, i) => (
            <li key={url} className="shrink-0">
              <button
                type="button"
                aria-label={`Show photo ${i + 1} of ${shown.length}`}
                aria-pressed={url === main}
                onClick={() => setSelected(url)}
                className={`block overflow-hidden rounded-md border-2 ${url === main ? "border-ink" : "border-line hover:border-muted"}`}
              >
                <img src={url} alt="" referrerPolicy="no-referrer" loading="lazy" onError={() => drop(url)} className="size-12 bg-photo object-contain" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
