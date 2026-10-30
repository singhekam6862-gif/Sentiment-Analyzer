# SPEC — E-Commerce Sentiment & Review Authenticity Tool (Flipkart)

> **Status:** v0.2 (single-source) · **Owner:** Ekamjot Singh
> **Source of truth:** This file is the contract between `/backend` and `/frontend`.
> Any change to the `/api/v1/analyze` response shape MUST be made here first (see `CLAUDE.md`).

---

## A. Project Overview & Core Features

A tool that takes a product query (e.g. `realme Buds T310`), collects its **Flipkart** reviews, and returns an analysis of what buyers actually think — and how much of that feedback can be trusted. Two products can be analysed side by side.

### A.1 Single-Source Review Collection (Flipkart)
- **Flipkart is the only review source.** Its review pages are public (no login), and Indian buyers write a lot of Hinglish there.
- **Why not Amazon.in:** since late 2024 Amazon shows logged-out visitors only ~8 top reviews and puts the full review list behind a sign-in. That is too few reviews for burst/duplicate detection, and scraping behind a login is off-limits for this project.
- Every review carries `platform = "flipkart"` internally; the public contract no longer exposes a platform field.

### A.2 Overall Sentiment Polarity (with Hinglish Normalization)
- Every review is classified as **Positive**, **Negative**, or **Neutral**; the product's percentages sum to 100.
- A **Hinglish normalizer** runs before classification, mapping common Indian e-commerce slang/code-mixed phrases to sentiment-bearing English equivalents. Examples:

  | Hinglish input        | Normalized meaning     | Polarity |
  |-----------------------|------------------------|----------|
  | `paisa vasool`        | good value for money   | Positive |
  | `mast` / `ekdum mast` | excellent              | Positive |
  | `badhiya`             | very good              | Positive |
  | `bakwas`              | rubbish / useless      | Negative |
  | `bekar` / `bekaar`    | useless                | Negative |
  | `paisa barbaad`       | waste of money         | Negative |
  | `theek thaak`         | okay / average         | Neutral  |

- Preprocessing **must preserve negations** (`not`, `never`, `no`, `nahi`, `mat`) and **emojis** (see `CLAUDE.md` guardrail 4).

### A.3 Aspect-Based Sentiment Analysis (ABSA)
Scores each product across 6 electronics pillars, **0–100** (50 = neutral / no signal):

| Aspect key                | Example cue phrases                                        |
|---------------------------|------------------------------------------------------------|
| `sound_quality`           | bass, treble, clarity, audio, sound                        |
| `anc_noise_cancellation`  | ANC, noise cancellation, transparency mode, outside noise  |
| `mic_call_quality`        | mic, calls, voice, the other person can't hear             |
| `battery_life`            | battery, backup, charging, hours, case charge              |
| `comfort_build`           | fit, ear pain, comfortable, build, plastic, hinge          |
| `value_for_money`         | price, worth, paisa vasool, overpriced, budget             |

- An aspect with zero mentions scores `50` and its `summary` says there wasn't enough data.

### A.4 Authenticity / Fake Review Detection ("Trust Score")
- **Per-review** `review_trust_score` (0–100) and a **per-product** `trust_score` (0–100, the mean over reviews, weighted by helpful votes).
- Signals that lower trust:

  | Signal               | Heuristic                                                                   |
  |----------------------|-----------------------------------------------------------------------------|
  | Unverified purchase  | `verified_purchase == false` (Flipkart: no "Certified Buyer" badge)         |
  | Review burst         | ≥ 3 unverified 5★ reviews posted on the same date                            |
  | Extreme brevity      | Very short text (< 6 tokens) that is generic praise with no aspect mention  |
  | Generic phrasing     | Mostly template words ("nice product", "good", "best") with no aspect mention |
  | Duplicate text       | Near-identical text (≥ 70 % token overlap) to other reviews                  |
  | Rating/text mismatch | 5★ with strongly negative text, or 1★ with strongly positive text           |

- Reviews below `45` get `is_suspicious = true` and list their triggered `trust_flags`.

