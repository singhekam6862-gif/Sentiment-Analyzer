"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { startAnalysis } from "@/lib/api";

/** The Flipkart link box. `large` is the home page hero version; the header uses the compact one. */
export function AnalyseForm({ large = false }: { large?: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = large ? "hero-url" : "header-url";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const job = await startAnalysis({ url: url.trim() });
      setUrl("");
      router.push(`/analysis/${job.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start the analysis");
    } finally {
      setBusy(false);
    }
  }

  const height = large ? "h-14 text-lg" : "h-11 text-base";
  return (
    <form onSubmit={submit} className="flex w-full flex-col">
      {/* overflow-hidden would clip an outside focus ring, so both controls draw theirs inside */}
      <div className={`flex overflow-hidden rounded-lg border-field bg-paper ${large ? "border-2" : "border"}`}>
        <label htmlFor={id} className="sr-only">
          Flipkart product link
        </label>
        <input
          id={id}
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a Flipkart product link"
          className={`${height} min-w-0 flex-1 bg-paper px-4 text-ink outline-praise -outline-offset-4 placeholder:text-muted`}
        />
        <button
          type="submit"
          disabled={busy}
          // Inset 4px so the filled button sits inside the field's border; its height is the field's minus that inset.
          className={`${large ? "h-12 px-7 text-lg" : "h-9 px-5 text-base"} m-1 shrink-0 rounded-md bg-selected font-semibold text-on-selected outline-on-selected -outline-offset-4 hover:opacity-90 disabled:opacity-60`}
        >
          {busy ? "Starting…" : "Analyse"}
        </button>
      </div>
      {error && (
        <p role="alert" className={`rise mt-2 text-sm ${large ? "text-complaint" : "text-masthead-warn"}`}>
          {error}
        </p>
      )}
    </form>
  );
}
