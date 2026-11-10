# SPEC — Flipkart Review Analyser

> **Status:** v3 (rebuild) · **Owner:** Ekamjot Singh
> **Source of truth:** This file is the contract between `/backend` and `/frontend`.
> Any change to the `/api/v3` request or response shapes MUST be made here first (see `CLAUDE.md`).
> v0.2 is preserved in git (commit `e108e44`); `docs/REBUILD_PLAN.md` explains why v3 exists.

---

## A. What the product does

Every screen helps answer one question: **"Should I buy this, and what will annoy me if I do?"**

Input: a product from the local catalogue, or a pasted Flipkart product link. Output: a verdict page built only from that product's Flipkart reviews.

### A.1 Rules every feature follows
1. **Every claim links to evidence.** Aspect counts, use-case verdicts and pros/cons point to the reviews behind them. Quotes are verbatim substrings of real reviews.
2. **Percentages with their counts, not opaque scores.** "Battery: 78% positive, 14 praise, 4 complaints", never "Battery 62/100". Whole numbers, 0% or 100% only when exact, and counts alone when fewer than 10 reviews sit behind the number. Percentages are computed in the frontend from the counts the API sends.
3. **Honest uncertainty.** Thin evidence is labelled (`confidence: low`, `too_few`), never hidden behind a neutral number.
4. **Any product category.** Aspects come from the reviews. A category template (e.g. TWS earbuds) only seeds names and use cases; the LLM path finds aspects for anything.

### A.2 Single source: Flipkart
- Flipkart review pages are public (no login), and Indian buyers write a lot of Hinglish there.
- Amazon.in is not a source: since late 2024 it shows logged-out visitors only ~8 top reviews and puts the rest behind a sign-in.

### A.3 Review groups (the funnel)
Every collected review lands in exactly one group:

| Group | Rule | Used for aspects / verdict? |
|---|---|---|
| `suspicious` | Trust score < 45 (signals below) | No. Shown separately with the reason. |
| `fulfillment` | Negative and about delivery, packaging, seller or refund, not the product | No. Shown separately. |
| `product` | Everything else | Yes |

Trust signals (each lowers the score): unverified purchase; same-day burst (≥ 3 unverified 5★ on one date); short generic praise with no aspect; near-duplicate text (≥ 70 % token overlap); rating/text mismatch. The UI never shows a trust *number*; it shows the funnel and the reasons.

### A.4 Sentiment and Hinglish
- Each product review is `positive`, `negative` or `neutral`.
- A Hinglish normalizer runs first (`paisa vasool` → good value, `bakwas` → rubbish, `theek thaak` → okay, …).
- Preprocessing **must preserve negations** (`not`, `never`, `no`, `nahi`, `mat`, `na`) and **emojis** (`CLAUDE.md` guardrail 4).

### A.5 Aspects (opinion units)
- For each product review, extract opinion units: `{aspect, polarity, quote}` where `quote` is the exact sentence or clause that carries the opinion.
- **LLM path** (Groq → Gemini, `LLM_PROVIDERS` order): few-shot extraction, ~20 reviews per call, JSON validated against the schema; quotes not found verbatim in the review are dropped.
- **Rule-based path** (no key, or every provider failed): category keyword lexicon + clause splitting + the Hinglish-aware clause scorer.
- Aspect counts: `praise`, `complaints`, `mixed` = number of product reviews with that polarity for the aspect (one vote per review per aspect).
- `confidence`: `high` ≥ 6 mentions, `medium` 4–5, `low` ≤ 3.
- **Grade shown per aspect** (frontend only, from the counts): Good / Average / Poor with the use-case cutoffs of §A.6, "Too few" under 2 mentions. Counts stay next to it, plus the percent positive (praise ÷ praise + complaints, the same share the grade uses, so mixed is left out) from 10 such reviews up.
- **Suggested aspect keys** for the LLM: the category template's keys, then the aspect names Flipkart itself shows as review filters on page 1 of a live scrape ("Battery", "Sound Quality" → `battery`, `sound_quality`). No extra requests.
- The LLM path asks for low reasoning effort, and a provider that fails one batch is skipped for the job's remaining batches.
- **Long-term reliability** is a built-in aspect: opinion units from reviews written after weeks/months of use (`after 3 months`, `6 months use`, `ab kharab ho gaya`, `stopped working`, …) that report a failure or degradation.

