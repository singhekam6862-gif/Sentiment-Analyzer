from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3

import httpx

from app.schemas import AISummary, AspectKey, AspectScore, RawReview, ReviewStats

logger = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cache.sqlite"
LLM_TIMEOUT_SECONDS = 5.0
MAX_PROMPT_REVIEWS = 10

# name -> (key env var, model env var, default model, OpenAI-compatible chat completions URL)
PROVIDERS: dict[str, tuple[str, str, str, str]] = {
    "groq": (
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "openai/gpt-oss-20b",
        "https://api.groq.com/openai/v1/chat/completions",
    ),
    "gemini": (
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "gemini-2.5-flash",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ),
}

SYSTEM_PROMPT = (
    "You summarise Indian e-commerce product reviews, some written in Hinglish. "
    "Reply with only a JSON object with keys 'pros' (exactly 3 short, specific strings), "
    "'cons' (exactly 3 short, specific strings) and 'buying_verdict' (one sentence). "
    "Base every point on the reviews given; do not invent specs."
)

ASPECT_PRO_PHRASES = {
    AspectKey.ANC_NOISE_CANCELLATION: "Active noise cancellation gives strong commute noise isolation.",
    AspectKey.SOUND_QUALITY: "Punchy, dynamic sound quality with crisp treble and deep bass response.",
    AspectKey.VALUE_FOR_MONEY: "Excellent value for money, offering high-end features at a competitive price.",
    AspectKey.BATTERY_LIFE: "Reliable battery backup for extended daily listening sessions.",
    AspectKey.COMFORT_BUILD: "Comfortable ergonomic fit suitable for long hours and workouts.",
    AspectKey.MIC_CALL_QUALITY: "Decent voice pickup for casual indoor calls.",
}

ASPECT_CON_PHRASES = {
    AspectKey.MIC_CALL_QUALITY: "Microphone call quality struggles outdoors in traffic and wind.",
    AspectKey.BATTERY_LIFE: "Battery capacity and charging reliability degrade noticeably over months.",
    AspectKey.COMFORT_BUILD: "Charging case scratches easily and the lid feels delicate.",
    AspectKey.ANC_NOISE_CANCELLATION: "ANC mode causes slight ear pressure in quiet indoor spaces.",
    AspectKey.SOUND_QUALITY: "Default tuning is bass-heavy and needs manual EQ for neutral audio.",
    AspectKey.VALUE_FOR_MONEY: "Frequent price fluctuations make timing your purchase important.",
}

ASPECT_NAMES = {
    AspectKey.SOUND_QUALITY: "sound quality",
    AspectKey.ANC_NOISE_CANCELLATION: "noise cancellation",
    AspectKey.MIC_CALL_QUALITY: "mic and call quality",
    AspectKey.BATTERY_LIFE: "battery life",
    AspectKey.COMFORT_BUILD: "comfort and build",
    AspectKey.VALUE_FOR_MONEY: "value for money",
}


def build_rule_based_summary(aspect_scores: list[AspectScore], stats: ReviewStats) -> AISummary:
    """Guaranteed 3 pros, 3 cons and a verdict, with no network dependency."""
    ranked = sorted(aspect_scores, key=lambda a: a.score, reverse=True)
    best, worst = ranked[0].aspect, ranked[-1].aspect
    verdict = (
        f"Rated {stats.overall_rating:.1f}/5 by Flipkart buyers with a review trust score of "
        f"{stats.trust_score}/100; strongest on {ASPECT_NAMES[best]}, weakest on {ASPECT_NAMES[worst]}."
    )
    return AISummary(
        pros=[ASPECT_PRO_PHRASES[a.aspect] for a in ranked[:3]],
        cons=[ASPECT_CON_PHRASES[a.aspect] for a in reversed(ranked[-3:])],
        buying_verdict=verdict,
        generated_by="rule_based",
    )


def build_prompt(product_name: str, reviews: list[RawReview], aspect_scores: list[AspectScore]) -> str:
    """Builds the user prompt from trusted reviews and the computed aspect scores."""
    aspects = ", ".join(f"{ASPECT_NAMES[a.aspect]} {a.score}/100" for a in aspect_scores)
    lines = [f"- [{r.rating}★] {(r.title or '').strip()} {r.text[:300]}".strip() for r in reviews[:MAX_PROMPT_REVIEWS]]
    return f"Product: {product_name}\nAspect scores: {aspects}\nReviews:\n" + "\n".join(lines)


def parse_llm_summary(raw_text: str, provider: str) -> AISummary | None:
    """Validates the model's JSON answer; returns None when it breaks the 3+3+verdict contract."""
    try:
        parsed = json.loads(raw_text)
        pros = [str(p).strip() for p in parsed["pros"] if str(p).strip()]
        cons = [str(c).strip() for c in parsed["cons"] if str(c).strip()]
        verdict = str(parsed["buying_verdict"]).strip()
    except (ValueError, KeyError, TypeError):
        return None
    if len(pros) < 3 or len(cons) < 3 or not verdict:
        return None
    return AISummary(pros=pros[:3], cons=cons[:3], buying_verdict=verdict, generated_by=provider)


def _cache_key(provider: str, model: str, prompt: str) -> str:
    return hashlib.sha256(f"{provider}\n{model}\n{prompt}".encode("utf-8")).hexdigest()


def _open_cache() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, answer TEXT)")
    return conn


def _cache_get(key: str) -> str | None:
    try:
        with closing(_open_cache()) as conn:
            row = conn.execute("SELECT answer FROM llm_cache WHERE key = ?", (key,)).fetchone()
            return row[0] if row else None
    except sqlite3.Error as exc:
        logger.warning("LLM cache read failed: %s", exc)
        return None


def _cache_put(key: str, answer: str) -> None:
    try:
        with closing(_open_cache()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?, ?)", (key, answer))
    except sqlite3.Error as exc:
        logger.warning("LLM cache write failed: %s", exc)


def _call_provider(provider: str, prompt: str) -> AISummary | None:
    """One chat-completions call (or cache hit) for one provider; never raises."""
    key_env, model_env, default_model, url = PROVIDERS[provider]
    api_key = os.getenv(key_env)
    if not api_key:
        return None
    model = os.getenv(model_env) or default_model
    cache_key = _cache_key(provider, model, prompt)

    cached = _cache_get(cache_key)
    if cached and (summary := parse_llm_summary(cached, provider)):
        return summary

    body = {
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    try:
        resp = httpx.post(url, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("%s summary failed: %s", provider, exc)
        return None

    summary = parse_llm_summary(answer, provider)
    if summary:
        _cache_put(cache_key, answer)
    else:
        logger.warning("%s returned an invalid summary; trying next provider", provider)
    return summary


def generate_summary(
    product_name: str,
    trusted_reviews: list[RawReview],
    aspect_scores: list[AspectScore],
    stats: ReviewStats,
) -> AISummary:
    """Tries each provider in LLM_PROVIDERS order, then falls back to the rule-based summary."""
    if trusted_reviews:
        prompt = build_prompt(product_name, trusted_reviews, aspect_scores)
        order = os.getenv("LLM_PROVIDERS", "groq,gemini")
        for provider in (p.strip().lower() for p in order.split(",")):
            if provider in PROVIDERS and (summary := _call_provider(provider, prompt)):
                return summary
    return build_rule_based_summary(aspect_scores, stats)
