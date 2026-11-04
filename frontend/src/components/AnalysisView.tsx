"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Report } from "@/components/Report";
import { getJob, startAnalysis } from "@/lib/api";
import type { AnalysisJob } from "@/types/analysis";

const POLL_MS = 1000;

async function loadJob(jobId: string): Promise<AnalysisJob> {
  try {
    return await getJob(jobId);
  } catch (err) {
    // Jobs live in backend memory; a catalogue link can simply be started again.
    if (jobId.startsWith("url-")) throw err;
    return startAnalysis({ product_id: jobId });
  }
}

export function AnalysisView() {
  const { jobId } = useParams<{ jobId: string }>();
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const tick = () =>
      loadJob(jobId).then(
        (next) => {
          if (stopped) return;
          setJob(next);
          if (next.status !== "done" && next.status !== "failed") timer = setTimeout(tick, POLL_MS);
        },
        (err: Error) => !stopped && setError(err.message),
      );
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  if (job?.status === "done" && job.result) return <Report analysis={job.result} />;

  const failed = error ?? (job?.status === "failed" ? job.error : null);
  return (
    <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      {failed ? (
        <div role="alert" className="max-w-xl">
          <h1 className="font-display text-4xl font-bold">We couldn’t analyse this one</h1>
          <p className="mt-3 text-lg">{failed}</p>
          <Link href="/" className="mt-6 inline-block font-semibold text-praise underline">
            Browse the catalogue
          </Link>
        </div>
      ) : (
        <div aria-live="polite" className="max-w-xl">
          <h1 className="font-display text-4xl font-bold">Reading the reviews…</h1>
          <p className="mt-3 text-lg text-muted">{job?.message ?? "Starting"}</p>
          <div className="mt-6 h-1.5 overflow-hidden bg-wash" aria-hidden="true">
            <div className="h-full w-1/3 animate-pulse bg-ink" />
          </div>
        </div>
      )}
    </main>
  );
}
