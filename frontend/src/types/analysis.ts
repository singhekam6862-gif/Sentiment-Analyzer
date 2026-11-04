// Mirror of SPEC.md §C (/api/v3). Change SPEC.md and backend/app/schemas.py together with this file.

export interface CatalogueProduct {
  id: string;
  name: string;
  category: string;
  review_count: number;
}

export type AnalysisRequest = { product_id: string } | { url: string };

export interface AnalysisJob {
  job_id: string;
  status: "queued" | "fetching" | "analysing" | "done" | "failed";
  message: string;
  result: Analysis | null;
  error: string | null;
}

export type Polarity = "praise" | "complaint" | "mixed";

export interface Quote {
  review_id: string;
  text: string;
  polarity: Polarity;
}

export interface Aspect {
  key: string;
  label: string;
  praise: number;
  complaints: number;
  mixed: number;
  confidence: "high" | "medium" | "low";
  quotes: Quote[];
}

export interface UseCase {
  name: string;
  verdict: "good" | "okay" | "poor" | "too_few";
  reason: string;
  review_count: number;
}

export interface Claim {
  text: string;
  review_ids: string[];
}

export interface Review {
  review_id: string;
  author: string;
  rating: number;
  title: string | null;
  text: string;
  review_date: string;
  verified_purchase: boolean;
  helpful_votes: number;
  group: "product" | "fulfillment" | "suspicious";
  sentiment: "positive" | "negative" | "neutral";
  aspects: string[];
  flags: string[];
}

export interface Analysis {
  product: {
    id: string;
    name: string;
    category: string;
    source_url: string | null;
    data_source: "live_scrape" | "catalogue";
    collected_on: string | null;
  };
  verdict: { headline: string; warning: string | null; generated_by: "groq" | "gemini" | "rule_based" };
  rating: { average: number; count: number; distribution: number[] };
  funnel: {
    collected: number;
    suspicious: { count: number; reason: string };
    fulfillment: { count: number; reason: string };
    analysed: number;
  };
  use_cases: UseCase[];
  aspects: Aspect[];
  pros: Claim[];
  cons: Claim[];
  reviews: Review[];
}
