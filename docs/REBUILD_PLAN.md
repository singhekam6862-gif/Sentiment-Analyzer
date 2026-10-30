# Rebuild Plan: Flipkart Review Analyser, from scratch

> Status: proposal (2026-10-29). Nothing here is built yet. Several steps change rules in
> `SPEC.md` and `CLAUDE.md`, and those files must be updated first, before any code.

---

## 1. Why the current outcomes are bad

The analysis numbers aren't the root problem. The inputs feeding them are.

| Layer | What happens today | Effect |
|---|---|---|
| **Data** | Live mode launches Chromium, searches Flipkart, opens the first hit, and parses **only the product page** (~8–10 reviews). It does all of this in 8 s and relies on hashed CSS classes (`a.wjcEIp`, `a._1fQZEK`). | Live mode almost always falls back to the seed file. The seed file has **64 reviews across 3 products**, so every query returns the same three earbuds, or a 404. |
| **Sentiment** | Substring lexicon: `any(pos in word for pos in POSITIVE_CUES)`, so "good" also matches "goodness" and "heavy"/"clear" always count as positive. Clause scores are just 88, 22, or the star rating. | Scores move in big jumps and mostly repeat the star rating. Hinglish works only for the dozen phrases listed in the normalizer. |
| **Aspects** | Six fixed earbud pillars, picked by keyword. | It can't analyse a phone, a mixer, or a shoe. |
| **Trust** | Heuristics with no ground truth, presented as a precise 0–100 "authenticity" score. | It claims more certainty than it has. |
| **Frontend** | Near-black slate, an emerald→cyan gradient headline, blurred glow blobs, a "✨ Sparkles" pill badge, glass cards, a radar chart, and an "Offline Demo / Hybrid" toggle that shows internal plumbing. Every metric gets equal weight. | This is the stock "AI dashboard" look. Users can't find the answer they came for. |

**Lesson for the rebuild:** get real data and a way to measure accuracy first. Models come second, and the UI comes last.

---

## 2. What the product should be

Every screen has to help answer one question: **"Should I buy this, and what will annoy me if I do?"**

Rules that follow from it:
1. **Every claim links to evidence.** Each pro, con, and aspect score opens the real review quotes behind it. Users trust quotes more than a number.
2. **Counts, not just scores.** "Battery: 41 people praise it, 9 complain" is clearer than "Battery 78/100".
3. **Honest uncertainty.** If only 4 reviews mention the mic, say "few mentions". Don't hide that behind a 50.
4. **Any product category.** Aspects come from the reviews themselves. They aren't a fixed earbud list.

---

## 3. Research: what works with free resources

