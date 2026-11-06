import json

import httpx
import pytest

from app import store
from app.nlp import llm


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch, tmp_path):
    """Keeps every test off the network and away from the real LLM cache and saved analyses."""
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_MODEL", "GEMINI_MODEL", "LLM_PROVIDERS", "FORCE_FALLBACK"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "CACHE_PATH", tmp_path / "cache.sqlite")
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "cache.sqlite")


class FakeLLM:
    """Stands in for httpx.post. `answers` maps provider -> answer, or is a callable(provider, body) -> answer."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, **kwargs):
        provider = "groq" if "groq.com" in url else "gemini"
        self.calls.append((provider, kwargs["json"]))
        answer = self.answers(provider, kwargs["json"]) if callable(self.answers) else self.answers.get(provider)
        if isinstance(answer, Exception):
            raise answer
        content = answer if isinstance(answer, str) else json.dumps(answer)
        body = {"choices": [{"message": {"content": content}}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))


@pytest.fixture
def fake_llm(monkeypatch):
    def install(answers):
        fake = FakeLLM(answers)
        monkeypatch.setattr(llm.httpx, "post", fake)
        return fake

    return install
