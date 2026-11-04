from dataclasses import dataclass
import json

from app.nlp import llm
from app.schemas import Aspect, UseCase

SYSTEM_PROMPT = (
    "You write the buying verdict for one product sold on Flipkart, from aspect counts and real review quotes "
    "(some in Hinglish). Reply with only a JSON object with keys 'headline' (one or two plain sentences: what it "
    "is good for and what it is not), 'pros' and 'cons' (up to 3 each; every item is an object with 'text', a "
    "short specific point, and 'aspect', one of the aspect keys given). Use only what the counts and quotes "
    "support; do not invent specs."
)


@dataclass
class Draft:
    """LLM-written verdict text; analysis attaches the review ids per aspect."""

    headline: str
    pros: list[tuple[str, str]]  # (text, aspect key)
    cons: list[tuple[str, str]]
    generated_by: str


def build_prompt(product_name: str, aspects: list[Aspect], use_cases: list[UseCase]) -> str:
    lines = [
        f"- {a.key} ({a.label}): {a.praise} praise, {a.complaints} complaints, {a.mixed} mixed. Quotes: "
        + " | ".join(q.text for q in a.quotes)
        for a in aspects
    ]
    uses = ", ".join(f"{u.name}: {u.verdict}" for u in use_cases) or "none"
    return f"Product: {product_name}\nUse cases: {uses}\nAspects:\n" + "\n".join(lines)


def _claims(items: object, keys: set[str]) -> list[tuple[str, str]]:
    claims = [(str(i["text"]).strip(), i["aspect"]) for i in items if i.get("aspect") in keys]  # type: ignore[union-attr]
    return [c for c in claims if c[0]][:3]


def parse_llm_summary(raw_text: str, provider: str, keys: set[str]) -> Draft | None:
    """Validates the model's JSON; drops claims about unknown aspects; None when the headline is missing."""
    try:
        parsed = json.loads(raw_text)
        headline = str(parsed["headline"]).strip()
        pros, cons = _claims(parsed.get("pros", []), keys), _claims(parsed.get("cons", []), keys)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return Draft(headline, pros, cons, provider) if headline else None


def generate_summary(product_name: str, aspects: list[Aspect], use_cases: list[UseCase]) -> Draft | None:
    """Verdict text from the LLM chain; None means the caller uses its rule-based verdict."""
    if not aspects:
        return None
    keys = {a.key for a in aspects}
    return llm.ask(SYSTEM_PROMPT, build_prompt(product_name, aspects, use_cases),
                   lambda raw, provider: parse_llm_summary(raw, provider, keys))
