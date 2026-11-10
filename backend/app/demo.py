"""Demo server: catalogue products only, never fetches Flipkart. Run: uvicorn app.demo:app --port 8001"""

from app.scraper import fetcher

fetcher.DEMO_MODE = True

from app.main import app  # noqa: E402,F401  (imported after the flag so this process never scrapes)
