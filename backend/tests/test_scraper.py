import asyncio
import json
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pathlib import Path

from app import catalogue
from app.catalogue import SEED_PATH
from app.schemas import RawReview
from app.scraper.fetcher import fetch_url_reviews
from app.scraper.flipkart import ScrapeBlockedError, _collect, reviews_page_url
from app.scraper.parser import parse_flipkart_html

SNAPSHOTS_DIR = Path(__file__).resolve().parent.parent / "app" / "scraper" / "snapshots"
URL = "https://www.flipkart.com/realme-buds-t310/p/itm123"


def test_parse_product_reviews_page_snapshot():
    """Real /product-reviews/ page (MSI Katana 15, saved 2026-10-30): the layout the live scraper reads."""
    html = (SNAPSHOTS_DIR / "flipkart_product_reviews_page.html").read_text(encoding="utf-8")
    reviews = parse_flipkart_html(html, product_query="msi katana", today=date(2026, 10, 30))

    assert len(reviews) == 10
    first = reviews[0]
    assert (first.rating, first.title, first.reviewer_name) == (5, "Best in the market!", "Flipkart Customer")
    assert first.text.startswith("Good laptop under the budget")
    assert "Review for:" not in first.text and not first.text.endswith("more")
    assert first.review_date == "2026-10-03"  # "· 27 days ago"
    assert first.helpful_votes == 15  # "Helpful for 15"
    assert reviews[2].review_date == "2025-09-01"  # "· Sep, 2025"
    assert reviews[2].helpful_votes == 18  # 👍 count, not the 👎 count next to it
    assert "😍" in reviews[1].text
    assert all(r.verified_purchase for r in reviews)  # "Verified Purchase"


def test_parse_live_flipkart_snapshot():
    """Real Flipkart markup (MSI Katana 15 reviews drawer, saved 2026-10-30): generated class names, relative dates."""
    html = (SNAPSHOTS_DIR / "flipkart_live_reviews.html").read_text(encoding="utf-8")
    reviews = parse_flipkart_html(html, product_query="msi katana", today=date(2026, 10, 30))

    assert len(reviews) == 8
    first = reviews[0]
    assert (first.rating, first.title, first.reviewer_name) == (5, "Best in the market!", "Flipkart Customer")
    assert first.text.startswith("Good laptop under the budget") and not first.text.endswith("more")
    assert first.review_date == "2026-10-02"  # "28 days ago"
    assert first.verified_purchase is True
    assert first.helpful_votes == 15
    assert "😍" in reviews[1].text  # emojis survive parsing
    assert [r.rating for r in reviews] == [5, 5, 5, 4, 5, 5, 4, 4]
    assert all(r.verified_purchase for r in reviews)


def test_parse_unverified_card_with_absolute_date():
    card = (
        "<div><div><div><div>2</div><div>Mic is bakwas 👎</div></div><div><div>12 Aug, 2026</div></div></div>"
        "<a><div>not good for calls... more</div></a>"
        "<div><div>Ramesh</div><div>1,204</div><div>3</div></div></div>"
    )
    [review] = parse_flipkart_html(card, product_query="x")
    assert (review.rating, review.title, review.text) == (2, "Mic is bakwas 👎", "not good for calls")
    assert review.review_date == "2026-08-12"
    assert review.verified_purchase is False
    assert review.helpful_votes == 1204


def test_reviews_page_url_from_product_link():
    product = "https://www.flipkart.com/msi-katana-15/p/itm46d7fa4f505a2?pid=COMHCQ4TNZJDSNGQ&lid=LSTX&ref=abc"
    assert reviews_page_url(product) == (
        "https://www.flipkart.com/msi-katana-15/product-reviews/itm46d7fa4f505a2"
        "?pid=COMHCQ4TNZJDSNGQ&lid=LSTX&marketplace=FLIPKART&page=1"
    )
    assert reviews_page_url(product, 3).endswith("&page=3")


