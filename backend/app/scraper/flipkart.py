import asyncio
from collections.abc import Callable
import logging
import random
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.schemas import RawReview, SpecGroup
from app.scraper.parser import parse_flipkart_aspects, parse_flipkart_html, parse_flipkart_product

logger = logging.getLogger(__name__)

USER_AGENTS = [
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
BLOCK_STATUSES = {403, 429}

MAX_REVIEWS = 50  # SPEC §D.3: the crawl's goal; stop as soon as this many unique reviews are read
MAX_PAGES = 8  # request cap: /product-reviews/?page=N shows 10 reviews per page, a few spare for duplicates
PAGE_RESERVE_SECONDS = 6.0  # stop early so the reviews already read come back inside the job's hard budget
PAGE_MIN_SECONDS = 4.0  # don't start a request with less time than this left
REQUEST_TIMEOUT_SECONDS = 20.0
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


def product_page_url(url: str) -> str:
    """Any product or reviews link → its product page: /<slug>/p/<itm>?pid=…"""
    parts = urlparse(url)
    path = parts.path.replace("/product-reviews/", "/p/", 1)
    query = {k: v[0] for k, v in parse_qs(parts.query).items() if k in ("pid", "lid")}
    return f"https://www.flipkart.com{path}?{urlencode(query)}"


async def _get(client, page_url: str, deadline: float) -> str:
    resp = await client.get(page_url, timeout=min(REQUEST_TIMEOUT_SECONDS, max(deadline - time.monotonic(), 1.0)))
    html = resp.text
    if resp.status_code in BLOCK_STATUSES or any(term in html.lower() for term in FLIPKART_CAPTCHA_STRINGS):
        raise ScrapeBlockedError(f"Flipkart CAPTCHA / bot wall detected (HTTP {resp.status_code})")
    resp.raise_for_status()
    return html


async def _collect(
    client, url: str, deadline: float, progress: Callable[[str], None] = lambda _: None, aspects: list[str] | None = None
) -> dict[str, RawReview]:
    """Requests review pages 1..MAX_PAGES; stops at MAX_REVIEWS, MAX_PAGES, the budget or a page with nothing new.

    Flipkart's aspect names from page 1 are appended to `aspects` when a list is passed.
    """
    reviews: dict[str, RawReview] = {}
    html = ""
    for n in range(1, MAX_PAGES + 1):
        if n > 1:
            if time.monotonic() + PAGE_MIN_SECONDS > deadline:
                break
            await asyncio.sleep(random.uniform(1, 2))
        try:
            html = await _get(client, reviews_page_url(url, n), deadline)
        except ScrapeBlockedError:
            raise
        except Exception:
            if not reviews:
                raise
            logger.warning("Flipkart review page %d failed; keeping %d reviews", n, len(reviews))
            break
        if n == 1 and aspects is not None:
            aspects.extend(parse_flipkart_aspects(html))
        new = {r.review_id: r for r in parse_flipkart_html(html, url) if r.review_id not in reviews}
        if not new:
            break  # past the last page: Flipkart repeats the last page or shows none
        reviews.update(new)
        progress(f"Fetching reviews from Flipkart ({min(len(reviews), MAX_REVIEWS)} so far)")
        if len(reviews) >= MAX_REVIEWS:
            break
    if not reviews:
        _keep_failed_page(html)
    return dict(list(reviews.items())[:MAX_REVIEWS])


async def _product_details(client, url: str, deadline: float) -> tuple[str | None, list[str], list[SpecGroup]]:
    """(title, image URLs, specs) from one product-page request (SPEC §D.3). Any failure, a block included, costs only these."""
    if time.monotonic() + PAGE_MIN_SECONDS > deadline:
        return None, [], []
    try:
        await asyncio.sleep(random.uniform(1, 2))
        return parse_flipkart_product(await _get(client, product_page_url(url), deadline))
    except Exception as exc:
        logger.warning("Flipkart product page failed (%s); keeping the reviews", exc)
        return None, [], []


def _keep_failed_page(html: str) -> None:
    """Saves the page that yielded no reviews (scripts kept: the JSON lives there), so a parser fix needs no new request."""
    try:
        FAILED_PAGE_PATH.write_text(html, encoding="utf-8")
        logger.warning("No reviews found; page saved to %s", FAILED_PAGE_PATH)
    except Exception:
        logger.exception("Could not save the failed Flipkart page")


async def scrape_flipkart_url(
    url: str, timeout: float = 90.0, progress: Callable[[str], None] = lambda _: None
) -> tuple[list[RawReview], list[str], str | None, list[str], list[SpecGroup]]:
    """Up to MAX_REVIEWS reviews from a product's all-reviews pages over plain HTTP (≤ MAX_PAGES requests),
    plus Flipkart's aspect names for the product and, from one product-page request, its title, image URLs and specs.

    Aborts immediately on CAPTCHA detection without retrying (SPEC §D.3).
    """
    deadline = time.monotonic() + timeout - PAGE_RESERVE_SECONDS
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-IN,en;q=0.9",
    }
    # IPv4 only: IPv6 to Flipkart stalled ~20 s per address on the dev machine before falling back.
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    async with httpx.AsyncClient(headers=headers, transport=transport, follow_redirects=True) as client:
        aspects: list[str] = []
        reviews = await _collect(client, url, deadline, progress, aspects)
        title, images, specs = await _product_details(client, url, deadline) if reviews else (None, [], [])
    return list(reviews.values()), aspects, title, images, specs
