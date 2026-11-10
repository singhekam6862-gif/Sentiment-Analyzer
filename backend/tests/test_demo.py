import importlib

from app.scraper import fetcher


def test_live_app_ignores_stale_force_fallback(monkeypatch):
    monkeypatch.setenv("FORCE_FALLBACK", "1")
    importlib.reload(fetcher)
    assert fetcher.DEMO_MODE is False


def test_demo_app_turns_live_fetching_off(monkeypatch):
    monkeypatch.setattr(fetcher, "DEMO_MODE", False)
    importlib.reload(importlib.import_module("app.demo"))
    assert fetcher.DEMO_MODE is True