### A.6 Use-case verdicts
- Used for the rule-based verdict headline and returned by the API. The report page doesn't show them as cards, because they repeat the "What reviewers mention" rows.
- Up to 6 use cases per product (earbuds: Music, Commuting, Gym and running, Office calls, Lasting a year, Gaming). Each maps to one or more aspects.
- From the mapped opinion units: `praise_share = praise / (praise + complaints)`.
  `good` ≥ 0.75 · `okay` 0.40–0.75 · `poor` < 0.40 · `too_few` when fewer than 2 reviews mention it.
- `reason` is one short sentence; `review_count` is the number of reviews it is based on.
- **No template** (any product whose name or category doesn't match one): the LLM chain picks up to 6 use-case names, each tied to exactly one aspect with ≥ 2 mentions. It never decides the verdict; the counts above do. Answers naming an unknown aspect, or repeating an aspect or name, are dropped.
- A product with no template and no valid LLM answer returns `use_cases: []`; the rule-based headline then names aspects instead.

### A.7 Verdict, pros and cons
- `verdict.headline`: short and backed by the counts. The LLM writes one sentence of about 14 words, and an answer over 18 words is rejected ("Good for music and commuting, weak on calls."). The rule-based fallback names at most the two good and two poor use cases with the most reviews.
- `verdict.warning`: one sentence when long-term reliability has ≥ 2 complaints and no more praise than complaints; else `null`.
- Up to 3 pros and 3 cons, each with the `review_ids` it came from.
- Written by the LLM chain **from the aggregated opinion units**, not raw reviews. Deterministic fallback builds them from the top/bottom aspects. `generated_by` reports `groq`, `gemini` or `rule_based`.
- LLM answers are cached in `backend/app/data/cache.sqlite`, keyed by a hash of prompt + model. Whole finished analyses are saved there too (§C.3).

### A.8 Comparison
Not in v3.0. Planned as a separate page that aligns two analyses' aspects in one table.

---

## B. Monorepo Directory Structure

```
Sentiment Analyser/
├── SPEC.md                         # This contract (source of truth)
├── CLAUDE.md                       # Operational rules for coding agents
├── docs/REBUILD_PLAN.md            # Why v3, research, phases
├── backend/                        # Python 3.11+ · FastAPI · httpx · NLP & LLM
│   ├── app/
│   │   ├── main.py                 # FastAPI app + /api/v3 routes
│   │   ├── schemas.py              # Pydantic models (mirror of Section C)
│   │   ├── jobs.py                 # Analysis jobs (background tasks)
│   │   ├── store.py                # Saved finished analyses (SQLite, 7-day reuse)
│   │   ├── catalogue.py            # Local product catalogue (seed_reviews.json)
│   │   ├── scraper/                # Flipkart fetch + parse, snapshots for tests
│   │   ├── nlp/
│   │   │   ├── preprocessor.py     # Hinglish normalizer (negation/emoji-safe)
│   │   │   ├── absa_engine.py      # Clause sentiment, keyword aspects, logistics split
│   │   │   ├── trust_scorer.py     # Trust signals → suspicious group
│   │   │   ├── opinions.py         # Opinion units (LLM path + rule-based path)
│   │   │   ├── categories.py       # Category templates: aspect labels, use cases
│   │   │   ├── llm.py              # Provider chain (Groq → Gemini) + answer cache
│   │   │   ├── summarizer.py       # Verdict/pros/cons prompt (LLM) — rule-based fallback lives in analysis.py
│   │   │   └── analysis.py         # Pipeline orchestrator → Analysis (Section C)
│   │   └── data/seed_reviews.json  # Offline catalogue
│   ├── eval/                       # Accuracy harness: gold.jsonl + `python -m eval` (see eval/README.md)
│   └── tests/
└── frontend/                       # Next.js (App Router) · TypeScript · Tailwind CSS
    ├── src/app/                    # / (search + catalogue), /analysis/[jobId]
    ├── src/components/             # Verdict, aspects, funnel, reviews
    ├── src/lib/api.ts              # Typed fetch client + job polling
    └── src/types/analysis.ts       # TS types mirroring Section C
```

---

## C. Strict Data Contract — `/api/v3`

All responses are JSON. Errors use FastAPI's `{"detail": "..."}`.

### C.1 `GET /api/v3/products`
The offline catalogue.

```json
[{ "id": "realme-buds-t310", "name": "realme Buds T310", "category": "TWS earbuds", "review_count": 24 }]
```

### C.2 `POST /api/v3/analyses`
Body: exactly one of `product_id` (catalogue id) or `url` (a `https://www.flipkart.com/...` product link).

```json
{ "product_id": "realme-buds-t310" }
```

Returns `202` with an `AnalysisJob` (C.4). Errors: `422` (neither/both fields, a non-Flipkart URL, or a URL over 2048 characters), `404` (unknown `product_id`), `429` (the server already holds 200 jobs and none has finished).

Load limits: at most 2 live scrapes run at once (further URL jobs wait in `fetching`), and the server keeps at most 200 jobs, dropping the oldest finished one to make room.

### C.3 `GET /api/v3/analyses/{job_id}`
Returns the `AnalysisJob`. `404` when the job id is unknown, or its saved result is more than 7 days old.

Every `done` job is saved in `backend/app/data/cache.sqlite` (table `analyses`) and reused for 7 days: re-posting the same product, or opening its link after a restart, returns the saved job without scraping or calling an LLM. Running and failed jobs are not saved, nor a URL job that fell back to the catalogue (its next attempt tries Flipkart again).

### C.4 `AnalysisJob`

```json
{
  "job_id": "realme-buds-t310",
  "status": "done",
  "message": "Analysed 16 product reviews",
  "result": { "...": "Analysis (C.5), only when status is done" },
  "error": null
}
```

| Field | Type | Notes |
|---|---|---|
| `job_id` | string | Catalogue jobs use the product id; URL jobs use a hash of the link's path and `pid`, so tracking parameters don't make a new job. Re-posting the same source returns the same job. |
| `status` | `queued` \| `fetching` \| `analysing` \| `done` \| `failed` | |
| `message` | string | Human progress line for the UI ("Fetching reviews (2/5 pages)") |
| `result` | `Analysis` \| null | Non-null only when `done` |
| `error` | string \| null | Non-null only when `failed`; written for the end user |

### C.5 `Analysis`

```json
{
  "product": {
    "id": "realme-buds-t310",
    "name": "realme Buds T310",
    "category": "TWS earbuds",
    "source_url": null,
    "images": [],
    "specs": [],
    "data_source": "catalogue",
    "collected_on": null
  },
  "verdict": {
    "headline": "Good for music and commuting, weak on calls.",
    "warning": "4 owners say a part failed after 2–6 months.",
    "generated_by": "rule_based"
  },
  "rating": { "average": 3.2, "count": 24, "distribution": [6, 4, 0, 7, 7] },
  "funnel": {
    "collected": 24,
    "suspicious": { "count": 4, "reason": "Unverified 5★ burst on 15 Jul 2026 with near-identical text." },
    "fulfillment": { "count": 4, "reason": "Complaints about delivery, packaging or the seller." },
    "analysed": 16
  },
  "use_cases": [
    { "name": "Music", "verdict": "good", "reason": "Heavy, clear bass and crisp vocals.", "review_count": 8 }
  ],
  "aspects": [
    {
      "key": "sound_quality",
      "label": "Sound quality",
      "praise": 7,
      "complaints": 1,
      "mixed": 0,
      "confidence": "high",
      "quotes": [{ "review_id": "fk_rt310_001", "text": "Bass is heavy and clear!", "polarity": "praise" }]
    }
  ],
  "pros": [{ "text": "Punchy, clear sound with heavy bass", "review_ids": ["fk_rt310_001"] }],
  "cons": [{ "text": "Hinge, charging or battery fail after 2–6 months", "review_ids": ["fk_rt310_008"] }],
  "reviews": [
    {
      "review_id": "fk_rt310_001",
      "author": "Ramesh Yadav",
      "rating": 4,
      "title": "Mast sound and bass",
      "text": "Bass is heavy and clear! ...",
      "review_date": "2026-08-12",
      "verified_purchase": true,
      "helpful_votes": 42,
      "group": "product",
      "sentiment": "positive",
      "aspects": ["sound_quality", "anc_noise_cancellation", "value_for_money"],
      "flags": []
    }
  ]
}
```

| Path | Type | Constraint |
|---|---|---|
| `product.name` | string | Live scrapes: short name, at most 7 words, every word taken from Flipkart's title (LLM, else the title's first 5 words) |
| `product.images` | string[] | 0–12 `https://rukminim*.flixcart.com` product photos in Flipkart's gallery order, no videos. Falls back to the page's single `og:image`. Empty for catalogue products or when the product page gave none |
| `product.specs` | `{ name, items: { name, value }[] }[]` | Flipkart's specification table, in its groups and order, copied as listed. Empty for catalogue products or when the product page gave none |
| `product.data_source` | `live_scrape` \| `catalogue` | |
| `product.collected_on` | date \| null | Date of a live scrape |
| `verdict.generated_by` | `groq` \| `gemini` \| `rule_based` | |
| `rating.average` | number | 0–5, one decimal, over **all** collected reviews (what Flipkart shows) |
| `rating.distribution` | int[5] | Counts for 1★…5★, index 0 = 1★ |
| `use_cases[]` | 0–6 items | `verdict`: `good` \| `okay` \| `poor` \| `too_few` |
| `aspects[]` | 0–8 items | Sorted by `praise + complaints + mixed` desc; `key` is a snake_case slug; `confidence`: `high` \| `medium` \| `low` |
| `aspects[].quotes[]` | 0–4 items | `polarity`: `praise` \| `complaint` \| `mixed`; complaints first when the aspect has more complaints than praise |
| `pros`, `cons` | 0–3 items each | |
| `reviews[]` | all collected reviews | `group`: `product` \| `fulfillment` \| `suspicious`; `sentiment`: `positive` \| `negative` \| `neutral`; sorted by `helpful_votes` desc |

