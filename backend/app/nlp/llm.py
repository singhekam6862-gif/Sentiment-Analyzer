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
LLM_TIMEOUT_SECONDS = 20.0

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


def ask(system: str, prompt: str, parse: Callable[[str, str], T | None]) -> T | None:
    """First valid parsed answer from the provider chain, or None (callers then use their rule-based path)."""
    order = os.getenv("LLM_PROVIDERS", "groq,gemini")
    for provider in (p.strip().lower() for p in order.split(",")):
        if provider in PROVIDERS and (result := _call_provider(provider, system, prompt, parse)) is not None:
            return result
    return None
