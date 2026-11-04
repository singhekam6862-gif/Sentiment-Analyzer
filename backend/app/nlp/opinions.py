"""Opinion units: (aspect, polarity, verbatim quote) per review (SPEC §A.5).

LLM path first (any product category), rule-based keyword path per batch when no provider answers.
"""

import json
import re

from app.nlp import llm
from app.nlp.absa_engine import extract_aspects_from_clause, score_clause_sentiment, split_into_clauses
from app.nlp.categories import RELIABILITY
from app.nlp.preprocessor import normalize_review_text
from app.schemas import RawReview

Opinion = tuple[str, str, str]  # (aspect key, praise|complaint|mixed, quote)

BATCH_SIZE = 20
POLARITIES = {"praise", "complaint", "mixed"}

LONG_TERM = re.compile(
    r"\b(after\s+\d+\s+(weeks?|months?)|\d+\s+months?\s+(use|later)|using\s+since"
    r"|stopped\s+(working|charging)|ab\s+kharab|still\s+working|years?\s+later)\b",
    re.IGNORECASE,
)

SYSTEM_PROMPT = """You extract opinion units from Flipkart product reviews. Many are in Hinglish (Hindi in Latin script): \
"mast", "badhiya", "paisa vasool" are praise; "bakwas", "bekar", "kharab" are complaints; "nahi" negates.

For each review, list every product aspect it gives an opinion on. Reply with only a JSON object:
{"reviews": [{"id": "<review id>", "opinions": [{"aspect": "<key>", "polarity": "praise|complaint|mixed", "quote": "<words>"}]}]}

Rules:
- "quote" is copied character for character from the review text: the shortest clause that carries the opinion.
- At most one opinion per aspect per review. Use "mixed" only when the same aspect is both praised and criticised.
- "aspect" is a short snake_case key a shopper would recognise (battery_life, camera, build_quality). Reuse the \
suggested keys when they fit and keep keys consistent across reviews.
- Use "long_term_reliability" for anything that broke, stopped or got worse after weeks or months of use.
- Ignore delivery, packaging, seller and refund comments: they are not about the product.

Example reviews:
[r1] (2★) Camera is mast in daylight but battery drains by evening. Delivery was late.
[r2] (5★) After 4 months still working fine, sound bahut clear hai.
Example answer:
{"reviews": [{"id": "r1", "opinions": [{"aspect": "camera", "polarity": "praise", "quote": "Camera is mast in daylight"}, \
{"aspect": "battery_life", "polarity": "complaint", "quote": "battery drains by evening"}]}, \
{"id": "r2", "opinions": [{"aspect": "long_term_reliability", "polarity": "praise", "quote": "After 4 months still working fine"}, \
{"aspect": "sound_quality", "polarity": "praise", "quote": "sound bahut clear hai"}]}]}"""


def _polarity(score: float) -> str:
    return "praise" if score >= 60 else "complaint" if score <= 40 else "mixed"


def extract_opinions(review: RawReview) -> list[Opinion]:
    """Rule-based path: one unit per aspect per review; each quote is a clause copied from review.text."""
    units: dict[str, tuple[str, str]] = {}
    for clause in split_into_clauses(review.text):
        clause = clause.strip(" ,")  # still a verbatim substring
        cleaned = normalize_review_text(clause)["cleaned_text"]
        polarity = _polarity(score_clause_sentiment(cleaned, review.rating))
        for aspect in extract_aspects_from_clause(cleaned):
            units.setdefault(aspect.value, (polarity, clause))
        # Long-term cues only count as reliability evidence from clearly happy or unhappy owners.
        if RELIABILITY not in units and review.rating != 3 and LONG_TERM.search(clause):
            units[RELIABILITY] = ("praise" if review.rating >= 4 else "complaint", clause)
    return [(key, polarity, quote) for key, (polarity, quote) in units.items()]


def build_prompt(batch: list[RawReview], suggested: list[str]) -> str:
    lines = [f"[{r.review_id}] ({r.rating}★) {r.text}" for r in batch]
    return f"Suggested aspect keys: {', '.join(suggested) or 'none'}\nReviews:\n" + "\n".join(lines)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def parse_opinions(raw_text: str, batch: dict[str, RawReview]) -> dict[str, list[Opinion]] | None:
    """Validates the model's JSON. Drops units with unknown ids or polarities, and quotes not found verbatim."""
    out: dict[str, list[Opinion]] = {rid: [] for rid in batch}
    try:
        for entry in json.loads(raw_text)["reviews"]:
            review = batch.get(str(entry.get("id")))
            if review is None:
                continue
            for o in entry.get("opinions", []):
                key, polarity, quote = _slug(str(o["aspect"])), o.get("polarity"), str(o["quote"]).strip(" \"“”")
                units = out[review.review_id]
                if key and polarity in POLARITIES and quote and quote in review.text and key not in {u[0] for u in units}:
                    units.append((key, polarity, quote))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return out


def extract_all_opinions(reviews: list[RawReview], suggested: list[str]) -> dict[str, list[Opinion]]:
    """Opinion units for every review, in batches; keys found so far are suggested to later batches."""
    out: dict[str, list[Opinion]] = {}
    keys = list(suggested)
    for start in range(0, len(reviews), BATCH_SIZE):
        batch = {r.review_id: r for r in reviews[start : start + BATCH_SIZE]}
        found = llm.ask(SYSTEM_PROMPT, build_prompt(list(batch.values()), keys),
                        lambda raw, _provider, batch=batch: parse_opinions(raw, batch))
        if found is None:
            found = {rid: extract_opinions(r) for rid, r in batch.items()}
        out.update(found)
        keys = list(dict.fromkeys(keys + [k for units in found.values() for k, _, _ in units]))
    return out