class FakePage:
    """Stands in for a Playwright page: each content() call returns the next HTML, the last one repeats."""

    def __init__(self, htmls):
        self.htmls, self.gotos, self.url = list(htmls), [], "fake"

    async def goto(self, url, **_):
        self.gotos.append(url)

    def get_by_text(self, _):
        return SimpleNamespace(first=SimpleNamespace(wait_for=AsyncMock()))

    async def content(self):
        return self.htmls.pop(0) if len(self.htmls) > 1 else self.htmls[0]

    async def title(self):
        return "fake"


@pytest.mark.asyncio
async def test_collect_opens_pages_until_nothing_new(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    drawer = (SNAPSHOTS_DIR / "flipkart_live_reviews.html").read_text(encoding="utf-8")
    page_html = (SNAPSHOTS_DIR / "flipkart_product_reviews_page.html").read_text(encoding="utf-8")
    page = FakePage([drawer, page_html, page_html])

    reviews = await _collect(page, "https://www.flipkart.com/x/p/itm1?pid=P1", time.monotonic() + 60)

    assert [u.rsplit("page=", 1)[1] for u in page.gotos] == ["1", "2", "3"]  # page 3 added nothing new, so it stopped
    assert len(reviews) == 16  # 8 + 10, minus 2 short reviews identical in both layouts (deduplicated)


CARD = "<div><div><div><div>4</div><div>Review {n}</div></div><div><div>12 Aug, 2026</div></div></div>" \
       "<div>text {n}</div><div><div>Buyer {n}</div></div></div>"


@pytest.mark.asyncio
async def test_collect_stops_at_max_pages(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    page = FakePage([CARD.format(n=n) for n in range(10)])

    reviews = await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)

    assert len(page.gotos) == 8 and len(reviews) == 8


@pytest.mark.asyncio
async def test_collect_stops_at_50_reviews(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    pages = ["".join(CARD.format(n=p * 15 + i) for i in range(15)) for p in range(8)]
    page = FakePage(pages)

    reviews = await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)

    assert len(page.gotos) == 4  # 15 + 15 + 15 + 15 = 60 ≥ 50, so page 5 is never requested
    assert len(reviews) == 50 and list(reviews.values())[-1].title == "Review 49"  # trimmed, first 50 kept


@pytest.mark.asyncio
async def test_collect_rereads_until_cards_render(monkeypatch, tmp_path):
    """Live run 2026-10-30: the first read had no cards yet. That must not end the scrape."""
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("app.scraper.flipkart.FAILED_PAGE_PATH", tmp_path / "failed.html")
    drawer = (SNAPSHOTS_DIR / "flipkart_live_reviews.html").read_text(encoding="utf-8")
    page = FakePage(["<html><body>Hang on, loading content</body></html>", drawer, drawer])

    reviews = await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)

    assert len(reviews) == 8
    assert not (tmp_path / "failed.html").exists()


@pytest.mark.asyncio
async def test_collect_saves_page_when_no_cards(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("app.scraper.flipkart.FAILED_PAGE_PATH", tmp_path / "failed.html")
    page = FakePage(["<html><script>x()</script><body>nothing here</body></html>"])

    assert await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60) == {}
    assert len(page.gotos) == 1  # an empty first page ends the scrape; later pages would be empty too
    saved = (tmp_path / "failed.html").read_text(encoding="utf-8")
    assert "nothing here" in saved and "<script" not in saved


@pytest.mark.asyncio
async def test_collect_raises_on_captcha():
    page = FakePage(["<html>Are you a human?</html>"])
    with pytest.raises(ScrapeBlockedError):
        await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)


@pytest.mark.asyncio
async def test_collect_raises_on_stripped_item_page():
    """Live 2026-11-03: Flipkart served the headless browser a generic 'Item Reviews' page with no cards."""
    page = FakePage(["<title>Item Reviews: Latest Review of Item | Price in India | Flipkart.com</title>"])
    with pytest.raises(ScrapeBlockedError):
        await _collect(page, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)
    assert len(page.gotos) == 1