### A.5 Product vs. Seller/Logistics Separation
- Each negative review is classified as a **product** complaint (defect, performance) or a **fulfillment** complaint (late delivery, damaged box, wrong item, seller behaviour, refund issues).
- `fulfillment_complaint_rate` = fulfillment-caused negatives ÷ all negatives × 100.
- Fulfillment complaints are **excluded from ABSA scores** so they don't count against the product's own quality.

### A.6 Temporal Sentiment Drift
- Splits reviews into **initial** (Day-1 / first-impression) and **long-term** (durability) cohorts.
- Long-term cues: `after 3 months`, `after 2 weeks`, `ab kharab ho gaya`, `stopped working`, `still working`, `6 months use`.
- If long-term sentiment falls by ≥ 15 points below initial sentiment, return a `durability_warning` string; otherwise `null`.

### A.7 AI Pros & Cons Summary
- An LLM pass over non-suspicious reviews produces **exactly 3 pros** and **exactly 3 cons** (short, specific bullets), plus a one-sentence `buying_verdict`.
- **Provider chain:** providers are tried in the order given by `LLM_PROVIDERS` (default `groq,gemini`). A provider is skipped when its API key is unset. Both are called through their OpenAI-compatible chat-completions endpoints:

  | Provider | Key env var      | Model env var  | Default model        |
  |----------|------------------|----------------|----------------------|
  | `groq`   | `GROQ_API_KEY`   | `GROQ_MODEL`   | `openai/gpt-oss-20b` |
  | `gemini` | `GEMINI_API_KEY` | `GEMINI_MODEL` | `gemini-2.5-flash`   |

- If every provider is unavailable or returns an invalid answer, fall back to a deterministic summary built from the top/bottom ABSA aspects.
- `ai_summary.generated_by` reports which one produced the answer: `groq`, `gemini`, or `rule_based`.
- LLM answers are cached in `backend/app/data/cache.sqlite`, keyed by a hash of the prompt and model, so a repeated analysis spends no API quota.

### A.8 Product Comparison
- The frontend can analyse a second product and show both side by side (stats cards, overlaid ABSA radar, both summaries).
- This is done client-side with two independent `GET /api/v1/analyze` calls; the API itself always describes one product.

---

## B. Monorepo Directory Structure

```
Sentiment Analyser/
├── SPEC.md                         # This contract (source of truth)
├── CLAUDE.md                       # Operational rules for coding agents
├── backend/                        # Python 3.11+ · FastAPI · Playwright · NLP & LLM
│   ├── .env.example                # LLM keys/models template (copy to .env, gitignored)
│   ├── app/
│   │   ├── main.py                 # FastAPI app + routes
│   │   ├── schemas.py              # Pydantic models (mirror of Section C)
│   │   ├── scraper/
│   │   │   ├── flipkart.py         # Playwright scraper for Flipkart
│   │   │   ├── parser.py           # Flipkart HTML → RawReview parser
│   │   │   ├── hybrid_scraper.py   # Offline / snapshot / hybrid modes + seed loader
│   │   │   ├── fetcher.py          # Timeout + fallback wrapper (Section D)
│   │   │   └── snapshots/          # Static HTML DOM snapshots for offline parser tests
│   │   ├── nlp/
│   │   │   ├── preprocessor.py     # Hinglish normalizer (negation/emoji-safe)
│   │   │   ├── absa_engine.py      # Polarity, ABSA, logistics separation
│   │   │   ├── trust_scorer.py     # Trust Score calculator
│   │   │   ├── summarizer.py       # LLM provider chain + deterministic fallback
│   │   │   └── aggregator.py       # Pipeline orchestrator + temporal drift
│   │   └── data/
│   │       ├── seed_reviews.json   # Fallback dataset for demo safety
│   │       └── cache.sqlite        # LLM answer cache (gitignored)
│   ├── tests/                      # pytest suite
│   └── requirements.txt
└── frontend/                       # Next.js (App Router) · TypeScript · Tailwind CSS · Recharts · Lucide Icons
    ├── src/app/                    # Routes (search page + results dashboard)
    ├── src/components/             # Charts, stats cards, review list, inspector
    ├── src/lib/api.ts              # Typed fetch client
    ├── src/types/analysis.ts       # TS types mirroring Section C
    └── package.json
```

---

## C. Strict Data Contract — `GET /api/v1/analyze`

### C.1 Request

