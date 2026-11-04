import asyncio
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from app.schemas import RawReview
from app.scraper.parser import parse_flipkart_html

logger = logging.getLogger(__name__)

USER_AGENTS = [  # Chrome only: the browser is Chromium, and a Firefox UA on it is an easy bot signal
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
]

FLIPKART_CAPTCHA_STRINGS = [
    "are you a human",
    "access to this page has been denied",
    "please verify you are a human",
    "automated requests",
    "latest review of item |",  # stripped "Item Reviews" page Flipkart serves suspected bots: no cards, no CAPTCHA
]

MAX_REVIEWS = 50  # SPEC §D.3: the crawl's goal; stop as soon as this many unique reviews are read
MAX_PAGES = 8  # request cap: /product-reviews/?page=N shows 10 reviews per page, a few spare for duplicates
PAGE_RESERVE_SECONDS = 6.0  # stop early so the reviews already read come back inside the job's hard budget
PAGE_MIN_SECONDS = 4.0  # don't start a page load with less time than this left
BADGE_TEXT = re.compile(r"Verified (Purchase|Buyer)|Certified Buyer")
FAILED_PAGE_PATH = Path(__file__).resolve().parents[1] / "data" / "last_failed_scrape.html"  # gitignored


class ScrapeBlockedError(Exception):
    """Raised when a CAPTCHA or blocking wall is encountered."""


def reviews_page_url(url: str, page: int = 1) -> str:
    """Product link → page N of its all-reviews: /<slug>/p/<itm>?pid=… becomes /<slug>/product-reviews/<itm>?pid=…&page=N"""
    parts = urlparse(url)
    path = parts.path.replace("/p/", "/product-reviews/", 1)
    query = {k: v[0] for k, v in parse_qs(parts.query).items() if k in ("pid", "lid")}
    query.update(marketplace="FLIPKART", page=str(page))
    return f"https://www.flipkart.com{path}?{urlencode(query)}"


async def _open(page, url: str, timeout: float) -> None:
    await page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
    try:  # reviews render client-side; a buyer badge appearing means the cards are in the DOM
        await page.get_by_text(BADGE_TEXT).first.wait_for(timeout=min(8000, int(timeout * 1000)))
    except Exception:
        pass  # only unverified reviews, or none at all; parse whatever rendered


async def _read(page) -> str:
    content = await page.content()
    if any(term in content.lower() for term in FLIPKART_CAPTCHA_STRINGS):
        raise ScrapeBlockedError("Flipkart CAPTCHA / bot verification detected")
    return content


async def _read_page(page, page_url: str, url: str, deadline: float) -> list[RawReview]:
    await _open(page, page_url, deadline - time.monotonic())
    found = parse_flipkart_html(await _read(page), url)
    if not found:  # cards can render after the badge wait gives up; look at the same page once more, no new request
        await asyncio.sleep(1.5)
        found = parse_flipkart_html(await _read(page), url)
    return found


async def _collect(page, url: str, deadline: float) -> dict[str, RawReview]:
    """Opens review pages 1..MAX_PAGES by URL; stops at MAX_REVIEWS, MAX_PAGES, the budget or a page with nothing new."""
    reviews: dict[str, RawReview] = {}
    for n in range(1, MAX_PAGES + 1):
        if n > 1:
            if time.monotonic() + PAGE_MIN_SECONDS > deadline:
                break
            await asyncio.sleep(random.uniform(1, 2))
        try:
            found = await _read_page(page, reviews_page_url(url, n), url, deadline)
        except ScrapeBlockedError:
            raise
        except Exception:
            if not reviews:
                raise
            logger.warning("Flipkart review page %d failed; keeping %d reviews", n, len(reviews))
            break
        new = {r.review_id: r for r in found if r.review_id not in reviews}
        if not new:
            break  # past the last page: Flipkart repeats the last page or shows none
        reviews.update(new)
        if len(reviews) >= MAX_REVIEWS:
            break
    if not reviews:
        await _keep_failed_page(page)
    return dict(list(reviews.items())[:MAX_REVIEWS])


async def _keep_failed_page(page) -> None:
    """Saves the page that yielded no cards, so a parser fix can start from it without another live request."""
    try:
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", await page.content(), flags=re.S | re.I)
        FAILED_PAGE_PATH.write_text(html, encoding="utf-8")
        logger.warning("No review cards on %s (title %r); page saved to %s", page.url, await page.title(), FAILED_PAGE_PATH)
    except Exception:
        logger.exception("Could not save the failed Flipkart page")


async def scrape_flipkart_url(url: str, timeout: float = 90.0) -> list[RawReview]:
    """Reads up to MAX_REVIEWS reviews from a product's all-reviews pages with Playwright, one browser, ≤ MAX_PAGES loads.

    Aborts immediately on CAPTCHA detection without retrying (SPEC §D.3).
    shortcut: long reviews keep Flipkart's "... more" cut-off; click each "more" if full text matters.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed; cannot scrape live Flipkart")
        return []

    deadline = time.monotonic() + timeout - PAGE_RESERVE_SECONDS
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS), viewport={"width": 1280, "height": 900}, locale="en-IN"
            )
            reviews = await _collect(await context.new_page(), url, deadline)
        finally:
            await browser.close()
    return list(reviews.values())