| Question | Finding | Decision |
|---|---|---|
| LLM vs. small model for ABSA? | Fine-tuned models win. Zero-/few-shot LLMs come close and need no training data ([Simmering & Huoviala 2023](https://arxiv.org/pdf/2310.18025); [Czech ABSA study, 2025](https://arxiv.org/html/2508.07860v1); [zero-shot multilingual ABSA](https://huggingface.co/papers/2412.12564), where simple prompts beat elaborate ones). | Use a few-shot LLM with a simple prompt for aspect extraction. There's no labelled Flipkart ABSA data to fine-tune on, and building some isn't worth it for this project. |
| What should the LLM extract? | **"Opinion units"**: aspect + polarity + the supporting excerpt. LLMs extract these accurately with few-shot prompts ([Häglund & Björklund, NoDaLiDa 2025](https://preview.aclanthology.org/moar-dois/2025.nodalida-1.24.pdf)). | One JSON object per review: `[{aspect, polarity, quote}]`. The quote gives the UI its evidence for free. |
| How to summarise? | Wayfair's production pipeline: extract aspect–sentiment pairs, consolidate them, keep the most frequent aspects, sample representative reviews, then run a structured prompt ([EMNLP 2025 Industry](https://arxiv.org/html/2509.26103v1)). | Same pipeline. The summary is written **from the aggregated opinion units**, not from raw reviews, and every cited quote is checked to exist. |
| Free sentence-level sentiment model for Hinglish? | `cardiffnlp/twitter-xlm-roberta-base-sentiment` (3-class, trained on tweets in 8 languages including Hindi; [XLM-T paper](https://arxiv.org/pdf/2104.12250)). There's also a MuRIL fine-tune covering English/Hindi/Hinglish ([airzipm/sentiment-analysis-muril-v2](https://huggingface.co/airzipm/sentiment-analysis-muril-v2), a community model, so verify it). XLM-R is a sound base for code-mixed text ([ISI thesis](https://dspace.isical.ac.in/items/431fe1ea-4c9f-4183-8a86-028b27ea5b95)). | Run both on CPU against the gold set (§5) and keep the winner. This serves as the no-LLM fallback and the cross-check. |
| Fake review detection? | Behavioural signals (reviewer history, timing) carry more information than text alone ([Zhang et al., JMIS](https://jmis-web.org/articles/1287)). AI-written fakes are *less specific* and more "mechanical" than real reviews ([JRCS 2025](https://ideas.repec.org/a/eee/joreco/v87y2025ics0969698925001791.html)). | Flipkart exposes no reviewer history, so real fake detection is out of reach. Reframe the feature as **"Review signals"**: duplicates, date bursts, low-specificity text, rating/text mismatch, unverified share. Show which signals fired, and drop the precise authenticity number. |
| Free LLM quota? | Groq free tier: per-model limits, roughly 30 RPM and 1K–14K requests/day, no card needed. Gemini free tier: Flash/Flash-Lite only since Apr 2026, with low daily caps ([summary](https://agentdeals.dev/gemini-api-pricing-changes); check your own dashboards). | Batch **~20 reviews per call**, so 200 reviews ≈ 10 calls. Groq first, Gemini second, rule-based last. Cache by content hash (already done). |
| Real data without scraping? | Kaggle "Flipkart product customer reviews" has ~205K rows across 104 product types, scraped Dec 2022, with VADER-derived labels ([Baselight mirror](https://baselight.app/u/kaggle/dataset/niraliivaghani_flipkart_product_customer_reviews_dataset)). A similar 194K set is on [Zenodo](https://zenodo.org/records/17612521). | Import one of them as the offline catalogue: **~100 products instead of 3**. Check the licence before committing it. Ignore its VADER labels. |
| Free hosting? | HF Spaces CPU Basic offers 2 vCPU and 16 GB, but the docs now say Docker Spaces need a paid plan ([HF docs](https://huggingface.co/docs/hub/spaces-overview)). Flipkart will very likely block datacenter IPs anyway. | Frontend on Vercel (free). Backend demo runs **offline mode only** in the cloud. Live scraping is a local-machine feature. |

---

## 4. Architecture (v3)

```
                    ┌────────────── frontend (Next.js) ──────────────┐
 paste Flipkart URL │ POST /api/v3/analyses {url | product_id}       │
 or pick a product ─┤ GET  /api/v3/analyses/{id}   (poll, ~1 s)      │
                    └───────────────────────┬────────────────────────┘
                                            ▼
 backend (FastAPI)  ── ingest ──►  SQLite: products, reviews (persist forever)
                       │  1. catalogue hit? done
                       │  2. live: httpx GET review pages (Playwright only if needed)
                       │     max 5 pages, 1–2 s jitter, abort on CAPTCHA, never retry
                    ── analyse ─►  SQLite: analyses (keyed by review-set hash)
                       a. normalise (keep negations + emoji)
                       b. sentence sentiment   XLM-T / MuRIL on CPU (batch)
                       c. opinion units        LLM, 20 reviews/call, JSON; keyword fallback
                       d. aspect clustering    multilingual MiniLM embeddings → top 6–8 aspects
                       e. review signals       dupes (embedding cosine), bursts, specificity
                       f. monthly trend        sentiment by review month
                       g. grounded summary     LLM over (c)+(d); quotes verified
```

Main changes from today:
- **Input is a product URL or a catalogue pick, not a search query.** That removes the search-page step, the most fragile part. Fuzzy search runs over the local catalogue only.
- **Ingestion is a background job with progress,** not a request that has to finish in 8 s. ⚠ This replaces the `CLAUDE.md` "8-second timeout" rule. The safety intent stays (one attempt, hard total budget of ~30 s, CAPTCHA aborts, catalogue fallback), but the rule text has to change first.
- **Reviews persist,** so a product scraped once can be analysed again without scraping.
- **Drift becomes a real timeline** (sentiment by month), not keyword cohorts. The "after 3 months" cue detection stays as an extra highlight.
- Error responses and the contract invariants carry over. The response shape changes (dynamic aspects, counts, quotes), so this is a **v3 contract** in `SPEC.md` §C.

Draft response shape (to finalise in SPEC first):

```jsonc
{
  "product": { "name", "category", "image_url", "source_url", "data_source", "reviews_analyzed" },
  "verdict": { "text", "rating_avg", "sentiment_split": {"positive","neutral","negative"}, "generated_by" },
  "aspects": [ { "key", "label", "positive", "negative", "mentions", "confidence": "low|ok|high",
                 "quotes": [ { "review_id", "text", "polarity" } ] } ],
  "pros": [ { "text", "review_ids": [] } ],   "cons": [ { "text", "review_ids": [] } ],
  "signals": { "verified_ratio", "duplicates", "burst_dates": [], "low_specificity_ratio", "flagged_review_ids": [] },
  "trend": [ { "month", "positive_ratio", "count" } ],
  "fulfillment": { "complaint_rate", "examples": [] },
  "reviews": [ /* all analysed reviews, paged; each with sentiment, aspects, flags */ ]
}
```

---

## 5. Measure before you build

This is the step the first build skipped, and the reason nobody could tell whether a change helped.

1. **Gold set.** 300 reviews: the existing 64 seed reviews plus ~240 from the Kaggle set, with **at least 80 Hinglish/code-mixed**. Label each one for polarity, aspects with polarity, and fulfillment vs. product. To save time, let the LLM pre-label and a human correct it. Store it as `backend/eval/gold.jsonl`.
2. **Harness.** `python -m eval` prints per-component macro-F1: sentence sentiment, aspect detection, aspect polarity, fulfillment split. It never touches the network unless `--llm` is passed.
3. **Baseline.** Run today's lexicon engine through the harness. Every later step must beat that number, or it doesn't ship.

---

## 6. Frontend: moving away from the "AI dashboard" look

**Direction: an editorial verdict page.** It should read like a well-made Consumer Reports page, not a crypto dashboard.

| Instead of | Do |
|---|---|
| Dark slate + emerald/cyan gradients, glow blobs, glass | A light-first, warm off-white page with near-black ink and **one** accent colour (e.g. Flipkart-adjacent deep blue, or a muted brick). Dark mode comes from the same tokens, not a separate neon theme. |
| System font + gradient headline | A serif display face for the verdict (e.g. *Fraunces* or *Instrument Serif*) plus a quiet sans for the UI (*IBM Plex Sans* or *Geist*). Use tabular figures for numbers. |
| Sparkles pill badges, icon on every label | Icons only where they help an action. No decorative badges. |
| Radar chart | **Diverging horizontal bars** per aspect (praise on the right, complaints on the left, mention count on the bar). Aspects are easy to compare and work at phone width. |
| Six equal-weight cards | A clear hierarchy, top to bottom: **(1)** verdict sentence + rating + reviews count, **(2)** what people like and dislike (aspect bars, each expands to quotes), **(3)** pros/cons with "see 12 reviews" links, **(4)** "Can you trust these reviews?" in plain language, **(5)** sentiment over time, **(6)** review explorer with filters (aspect, sentiment, verified, flagged). |
| "Offline Demo / Hybrid" toggle | A single input: "Paste a Flipkart product link or search our catalogue". The data source goes in a small footnote ("Reviews collected 29 Oct 2026, 143 reviews"). |
| Spinner | Real progress: "Fetching reviews (3/5 pages)… Reading reviews… Writing summary…". |
| Compare = two dashboards side by side | A compare page with a single aligned table: aspect rows, one column per product, and the winner on each row marked. |

Process:
1. Build **two static mockups** (HTML, real data from the seed file) in different directions, and choose between them before writing any React.
2. Turn the chosen one into design tokens (`globals.css` custom properties + Tailwind theme): colour, type scale, spacing, radius.
3. Build components against worst-case data: 3 reviews, 2,000 reviews, a 120-character product name, one aspect, no Hinglish, all-negative reviews.
4. Check phone width (375 px), keyboard navigation, and contrast (WCAG AA).

---

## 7. Phases

Each phase ends in something that can be demoed, plus a passing test or eval number.

| # | Phase | Work | Done when |
|---|---|---|---|
| 0 | **Decide & freeze** | Answer the open questions (§8). Write SPEC v3 (contract, URL input, job flow). Update the CLAUDE.md scraping rule. Branch `rebuild/v3`. | SPEC v3 approved |
| 1 | **Data** | Kaggle → SQLite import script. Catalogue search. URL-based fetcher using httpx + parser tests on fresh snapshots. **One** manual live check (with your OK) to confirm review pages load without Playwright. | ≥ 80 products available offline; snapshot parser tests pass |
| 2 | **Eval harness** | Gold set, `python -m eval`, lexicon baseline recorded | Baseline numbers committed |
| 3 | **Sentiment + aspects** | XLM-T vs. MuRIL bake-off. LLM opinion units with schema validation + keyword fallback. Embedding aspect clustering. | Beats baseline on gold set; works for a non-earbud product |
| 4 | **Summary + signals + trend** | Grounded pros/cons with quote verification. Review signals. Monthly trend. Fulfillment split. | Unit tests; no unverifiable quote ever reaches the response |
| 5 | **Frontend** | Mockups → tokens → pages (home, product, compare). Progress polling. | Lighthouse a11y ≥ 95; works at 375 px; worst-case data renders |
| 6 | **Ship** | Vercel (frontend), backend locally, or Render/Koyeb free in offline mode. README with screenshots. | Public demo link works with no keys set |

What can be reused: the FastAPI skeleton, the Pydantic `StrictModel` pattern, the LLM provider chain + SQLite cache in `summarizer.py`, the Hinglish normalizer (as a pre-step), the CAPTCHA detection, and the test layout. Everything in `frontend/src/components/` gets replaced.

---

## 8. Decisions needed from you

1. **Categories:** earbuds only (faster, keeps the 6 fixed pillars), or any product (dynamic aspects; recommended)?
2. **Input:** OK to switch from a free-text search to *paste a Flipkart URL + search the local catalogue*?
3. **The 8-second rule:** OK to replace it with a background job (one attempt, ~30 s cap, same CAPTCHA abort and fallback)?
4. **Dataset licence:** you check the Kaggle/Zenodo terms before the data gets committed (or we keep it out of git and add a download script).
5. **Is this a portfolio/demo piece or something real users will use?** That decides whether cloud live scraping matters at all.

## 9. Unverified assumptions (check these early)

- Groq/Gemini free-tier numbers come from secondary blogs. Check your own dashboards.
- That Flipkart review pages are server-rendered and fetchable with plain HTTP. Needs the one manual live check in Phase 1.
- The MuRIL community model's quality. Only the gold set will tell.
- HF Spaces Docker on the free tier. The docs say it's paid, so plan for Render/Koyeb or local hosting.
