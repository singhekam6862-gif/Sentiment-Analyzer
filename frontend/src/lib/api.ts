import type { AnalysisJob, AnalysisRequest, CatalogueProduct } from "@/types/analysis";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = body?.detail;
    // 422 details are a list of pydantic errors; show the first message.
    const message = typeof detail === "string" ? detail : detail?.[0]?.msg?.replace(/^Value error, /, "");
    throw new Error(message ?? `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const listProducts = () => request<CatalogueProduct[]>("/api/v3/products");

export const startAnalysis = (body: AnalysisRequest) =>
  request<AnalysisJob>("/api/v3/analyses", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const getJob = (jobId: string) => request<AnalysisJob>(`/api/v3/analyses/${encodeURIComponent(jobId)}`);