```
GET /api/v1/analyze?query=realme+buds+t310&mode=offline
```

| Param           | Type   | Required | Notes                                                      |
|-----------------|--------|----------|------------------------------------------------------------|
| `query`         | string | yes      | Product search query, 2–120 characters                     |
| `mode`          | string | no       | `hybrid` (default, live with fallback), `offline` (seed), `snapshot` (local HTML) |
| `force_refresh` | bool   | no       | Bypass the in-memory response cache                        |

### C.2 Response — JSON Schema (Draft 2020-12)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://sentiment-analyser.local/schemas/analyze-response.json",
  "title": "AnalyzeResponse",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "product_metadata",
    "review_stats",
    "aspect_scores",
    "temporal_drift",
    "ai_summary",
    "top_genuine_reviews"
  ],
  "properties": {
    "product_metadata": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "category", "image_url", "total_reviews_analyzed", "data_source"],
      "properties": {
        "name": { "type": "string" },
        "category": { "type": "string" },
        "image_url": { "type": ["string", "null"], "format": "uri" },
        "total_reviews_analyzed": { "type": "integer", "minimum": 0 },
        "data_source": { "type": "string", "enum": ["live_scrape", "cached_fallback"] }
      }
    },
    "review_stats": { "$ref": "#/$defs/ReviewStats" },
    "aspect_scores": {
      "type": "array",
      "minItems": 6,
      "maxItems": 6,
      "items": { "$ref": "#/$defs/AspectScore" }
    },
    "temporal_drift": {
      "type": "object",
      "additionalProperties": false,
      "required": ["initial_sentiment", "long_term_sentiment", "durability_warning"],
      "properties": {
        "initial_sentiment": { "type": "integer", "minimum": 0, "maximum": 100 },
        "long_term_sentiment": { "type": "integer", "minimum": 0, "maximum": 100 },
        "durability_warning": { "type": ["string", "null"] }
      }
    },
    "ai_summary": {
      "type": "object",
      "additionalProperties": false,
      "required": ["pros", "cons", "buying_verdict", "generated_by"],
      "properties": {
        "pros": { "type": "array", "items": { "type": "string" }, "minItems": 3, "maxItems": 3 },
        "cons": { "type": "array", "items": { "type": "string" }, "minItems": 3, "maxItems": 3 },
        "buying_verdict": { "type": "string" },
        "generated_by": { "type": "string", "enum": ["groq", "gemini", "rule_based"] }
      }
    },
    "top_genuine_reviews": {
      "type": "array",
      "maxItems": 5,
      "items": { "$ref": "#/$defs/GenuineReview" }
    }
  },
  "$defs": {
    "SentimentSplit": {
      "type": "object",
      "additionalProperties": false,
      "required": ["positive", "negative", "neutral"],
      "description": "Percentages; positive + negative + neutral = 100 (±0.1 rounding).",
      "properties": {
        "positive": { "type": "number", "minimum": 0, "maximum": 100 },
        "negative": { "type": "number", "minimum": 0, "maximum": 100 },
        "neutral": { "type": "number", "minimum": 0, "maximum": 100 }
      }
    },
    "ReviewStats": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "overall_rating",
        "sentiment_split",
        "trust_score",
        "verified_purchase_ratio",
        "fulfillment_complaint_rate"
      ],
      "properties": {
        "overall_rating": { "type": "number", "minimum": 0, "maximum": 5 },
        "sentiment_split": { "$ref": "#/$defs/SentimentSplit" },
        "trust_score": { "type": "integer", "minimum": 0, "maximum": 100 },
        "verified_purchase_ratio": { "type": "number", "minimum": 0, "maximum": 1 },
        "fulfillment_complaint_rate": { "type": "number", "minimum": 0, "maximum": 100 }
      }
    },
    "AspectScore": {
      "type": "object",
      "additionalProperties": false,
      "required": ["aspect", "score", "summary"],
      "properties": {
        "aspect": {
          "type": "string",
          "enum": [
            "sound_quality",
            "anc_noise_cancellation",
            "mic_call_quality",
            "battery_life",
            "comfort_build",
            "value_for_money"
          ]
        },
        "score": { "type": "integer", "minimum": 0, "maximum": 100 },
        "summary": { "type": "string" }
      }
    },
    "GenuineReview": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "review_id",
        "author",
        "rating",
        "title",
        "text",
        "review_date",
        "verified_purchase",
        "helpful_votes",
        "sentiment",
        "review_trust_score"
      ],
      "properties": {
        "review_id": { "type": "string" },
        "author": { "type": "string" },
        "rating": { "type": "integer", "minimum": 1, "maximum": 5 },
        "title": { "type": ["string", "null"] },
        "text": { "type": "string" },
        "review_date": { "type": "string", "format": "date" },
        "verified_purchase": { "type": "boolean" },
        "helpful_votes": { "type": "integer", "minimum": 0 },
        "sentiment": { "type": "string", "enum": ["positive", "negative", "neutral"] },
        "aspects_mentioned": {
          "type": "array",
          "items": { "$ref": "#/$defs/AspectScore/properties/aspect" },
          "default": []
        },
        "review_trust_score": { "type": "integer", "minimum": 0, "maximum": 100 }
      }
    }
  }
}
```

### C.3 Example Response (abridged)

```json
{
  "product_metadata": {
    "name": "realme Buds T310",
    "category": "TWS Earbuds",
    "image_url": "https://example.com/realme-buds-t310.jpg",
    "total_reviews_analyzed": 24,
    "data_source": "cached_fallback"
  },
  "review_stats": {
    "overall_rating": 3.6,
    "sentiment_split": { "positive": 58.3, "negative": 33.3, "neutral": 8.4 },
    "trust_score": 74,
    "verified_purchase_ratio": 0.79,
    "fulfillment_complaint_rate": 25.0
  },
  "aspect_scores": [
    { "aspect": "sound_quality", "score": 82, "summary": "Audio & Bass clarity received high praise from Flipkart buyers." }
  ],
  "temporal_drift": {
    "initial_sentiment": 81,
    "long_term_sentiment": 63,
    "durability_warning": "Durability Warning: Long-term buyer satisfaction drops by 18 points ..."
  },
  "ai_summary": {
    "pros": ["Strong bass for the price", "Effective ANC on commutes", "Reliable 30h+ battery with case"],
    "cons": ["Average mic in windy outdoor calls", "Case hinge durability concerns", "Touch controls occasionally misfire"],
    "buying_verdict": "A solid paisa-vasool pick for music and commuting; skip it if call quality is your priority.",
    "generated_by": "groq"
  },
  "top_genuine_reviews": [
    {
      "review_id": "fk_rt310_101",
      "author": "Rohit Kumar",
      "rating": 4,
      "title": "Paisa vasool ANC buds!",
      "text": "Paisa vasool earbuds 🔥 ANC is mast for this price, bass thoda heavy hai.",
      "review_date": "2026-08-14",
      "verified_purchase": true,
      "helpful_votes": 37,
      "sentiment": "positive",
      "aspects_mentioned": ["sound_quality", "anc_noise_cancellation", "value_for_money"],
      "review_trust_score": 92
    }
  ]
}
```

### C.4 Matching Pydantic Models (`backend/app/schemas.py`)

```python
class ReviewStats(StrictModel):
    overall_rating: float = Field(ge=0, le=5)
    sentiment_split: SentimentSplit
    trust_score: Score
    verified_purchase_ratio: float = Field(ge=0, le=1)
    fulfillment_complaint_rate: Percent


