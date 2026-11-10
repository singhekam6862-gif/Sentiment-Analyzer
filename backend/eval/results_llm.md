# Evaluation results

Aspect path: LLM chain. Gold labels: eval/gold.jsonl.

## Review sentiment (64 reviews, 13 Hinglish)

| Method | Accuracy | Macro-F1 | Accuracy on Hinglish |
|---|---|---|---|
| Star rating only (baseline) | 0.95 | 0.86 | 1.00 |
| Pipeline (text + rating) | 0.98 | 0.94 | 1.00 |

Pipeline confusion matrix:

| gold \ predicted | positive | negative | neutral |
|---|---|---|---|
| positive | 40 | 0 | 0 |
| negative | 0 | 20 | 1 |
| neutral | 0 | 0 | 3 |

## Review groups: product / fulfillment / suspicious (64 reviews)

| Accuracy | Macro-F1 |
|---|---|
| 1.00 | 1.00 |

| gold \ predicted | product | fulfillment | suspicious |
|---|---|---|---|
| product | 52 | 0 | 0 |
| fulfillment | 0 | 8 | 0 |
| suspicious | 0 | 0 | 4 |

## Aspects (52 product reviews, 94 labelled opinions)

| Precision | Recall | F1 | Polarity accuracy (on 82 found) |
|---|---|---|---|
| 0.88 | 0.87 | 0.88 | 0.95 |

| Aspect | Gold mentions | Precision | Recall | F1 |
|---|---|---|---|---|
| sound_quality | 23 | 0.92 | 0.96 | 0.94 |
| anc_noise_cancellation | 17 | 1.00 | 0.76 | 0.87 |
| mic_call_quality | 9 | 1.00 | 1.00 | 1.00 |
| battery_life | 11 | 0.92 | 1.00 | 0.96 |
| comfort_build | 15 | 0.88 | 0.93 | 0.90 |
| value_for_money | 12 | 0.82 | 0.75 | 0.78 |
| long_term_reliability | 7 | 0.50 | 0.57 | 0.53 |

