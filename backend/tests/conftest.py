import pytest

from app.nlp import summarizer


@pytest.fixture(autouse=True)
def offline_llm(monkeypatch, tmp_path):
    """Keeps every test off the network and away from the real LLM answer cache."""
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY", "GROQ_MODEL", "GEMINI_MODEL", "LLM_PROVIDERS", "FORCE_FALLBACK"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(summarizer, "CACHE_PATH", tmp_path / "cache.sqlite")
