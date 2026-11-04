import asyncio
import logging
import os

from app.schemas import RawReview
from app.scraper.flipkart import ScrapeBlockedError, scrape_flipkart_url

logger = logging.getLogger(__name__)

LIVE_BUDGET_SECONDS = 90.0  # safety net for a stalled page (SPEC §D.1); the crawl normally ends at 50 reviews first
LIVE_SCRAPE_SLOTS = 2  # each scrape is a headless Chromium; more URL jobs wait here instead of exhausting the server
_live_slots = asyncio.Semaphore(LIVE_SCRAPE_SLOTS)


async def fetch_url_reviews(url: str) -> list[RawReview]:
    """One live attempt within the budget. Returns [] on block, timeout or any error; never raises."""
    if os.getenv("FORCE_FALLBACK", "0") == "1":
        return []
    try:
        # Own loop in a worker thread: uvicorn --reload on Windows runs a selector loop, where Playwright can't spawn its browser.
        async with _live_slots:  # waiting for a slot doesn't count against the budget
            return await asyncio.to_thread(
                lambda: asyncio.run(asyncio.wait_for(scrape_flipkart_url(url, timeout=LIVE_BUDGET_SECONDS), LIVE_BUDGET_SECONDS))
            )
    except (asyncio.TimeoutError, ScrapeBlockedError) as exc:
        logger.warning("Live scrape failed (%s)", exc)
    except Exception:
        logger.exception("Unexpected scraper error")
    return []
