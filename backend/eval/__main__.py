"""Accuracy of the NLP pipeline against hand-checked labels (eval/gold.jsonl). See eval/README.md.

    cd backend
    python -m eval                       # rule-based path only, never touches the network
    python -m eval --llm                 # aspects from the LLM chain (keys from backend/.env)
    python -m eval --out eval/results.md # also save the report as UTF-8
"""

import argparse
from collections.abc import Callable
import json
from pathlib import Path
import sys

from app import catalogue
from app.nlp import opinions
from app.nlp.analysis import classify_reviews
from app.nlp.categories import LABELS
from app.schemas import RawReview
from eval.metrics import accuracy, confusion, macro_f1, set_prf

GOLD_PATH = Path(__file__).resolve().parent / "gold.jsonl"
SENTIMENTS = ("positive", "negative", "neutral")
GROUPS = ("product", "fulfillment", "suspicious")
ASPECT_KEYS = tuple(LABELS)  # the earbuds template; other keys an LLM invents are out of scope, not errors


def load_gold() -> dict[str, dict]:
    rows = [json.loads(line) for line in GOLD_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["review_id"]: row for row in rows}


def load_reviews() -> dict[str, list[RawReview]]:
    """Seed reviews per catalogue product (the trust scorer needs each product's reviews together)."""
    return {p.id: catalogue.get_product(p.id)[1] for p in catalogue.list_products()}


def star_baseline(rating: int) -> str:
    return "positive" if rating >= 4 else "negative" if rating <= 2 else "neutral"


def predict(reviews_by_product: dict[str, list[RawReview]], gold: dict[str, dict], use_llm: bool) -> tuple[dict, int]:
    """review_id -> predicted labels, and how many reviews fell back to the rule-based aspect path."""
    fallbacks = [0]
    rule_based = opinions.extract_opinions

    def counted(review: RawReview):
        fallbacks[0] += 1
        return rule_based(review)

    out: dict[str, dict] = {}
    for reviews in reviews_by_product.values():
        for r in classify_reviews(reviews):
            out[r.review_id] = {"sentiment": r.sentiment, "group": r.group}
        # Aspects are scored on the gold product group, so grouping mistakes don't leak into aspect numbers.
        product = [r for r in reviews if gold[r.review_id]["group"] == "product"]
        if use_llm:
            opinions.extract_opinions = counted  # extract_all_opinions calls it for every batch the LLM didn't answer
            try:
                found = opinions.extract_all_opinions(product, list(ASPECT_KEYS))
            finally:
                opinions.extract_opinions = rule_based
        else:
            found = {r.review_id: rule_based(r) for r in product}
        for r in reviews:
            out[r.review_id]["star"] = star_baseline(r.rating)
            out[r.review_id]["aspects"] = {k: p for k, p, _ in found.get(r.review_id, []) if k in ASPECT_KEYS}
    return out, fallbacks[0]


def _table(header: list[str], rows: list[list]) -> list[str]:
    cells = [[f"{c:.2f}" if isinstance(c, float) else str(c) for c in row] for row in rows]
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(r) + " |" for r in cells]


def _confusion_table(gold: list[str], pred: list[str], labels: tuple[str, ...]) -> list[str]:
    matrix = confusion(gold, pred, labels)
    return _table(["gold \\ predicted", *labels], [[label, *row] for label, row in zip(labels, matrix)])


def sentiment_section(gold: dict, pred: dict) -> list[str]:
    ids = list(gold)
    hing = [i for i in ids if gold[i]["hinglish"]]
    g = [gold[i]["sentiment"] for i in ids]

    def row(name: str, key: str) -> list:
        p = [pred[i][key] for i in ids]
        h_acc = accuracy([gold[i]["sentiment"] for i in hing], [pred[i][key] for i in hing])
        return [name, accuracy(g, p), macro_f1(g, p, SENTIMENTS), h_acc]

    return [
        f"## Review sentiment ({len(ids)} reviews, {len(hing)} Hinglish)", "",
        *_table(["Method", "Accuracy", "Macro-F1", "Accuracy on Hinglish"],
                [row("Star rating only (baseline)", "star"), row("Pipeline (text + rating)", "sentiment")]),
        "", "Pipeline confusion matrix:", "",
        *_confusion_table(g, [pred[i]["sentiment"] for i in ids], SENTIMENTS),
    ]


def group_section(gold: dict, pred: dict) -> list[str]:
    ids = list(gold)
    g, p = [gold[i]["group"] for i in ids], [pred[i]["group"] for i in ids]
    return [
        f"## Review groups: product / fulfillment / suspicious ({len(ids)} reviews)", "",
        *_table(["Accuracy", "Macro-F1"], [[accuracy(g, p), macro_f1(g, p, GROUPS)]]),
        "", *_confusion_table(g, p, GROUPS),
    ]


def aspect_section(gold: dict, pred: dict) -> list[str]:
    ids = [i for i in gold if gold[i]["group"] == "product"]
    gold_pairs = {(i, k) for i in ids for k in gold[i]["aspects"]}
    pred_pairs = {(i, k) for i in ids for k in pred[i]["aspects"]}
    both = gold_pairs & pred_pairs
    polarity = accuracy([gold[i]["aspects"][k] for i, k in both], [pred[i]["aspects"][k] for i, k in both])
    per_aspect = []
    for key in ASPECT_KEYS:
        g = {pair for pair in gold_pairs if pair[1] == key}
        per_aspect.append([key, len(g), *set_prf(g, {pair for pair in pred_pairs if pair[1] == key})])
    return [
        f"## Aspects ({len(ids)} product reviews, {len(gold_pairs)} labelled opinions)", "",
        *_table(["Precision", "Recall", "F1", f"Polarity accuracy (on {len(both)} found)"],
                [[*set_prf(gold_pairs, pred_pairs), polarity]]),
        "", *_table(["Aspect", "Gold mentions", "Precision", "Recall", "F1"], per_aspect),
    ]


def report(gold: dict, pred: dict, path: str) -> str:
    sections: list[Callable[[dict, dict], list[str]]] = [sentiment_section, group_section, aspect_section]
    lines = ["# Evaluation results", "", f"Aspect path: {path}. Gold labels: eval/gold.jsonl.", ""]
    for section in sections:
        lines += [*section(gold, pred), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> str:
    args = argparse.ArgumentParser(prog="python -m eval")
    args.add_argument("--llm", action="store_true", help="extract aspects with the LLM chain (spends API quota)")
    args.add_argument("--out", help="also write the report to this file (UTF-8)")
    opts = args.parse_args(argv)
    if opts.llm:
        from dotenv import load_dotenv  # installed with uvicorn[standard]

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    gold = load_gold()
    pred, fallbacks = predict(load_reviews(), gold, opts.llm)
    path = "rule-based"
    if opts.llm:
        path = f"LLM chain ({fallbacks} reviews fell back to rule-based)" if fallbacks else "LLM chain"
    text = report(gold, pred, path)
    if opts.out:
        Path(opts.out).write_text(text + "\n", encoding="utf-8")
    return text


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(main())
