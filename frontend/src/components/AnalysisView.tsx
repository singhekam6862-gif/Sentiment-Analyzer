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
    // Saved results expire after 7 days; a catalogue link can simply be started again.
    if (jobId.startsWith("url-")) throw err;
    return startAnalysis({ product_id: jobId });
  }
}

/** Which step the job is on, from its status and the progress message the backend writes (SPEC §C.4). */
function currentStep(job: AnalysisJob | null): number {
  if (!job || job.status === "queued" || job.status === "fetching") return 0;
  return job.message.startsWith("Writing") ? 2 : 1;
}

function Progress({ job, live }: { job: AnalysisJob | null; live: boolean }) {
  const steps = [
    live ? "Collect reviews from Flipkart" : "Load the saved reviews",
    "Find what buyers praise and complain about",
    "Write the verdict",
  ];
  const now = currentStep(job);
  return (
    <div className="rise max-w-xl rounded-xl border border-line bg-paper p-6 md:p-8">
      <h1 className="font-display text-4xl font-bold">Reading the reviews…</h1>
      <ol className="mt-6 flex flex-col gap-4">
        {steps.map((label, i) => (
          <li key={label} className="flex gap-3" aria-current={i === now ? "step" : undefined}>
            <span
              aria-hidden="true"
              className={`relative grid size-7 shrink-0 place-items-center rounded-full text-sm font-semibold transition-colors duration-200 ${
                i < now ? "bg-ink text-paper" : i === now ? "step-now border-2 border-ink" : "border border-line text-muted"
              }`}
            >
              {i < now ? <span className="pop">✓</span> : i + 1}
            </span>
            <span>
              <span className={i > now ? "text-muted" : "font-semibold"}>{label}</span>
              {i < now && <span className="sr-only"> (done)</span>}
              {i === now && (
                <span aria-live="polite" className="block text-sm text-muted">
                  <span key={job?.message} className="fade block">
                    {job?.message ?? "Starting"}
                  </span>
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
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

  // Keyed so a different product remounts the report and its scroll reveals start fresh.
  if (job?.status === "done" && job.result) return <Report key={job.job_id} analysis={job.result} />;

  const failed = error ?? (job?.status === "failed" ? job.error : null);
  return (
    <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
      {failed ? (
        <div role="alert" className="rise max-w-xl">
          <h1 className="font-display text-4xl font-bold">We couldn’t analyse this one</h1>
          <p className="mt-3 text-lg">{failed}</p>
          <Link href="/" className="mt-6 inline-block font-semibold text-praise underline">
            Browse the catalogue
          </Link>
        </div>
      ) : (
        <Progress job={job} live={jobId.startsWith("url-")} />
      )}
    </main>
  );
}
