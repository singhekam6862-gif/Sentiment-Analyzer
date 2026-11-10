from dataclasses import dataclass
import json
import re

from app.nlp import llm
from app.schemas import Aspect, UseCase

SYSTEM_PROMPT = (
    "You write the buying verdict for one product sold on Flipkart, from aspect counts and real review quotes "
    "(some in Hinglish). Reply with only a JSON object with keys 'headline' (one plain sentence of at most 14 words "
    "naming the strongest praise and, if the counts show one, the strongest complaint, like 'Good for music and "
    "commuting, weak on calls.'; no hype words), 'pros' and 'cons' (up to 3 each; every item is an object with 'text', a "
    "short specific point, and 'aspect', one of the aspect keys given). Use only what the counts and quotes "
    "support; do not invent specs."
)


USE_CASE_PROMPT = (
    "You choose what shoppers would ask a product is good for, from the aspects its reviews discuss. Reply with only "
    'a JSON object: {"use_cases": [{"name": "<2-3 words>", "aspect": "<one aspect key given>"}]}. Give up to 6. Each '
    'name must read naturally in "Is it good for <name>?" and be a real use or situation for this product '
    '("Photography", "Long days out", "Lasting a year"), not the aspect reworded. Only pair a name with an aspect '
    "that directly decides it, and don't name a kind of person the quotes don't mention. Use each aspect at most "
    "once. Fewer is better than a stretch: skip any aspect that says nothing about a use."
)
MAX_HEADLINE_WORDS = 18  # the prompt asks for 14; a model that runs well past it falls through to the next provider
MAX_USE_CASE_NAME = 40  # longer names break the card layout
MIN_MENTIONS = 2  # below this build_use_cases can only answer too_few

NAME_PROMPT = (
    "You shorten a shop listing title to the name a shopper would use: brand, product line and product type. Reply "
    'with only a JSON object: {"name": "<at most 7 words>"}. Use only words from the title. Drop specs, sizes, pack '
    "counts, colours and benefit claims."
)
MAX_NAME_WORDS = 7
FALLBACK_NAME_WORDS = 5


@dataclass
class Draft:
    """LLM-written verdict text; analysis attaches the review ids per aspect."""

    headline: str
    pros: list[tuple[str, str]]  # (text, aspect key)
    cons: list[tuple[str, str]]
    generated_by: str


def _name_words(text: str) -> list[str]:
    return re.findall(r"\w+", text.casefold())


def parse_short_name(raw_text: str, title: str) -> str | None:
    """Validates the model's JSON; a name with a word the title doesn't have is invented, so it's rejected."""
    try:
        name = json.loads(raw_text)["name"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(name, str):
        return None
    words = _name_words(name)
    return name.strip() if 0 < len(words) <= MAX_NAME_WORDS and set(words) <= set(_name_words(title)) else None


def short_product_name(title: str) -> str:
    """The name to show for a live-scraped product: from the LLM chain, else the title's first words before any specs."""
    if len(title.split()) <= FALLBACK_NAME_WORDS:
        return title
    short = llm.ask(NAME_PROMPT, f"Title: {title}", lambda raw, _provider: parse_short_name(raw, title))
    head = re.split(r"\s+-\s+|\s*\(", title)[0] or title
    return short or " ".join(head.split()[:FALLBACK_NAME_WORDS])


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
    """Validates the model's JSON; drops claims about unknown aspects; None when the headline is missing or too long."""
    try:
        parsed = json.loads(raw_text)
        headline = str(parsed["headline"]).strip()
        pros, cons = _claims(parsed.get("pros", []), keys), _claims(parsed.get("cons", []), keys)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return Draft(headline, pros, cons, provider) if 0 < len(headline.split()) <= MAX_HEADLINE_WORDS else None


def generate_summary(product_name: str, aspects: list[Aspect], use_cases: list[UseCase]) -> Draft | None:
    """Verdict text from the LLM chain; None means the caller uses its rule-based verdict."""
    if not aspects:
        return None
    keys = {a.key for a in aspects}
    return llm.ask(SYSTEM_PROMPT, build_prompt(product_name, aspects, use_cases),
                   lambda raw, provider: parse_llm_summary(raw, provider, keys))


def parse_use_cases(raw_text: str, keys: set[str]) -> list[tuple[str, list[str]]] | None:
    """Validates the model's JSON; drops unknown aspects and repeats; None when nothing usable is left."""
    out: list[tuple[str, list[str]]] = []
    names: set[str] = set()
    used: set[str] = set()
    try:
        for item in json.loads(raw_text)["use_cases"]:
            name, key = item.get("name"), item.get("aspect")
            if not isinstance(name, str) or not 0 < len(name := name.strip()) <= MAX_USE_CASE_NAME:
                continue
            if key in keys and key not in used and name.casefold() not in names:
                names.add(name.casefold())
                used.add(key)
                out.append((name[0].upper() + name[1:], [key]))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    return out[:6] or None


def generate_use_cases(product_name: str, aspects: list[Aspect]) -> list[tuple[str, list[str]]]:
    """Use-case template for a product with no written one: the LLM only picks names and aspects, counts set the verdict.

    One aspect per use case, because mentions can't be de-duplicated across aspects and "Based on N reviews" must hold.
    """
    usable = [a for a in aspects if a.praise + a.complaints + a.mixed >= MIN_MENTIONS]
    if not usable:
        return []
    lines = [f"- {a.key} ({a.label}): " + " | ".join(q.text for q in a.quotes) for a in usable]
    prompt = f"Product: {product_name}\nAspects:\n" + "\n".join(lines)
    keys = {a.key for a in usable}
    return llm.ask(USE_CASE_PROMPT, prompt, lambda raw, _provider: parse_use_cases(raw, keys)) or []
