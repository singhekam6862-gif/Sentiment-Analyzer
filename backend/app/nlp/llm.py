"""LLM provider chain shared by the summarizer and opinion extraction (SPEC §A.5, §A.7).

Providers are tried in LLM_PROVIDERS order; one without a key is skipped. Valid answers are cached in
data/cache.sqlite keyed by provider, model and prompt, so a repeated analysis spends no quota.
"""

from collections.abc import Callable
from contextlib import closing
import hashlib
import logging
import os
from pathlib import Path
import sqlite3
from typing import TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "cache.sqlite"
LLM_TIMEOUT_SECONDS = 15.0  # a 20-review batch takes ~2 s on Groq; a provider failing slowly costs this once per job
# Default reasoning made gpt-oss on Groq fail JSON mode (400 json_validate_failed) and Gemini time out.
# shortcut: assumes reasoning models (gpt-oss, Gemini 2.5+); remove it if a *_MODEL is set to a non-reasoning model.
REASONING_EFFORT = "low"

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
        "gemini-3.8-flash",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ),
}


def _cache_key(provider: str, model: str, system: str, prompt: str) -> str:
    return hashlib.sha256(f"{provider}\n{model}\n{system}\n{prompt}".encode("utf-8")).hexdigest()


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


def _call_provider(provider: str, system: str, prompt: str, parse: Callable[[str, str], T | None]) -> T | None:
    """One chat-completions call (or cache hit) for one provider; never raises."""
    key_env, model_env, default_model, url = PROVIDERS[provider]
    api_key = os.getenv(key_env)
    if not api_key:
        return None
    model = os.getenv(model_env) or default_model
    cache_key = _cache_key(provider, model, system, prompt)

    cached = _cache_get(cache_key)
    if cached and (result := parse(cached, provider)) is not None:
        return result

    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "reasoning_effort": REASONING_EFFORT,
    }
    try:
        resp = httpx.post(url, json=body, headers={"Authorization": f"Bearer {api_key}"}, timeout=LLM_TIMEOUT_SECONDS)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("%s call failed: %s", provider, exc)
        return None

    result = parse(answer, provider)
    if result is not None:
        _cache_put(cache_key, answer)
    else:
        logger.warning("%s returned an invalid answer; trying next provider", provider)
    return result


def ask(system: str, prompt: str, parse: Callable[[str, str], T | None], skip: set[str] | None = None) -> T | None:
    """First valid parsed answer from the provider chain, or None (callers then use their rule-based path).

    Pass the same `skip` set to related calls: a provider that fails is added and not tried again by them.
    """
    order = os.getenv("LLM_PROVIDERS", "groq,gemini")
    for provider in (p.strip().lower() for p in order.split(",")):
        if provider not in PROVIDERS or (skip is not None and provider in skip):
            continue
        if (result := _call_provider(provider, system, prompt, parse)) is not None:
            return result
        if skip is not None:
            skip.add(provider)
    return None