class AspectScore(StrictModel):
    aspect: AspectKey
    score: Score
    summary: str


class AISummary(StrictModel):
    pros: list[str] = Field(min_length=3, max_length=3)
    cons: list[str] = Field(min_length=3, max_length=3)
    buying_verdict: str
    generated_by: Literal["groq", "gemini", "rule_based"]


class GenuineReview(StrictModel):
    review_id: str
    author: str
    rating: int = Field(ge=1, le=5)
    title: str | None
    text: str
    review_date: date
    verified_purchase: bool
    helpful_votes: int = Field(ge=0)
    sentiment: Literal["positive", "negative", "neutral"]
    aspects_mentioned: list[AspectKey] = Field(default_factory=list)
    review_trust_score: Score


class AnalyzeResponse(StrictModel):
    product_metadata: ProductMetadata
    review_stats: ReviewStats
    aspect_scores: list[AspectScore] = Field(min_length=6, max_length=6)
    temporal_drift: TemporalDrift
    ai_summary: AISummary
    top_genuine_reviews: list[GenuineReview] = Field(max_length=5)
```

`ProductMetadata`, `SentimentSplit`, `TemporalDrift` and `AspectKey` are unchanged from v0.1; see `backend/app/schemas.py` for the full file.

### C.5 Contract Invariants
1. `aspect_scores` always contains **all 6 aspects exactly once**, in the order listed in `AspectKey`.
2. `top_genuine_reviews` excludes suspicious reviews (`review_trust_score < 45`) and is sorted by `helpful_votes` desc, then `review_trust_score` desc (may hold fewer than 5).
3. `sentiment_split` values sum to 100 (±0.1 rounding tolerance).
4. The response shape never changes; missing data yields neutral defaults (aspect score `50`), not omitted fields.
5. Errors use FastAPI's standard `{"detail": "..."}` with `422` (bad query), `404` (no reviews found for the query, live or seed), or `503` (live scrape *and* fallback both unavailable — should never happen in demo mode).

---

## D. Hybrid Scraping & Anti-Block Architecture

### D.1 The Golden Rule

> **Live scraping on Flipkart MUST ALWAYS be wrapped in a try/except with a hard timeout of max 8 seconds, and MUST gracefully fall back to `/backend/app/data/seed_reviews.json`.**
> The app must never crash during a live demo or get stuck in a CAPTCHA loop.

### D.2 Flow

```
request ──► in-memory cache hit (fresh)? ──yes──► return
                │ no
                ▼
        live Flipkart scrape (Playwright, headless)
        asyncio.wait_for(..., timeout=8.0)
                │
     ┌──────────┼───────────────────────────────┐
     │ success  │ TimeoutError / CAPTCHA / block │ any other Exception / empty
     ▼          ▼                                ▼
  analyse    log warning ──► load seed_reviews.json ──► data_source = cached_fallback
