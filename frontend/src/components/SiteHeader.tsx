"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { startAnalysis } from "@/lib/api";

export function SiteHeader() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  return (
    <header className="bg-ink text-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="font-display text-2xl font-bold uppercase tracking-wide">
          Review Analyser
        </Link>
        <form onSubmit={submit} className="ml-auto flex w-full max-w-xl flex-col sm:w-auto sm:flex-1">
          <div className="flex">
            <label htmlFor="flipkart-url" className="sr-only">
              Flipkart product link
            </label>
            <input
              id="flipkart-url"
              type="url"
              required
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste a Flipkart product link"
              className="h-11 min-w-0 flex-1 rounded-l bg-white px-3 text-base text-ink placeholder:text-muted"
            />
            <button
              type="submit"
              disabled={busy}
              className="h-11 rounded-r bg-accent px-5 font-semibold text-ink disabled:opacity-60"
            >
              {busy ? "Starting…" : "Analyse"}
            </button>
          </div>
          {error && (
            <p role="alert" className="mt-1 text-sm text-amber-200">
              {error}
            </p>
          )}
        </form>
      </div>
    </header>
  );
}
