# Evaluation

How accurate is the pipeline? `python -m eval` runs the 64 catalogue reviews through the real code and compares
its output with hand-checked labels in `gold.jsonl`.

```bash
cd backend
python -m eval                          # rule-based path; never touches the network
python -m eval --llm                    # aspects from the LLM chain (keys from .env; answers are cached)
python -m eval --out eval/results.md    # save the report (UTF-8)
```

Saved runs: [`results.md`](results.md) (rule-based) and [`results_llm.md`](results_llm.md) (LLM chain).

## What is measured

| Component | Code under test | Metric |
|---|---|---|
| Review sentiment | `absa_engine.classify_review_sentiment` | accuracy, macro-F1, accuracy on the Hinglish subset; compared with a **star-rating-only baseline** (4–5★ positive, 3★ neutral, 1–2★ negative) |
| Review groups | `analysis.classify_reviews` (trust scorer + fulfillment split) | accuracy, macro-F1, confusion matrix |
| Aspect detection | `opinions.extract_opinions` (rule-based) or `opinions.extract_all_opinions` (`--llm`) | precision / recall / F1 over (review, aspect) pairs, overall and per aspect |
| Aspect polarity | same | accuracy on the pairs both gold and prediction found |

Macro-F1 averages the per-class F1 without weighting, so the rare classes (neutral, suspicious) count as much as
the common ones.

Aspects are scored only on reviews whose **gold** group is `product`, so a grouping mistake doesn't also count as
an aspect mistake. Only the 7 aspects of the earbuds template are labelled (`categories.LABELS`). Aspects outside
it (connectivity, controls, companion app) are ignored on both sides, not counted as errors.

## Gold labels (`gold.jsonl`)

One JSON object per review:

```json
{"review_id": "fk_rt310_003", "sentiment": "positive", "group": "product", "hinglish": false,
 "aspects": {"sound_quality": "praise", "value_for_money": "praise", "comfort_build": "complaint"}}
```

Labelling rules:
- Labels are taken from the review **text** only, not the title. The pipeline quotes from the text, so a
  title-only opinion can't be found.
- `sentiment` is the reader's overall impression. A 3★ review that only complains is `negative`.
- An aspect gets a label only when the review gives an opinion on it. A spec mention ("7.5 hours with ANC on")
  is not an opinion on ANC.
- A part failing after weeks or months of use is `long_term_reliability`. It also counts as `battery_life` only
  when the battery itself got worse.
- `hinglish` is true when the text has Hindi words in Latin script ("mast", "paisa vasool", "kharab").

**The first draft of these labels was written by an AI assistant (Claude), not a human.** Before quoting any
number, check every row yourself and fix the ones you disagree with. The plan in `docs/REBUILD_PLAN.md` §5 asks
for exactly this: machine pre-labels, corrected by a person. `tests/test_eval.py` checks that every seed review
has exactly one valid row.

## Results (rule-based path, draft labels)

| Component | Result |
|---|---|
| Sentiment, star rating only | accuracy 0.95, macro-F1 0.86 |
| Sentiment, pipeline (first run) | accuracy 0.92, macro-F1 0.73. **Worse than the baseline**: averaging clause scores turned two balanced 3★ reviews positive and left three complaining 3★ reviews neutral |
| Sentiment, pipeline (after the 3★ fix) | accuracy 0.98, macro-F1 0.94. A 3★ review is now neutral when it has both praise and complaints, else it takes the side it has; `complain`, `artificial`, `robotic` and `dropped` joined the complaint words |
| Groups | accuracy 1.00 |
| Aspects, rule-based | P 0.81, R 0.94, F1 0.87; polarity 0.91 |
| Aspects, LLM chain | P 0.88, R 0.87, F1 0.88; polarity 0.95. Weakest on `long_term_reliability` (F1 0.53) |

The keyword path finds almost everything but over-matches: "music playback" counts as a sound opinion, "Zoom
calls" as a mic opinion, "stopped charging" as a battery opinion. The LLM is more precise and better at telling
praise from complaints. On reliability it does two things wrong: it files a battery that wore out over months under
`battery_life` only (3 misses), and it reads "works reliably" or "connection drops" as long-term reliability
(4 false hits).

## Limitations

- **Small and hand-written data.** 64 reviews of 3 earbuds. The catalogue reviews were written for the demo, so
  they are cleaner than real Flipkart text, and grouping in particular scores perfectly because the planted
  bursts and courier complaints are obvious. Expect lower numbers on scraped reviews.
- **Only 13 Hinglish reviews and 3 neutral ones.** Their scores move a lot with each single review.
- **Tuned on the test set.** The 3★ fix and its new words came from reading this set's errors, and there is no
  held-out split, so 0.98 overstates accuracy on new reviews. Label a fresh batch before tuning again and report
  that batch separately.
- **One labeller.** There is no inter-annotator agreement. A second person labelling the same rows and reporting
  Cohen's kappa would show how subjective the task is.
- **LLM runs are cached.** A repeat `--llm` run reuses the stored answers. Delete `app/data/cache.sqlite` to
  measure a fresh sample.

## Growing the set

Add real reviews from a live scrape: copy each review's id and text into a new catalogue product in
`app/data/seed_reviews.json`, then add one `gold.jsonl` row per review. Aim for at least 80 Hinglish reviews and a
second product category, as in `docs/REBUILD_PLAN.md` §5.