### C.6 Invariants
1. `funnel.analysed == funnel.collected - funnel.suspicious.count - funnel.fulfillment.count`, and the group counts in `reviews` match the funnel.
2. Every `quotes[].text` is a verbatim substring of the review with that `review_id`, and that review is in the `product` group.
3. Every id in `pros[].review_ids` / `cons[].review_ids` exists in `reviews`.
4. Aspect counts and use cases use `product` reviews only.
5. Missing data yields empty arrays or `null` per the table above, never omitted fields.

---

## D. Collecting reviews (background jobs)

### D.1 The Golden Rule
> **Live collection runs in a background job with one attempt that stops at 50 reviews, inside a hard 90-second safety budget. Any CAPTCHA, block, timeout or parse failure ends the attempt immediately. It never retries, never solves or bypasses a CAPTCHA, and never takes the API down.**

### D.2 Flow

```
POST /api/v3/analyses
   │
   ├─ product_id ──► catalogue reviews ──► analysing ──► done
   │
   └─ url ──► job running, done, or saved < 7 days ago? ──yes──► return it
                │ no
                ▼
            fetching: Flipkart review pages (≤ 50 reviews, ≤ 8 pages, 1–2 s jitter),
                      then 1 product page for title, images and specs if any review was read (≤ 90 s total)
                │
     ┌──────────┼──────────────────────────────┐
     │ ≥ 1 review│ CAPTCHA / block / timeout / 0 reviews
     ▼           ▼
  analysing   catalogue has the same product? ──yes──► analyse catalogue copy
     │           │ no
     ▼           ▼
    done       failed (error explains what happened and suggests the catalogue)
```

