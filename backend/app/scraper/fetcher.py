import asyncio
from collections.abc import Callable
import logging
import os

from app.schemas import RawReview, SpecGroup
from app.scraper.flipkart import ScrapeBlockedError, scrape_flipkart_url

logger = logging.getLogger(__name__)

LIVE_BUDGET_SECONDS = 90.0  # safety net for a stalled page (SPEC §D.1); the crawl normally ends at 50 reviews first
LIVE_SCRAPE_SLOTS = 2  # SPEC §C.2: more URL jobs wait here, so the server never hits Flipkart from many crawls at once
_live_slots = asyncio.Semaphore(LIVE_SCRAPE_SLOTS)


async def fetch_url_reviews(
    url: str, progress: Callable[[str], None] = lambda _: None
) -> tuple[list[RawReview], list[str], str | None, list[str], list[SpecGroup]]:
    """One live attempt within the budget: (reviews, Flipkart aspect names, title, image URLs, specs).
    ([], [], None, [], []) on block, timeout or any error; never raises."""
    if os.getenv("FORCE_FALLBACK", "0") == "1":
        return [], [], None, [], []
    try:
        async with _live_slots:  # waiting for a slot doesn't count against the budget
            return await asyncio.wait_for(scrape_flipkart_url(url, timeout=LIVE_BUDGET_SECONDS, progress=progress), LIVE_BUDGET_SECONDS)
    except (asyncio.TimeoutError, ScrapeBlockedError) as exc:
        logger.warning("Live scrape failed (%s)", exc)
    except Exception:
        logger.exception("Unexpected scraper error")
    return [], [], None, [], []