def test_catalogue_lists_seed_products():
    ids = {p.id for p in catalogue.list_products()}
    assert {"realme-buds-t310", "oneplus-nord-buds-3-pro", "sony-wf-c700n"} <= ids
    item, reviews = catalogue.get_product("realme-buds-t310")
    assert item.review_count == len(reviews) >= 24
    assert catalogue.get_product("unknown-product") is None


def test_catalogue_matches_flipkart_url_slug():
    assert catalogue.match_product("/realme-buds-t310-with-46db-anc/p/itm123") == "realme-buds-t310"
    assert catalogue.match_product("/boat-airdopes-141/p/itm999") is None


@pytest.mark.asyncio
async def test_fetcher_returns_live_reviews():
    live = [RawReview(review_id="fk_live_1", product_query="x", rating=4, text="Bass is mast", review_date="2026-09-01")]
    with patch("app.scraper.fetcher.scrape_flipkart_url", return_value=live):
        assert await fetch_url_reviews(URL) == live


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [asyncio.TimeoutError(), ScrapeBlockedError("CAPTCHA"), RuntimeError("boom"), []],
    ids=["timeout", "captcha", "unexpected_error", "empty_result"],
)
async def test_fetcher_never_raises(outcome):
    """Timeout, CAPTCHA, any error or an empty page all give [] so the job can fall back (SPEC §D)."""
    kwargs = {"return_value": outcome} if isinstance(outcome, list) else {"side_effect": outcome}
    with patch("app.scraper.fetcher.scrape_flipkart_url", **kwargs) as scraper:
        assert await fetch_url_reviews(URL) == []
    scraper.assert_called_once()  # one attempt, no retries


def test_fetcher_scrapes_on_its_own_loop_under_selector_loop():
    """uvicorn --reload on Windows runs a selector loop; the scrape must not depend on the caller's loop type."""
    seen = []

    async def fake_scrape(url, timeout):
        seen.append(type(asyncio.get_running_loop()).__name__)
        return ["ok"]

    loop = asyncio.SelectorEventLoop()
    with patch("app.scraper.fetcher.scrape_flipkart_url", fake_scrape):
        assert loop.run_until_complete(fetch_url_reviews(URL)) == ["ok"]
    loop.close()
    assert seen != ["_WindowsSelectorEventLoop"]  # a subprocess-capable loop (Proactor on Windows)


@pytest.mark.asyncio
async def test_live_scrapes_are_capped(monkeypatch):
    """Only LIVE_SCRAPE_SLOTS browsers run at once; the rest wait their turn."""
    running, peak = 0, 0

    async def fake_scrape(url, timeout):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return []

    monkeypatch.setattr("app.scraper.fetcher._live_slots", asyncio.Semaphore(2))
    with patch("app.scraper.fetcher.scrape_flipkart_url", fake_scrape):
        await asyncio.gather(*(fetch_url_reviews(URL) for _ in range(5)))
    assert peak == 2


@pytest.mark.asyncio
async def test_force_fallback_skips_live_scrape(monkeypatch):
    monkeypatch.setenv("FORCE_FALLBACK", "1")
    with patch("app.scraper.fetcher.scrape_flipkart_url") as scraper:
        assert await fetch_url_reviews(URL) == []
    scraper.assert_not_called()


def test_seed_dataset_integrity():
    """seed_reviews.json holds >= 3 Flipkart-only products with >= 20 unique, valid reviews each."""
    assert SEED_PATH.exists()
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert set(data) == {"products"}

    products = data["products"]
    assert {"realme buds t310", "oneplus nord buds 3 pro", "sony wf-c700n"} <= set(products)

    total_count = 0
    for prod_name, prod_info in products.items():
        reviews = prod_info["reviews"]
        assert len(reviews) >= 20, f"{prod_name} needs at least 20 reviews"
        ids = [r["review_id"] for r in reviews]
        assert len(ids) == len(set(ids)), f"{prod_name} has duplicate review ids"
        for item in reviews:
            raw_rev = RawReview.model_validate(item)
            assert raw_rev.platform == "flipkart"
            assert 1 <= raw_rev.rating <= 5
        total_count += len(reviews)

    assert total_count >= 60