### D.3 Anti-block rules
- **CAPTCHA detection = immediate abort** ("Are you a human?", "Access to this page has been denied", blocked pages). Never retry, solve or bypass.
- **Plain HTTP, no browser:** one httpx client per crawl (IPv4, Chrome User-Agent). Reviews are read from the JSON Flipkart embeds in each page (`window.__INITIAL_STATE__`); the HTML card parser is the fallback when a page has none. HTTP 403/429 counts as a block.
- **No retry loops.** One live attempt per job; a failed URL job can be re-posted by the user, not automatically.
- **Bounded crawl:** stops as soon as 50 unique reviews are read (extra reviews on the last page are dropped). Max 8 review pages (`/product-reviews/…&page=N`, 10 reviews each, spare pages cover duplicates), 1–2 s jitter between pages. Stops early at the first page that adds no new reviews. The 90 s budget is only a safety net for a stalled page; a normal crawl ends at 50 reviews well before it.
- **One product page:** after a crawl that read at least one review, one request to the product page reads its title, images and specs (review pages carry none of them), same client, jitter and budget. It's skipped when the budget is nearly spent. Any failure there, a block included, costs only those details: the reviews are kept and nothing is retried.
- **`FORCE_FALLBACK=1`** disables live collection entirely (demos, CI): URL jobs go straight to the catalogue check.
- **Never scrape Amazon.**

### D.4 `seed_reviews.json` shape

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

Catalogue ids are the keys slugified (`realme buds t310` → `realme-buds-t310`).
