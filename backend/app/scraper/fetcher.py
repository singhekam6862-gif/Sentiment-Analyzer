import asyncio
import logging
from typing import Any

from app.scraper.flipkart import ScrapeBlockedError, scrape_flipkart
from app.scraper.hybrid_scraper import SCRAPE_TIMEOUT_SECONDS, load_seed_reviews

logger = logging.getLogger(__name__)


async def fetch_reviews(query: str) -> tuple[list[dict[str, Any]], str]:
    """Return (reviews, data_source). Never raises on scrape failure (SPEC §D.3)."""
    try:
        reviews = await asyncio.wait_for(
            scrape_flipkart(query, timeout=SCRAPE_TIMEOUT_SECONDS), timeout=SCRAPE_TIMEOUT_SECONDS
        )
        if not reviews:
            raise ScrapeBlockedError("empty result")
        return [r.model_dump() for r in reviews], "live_scrape"
    except (asyncio.TimeoutError, ScrapeBlockedError) as exc:
        logger.warning("Live scrape failed (%s); using fallback", exc)
    except Exception:
        logger.exception("Unexpected scraper error; using fallback")

    return [r.model_dump() for r in load_seed_reviews(query)], "cached_fallback"
