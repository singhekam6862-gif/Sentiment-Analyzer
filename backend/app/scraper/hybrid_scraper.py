import asyncio
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Literal

from app.schemas import RawReview
from app.scraper.flipkart import ScrapeBlockedError, scrape_flipkart
from app.scraper.parser import parse_flipkart_html

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT_SECONDS = 8.0
BASE_DIR = Path(__file__).resolve().parent
SNAPSHOTS_DIR = BASE_DIR / "snapshots"
SEED_PATH = BASE_DIR.parent / "data" / "seed_reviews.json"


@dataclass
class ScrapeResult:
    """Reviews for one product plus where they came from."""

    reviews: list[RawReview]
    data_source: Literal["live_scrape", "cached_fallback"]
    query: str = ""


def _match_product_key(query: str, available_keys: list[str]) -> str | None:
    """Fuzzy match product search query against seed dataset product keys."""
    q_norm = query.lower().strip()
    if not q_norm or not available_keys:
        return None

    # Exact or substring match
    for key in available_keys:
        if key == q_norm or key in q_norm or q_norm in key:
            return key

    # Token overlap score
    q_tokens = set(q_norm.replace("-", " ").split())
    best_key = None
    best_score = 0

    for key in available_keys:
        key_tokens = set(key.replace("-", " ").split())
        overlap = len(q_tokens.intersection(key_tokens))
        if overlap > best_score:
            best_score = overlap
            best_key = key

    return best_key if best_score > 0 else None


def load_seed_reviews(query: str = "realme buds t310") -> list[RawReview]:
    """Loads the matching product's reviews from seed_reviews.json."""
    if not SEED_PATH.exists():
        logger.error("seed_reviews.json not found at %s", SEED_PATH)
        return []

    try:
        data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to parse seed_reviews.json: %s", exc)
        return []

    products_dict = data.get("products", {})
    matched_key = _match_product_key(query, list(products_dict.keys()))
    if not matched_key:
        return []

    return [RawReview.model_validate(r) for r in products_dict[matched_key].get("reviews", [])]


def load_snapshot_reviews(query: str = "realme buds t310") -> list[RawReview]:
    """Loads reviews from the static Flipkart HTML snapshot for offline testing."""
    fk_path = SNAPSHOTS_DIR / "flipkart_sample.html"
    if not fk_path.exists():
        return []
    return parse_flipkart_html(fk_path.read_text(encoding="utf-8"), product_query=query)


async def fetch_product_reviews(query: str, mode: str = "hybrid") -> ScrapeResult:
    """Fetch Flipkart reviews for a product query.

    Modes:
      - 'offline': loads matching reviews from seed_reviews.json.
      - 'snapshot': parses the local flipkart_sample.html.
      - 'hybrid': attempts a live scrape with an 8s timeout, falling back to the seed on block/timeout/empty.
    """
    mode_clean = mode.lower().strip()

    # Respect FORCE_FALLBACK environment variable for presentations/CI
    if os.getenv("FORCE_FALLBACK", "0") == "1" and mode_clean == "hybrid":
        mode_clean = "offline"

    if mode_clean == "offline":
        return ScrapeResult(load_seed_reviews(query), "cached_fallback", query)

    if mode_clean == "snapshot":
        return ScrapeResult(load_snapshot_reviews(query), "cached_fallback", query)

    try:
        reviews = await asyncio.wait_for(
            scrape_flipkart(query, timeout=SCRAPE_TIMEOUT_SECONDS), timeout=SCRAPE_TIMEOUT_SECONDS
        )
        if reviews:
            return ScrapeResult(reviews, "live_scrape", query)
        logger.warning("Flipkart live scrape returned no reviews; using seed fallback")
    except (asyncio.TimeoutError, ScrapeBlockedError) as exc:
        logger.warning("Flipkart live scrape failed (%s); using seed fallback", exc)
    except Exception:
        logger.exception("Unexpected Flipkart scraper error; using seed fallback")

    return ScrapeResult(load_seed_reviews(query), "cached_fallback", query)
