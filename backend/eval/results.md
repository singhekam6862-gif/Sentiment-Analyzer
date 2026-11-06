# Evaluation results

Aspect path: rule-based. Gold labels: eval/gold.jsonl.

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

| Precision | Recall | F1 | Polarity accuracy (on 88 found) |
|---|---|---|---|
| 0.81 | 0.94 | 0.87 | 0.91 |

| Aspect | Gold mentions | Precision | Recall | F1 |
|---|---|---|---|---|
| sound_quality | 23 | 0.74 | 1.00 | 0.85 |
| anc_noise_cancellation | 17 | 0.77 | 1.00 | 0.87 |
| mic_call_quality | 9 | 0.90 | 1.00 | 0.95 |
| battery_life | 11 | 0.69 | 1.00 | 0.81 |
| comfort_build | 15 | 0.88 | 0.93 | 0.90 |
| value_for_money | 12 | 1.00 | 0.75 | 0.86 |
| long_term_reliability | 7 | 1.00 | 0.71 | 0.83 |