```

### D.3 Reference Wrapper (`backend/app/scraper/fetcher.py`)

```python
async def fetch_reviews(query: str) -> tuple[list[dict], str]:
    """Return (reviews, data_source). Never raises on scrape failure."""
    try:
        reviews = await asyncio.wait_for(
            scrape_flipkart(query, timeout=SCRAPE_TIMEOUT_SECONDS), timeout=SCRAPE_TIMEOUT_SECONDS
        )
        if not reviews:
            raise ScrapeBlockedError("empty result")
        return [r.model_dump() for r in reviews], "live_scrape"
    except (asyncio.TimeoutError, ScrapeBlockedError) as exc:
        logger.warning("Live scrape failed (%s); using fallback", exc)
    except Exception:
        logger.exception("Unexpected scraper error; using fallback")
    return [r.model_dump() for r in load_seed_reviews(query)], "cached_fallback"
```

### D.4 Anti-Block Rules
- **CAPTCHA detection = immediate abort.** If the page contains a robot-check marker (Flipkart's "Are you a human?", "Access to this page has been denied", or a blocked page), raise `ScrapeBlockedError`. **Never retry, solve, or bypass a CAPTCHA.**
- **No retry loops.** At most one live attempt per request.
- **Bounded crawl:** max 3 review pages, polite delay (1–2 s jitter) between pages, all inside the 8 s budget.
- **Demo mode:** env var `FORCE_FALLBACK=1` skips live scraping completely (use for presentations and CI).
- **Never scrape Amazon.** It is not a source any more (see A.1).

### D.5 `seed_reviews.json` Shape

```json
{
  "products": {
    "realme buds t310": {
      "metadata": { "name": "realme Buds T310", "category": "TWS Earbuds", "image_url": null },
      "reviews": [
        {
          "review_id": "fk_rt310_101",
          "platform": "flipkart",
          "product_query": "realme buds t310",
          "reviewer_name": "Rohit Kumar",
          "rating": 4,
          "title": "Paisa vasool ANC buds!",
          "text": "Paisa vasool earbuds 🔥 ANC is mast for this price.",
          "review_date": "2026-08-14",
          "verified_purchase": true,
          "helpful_votes": 37
        }
      ]
    }
  }
}
```
