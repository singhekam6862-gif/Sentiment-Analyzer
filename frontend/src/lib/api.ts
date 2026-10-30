import type {
  AnalyzeResponse,
  InspectReviewRequest,
  InspectReviewResponse,
  ProductSuggestion,
} from "@/types/analysis";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`
    );
  }
  return res.json() as Promise<T>;
}

export const analyzeProduct = (query: string, mode: "hybrid" | "offline" = "hybrid") =>
  request<AnalyzeResponse>(
    `/api/v1/analyze?query=${encodeURIComponent(query)}&mode=${mode}`
  );

export const fetchSuggestions = () =>
  request<ProductSuggestion[]>("/api/v1/products/suggestions");

export const inspectSingleReview = (payload: InspectReviewRequest) =>
  request<InspectReviewResponse>("/api/v1/inspect-review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
