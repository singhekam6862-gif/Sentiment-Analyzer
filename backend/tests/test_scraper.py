import asyncio
import json
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from pathlib import Path

from app import catalogue, jobs
from app.catalogue import SEED_PATH
from app.schemas import AnalysisJob, RawReview, SpecGroup, SpecItem
from app.scraper.fetcher import fetch_url_reviews
from app.scraper.flipkart import ScrapeBlockedError, _collect, _product_details, product_page_url, reviews_page_url
from app.scraper.parser import MAX_IMAGES, parse_flipkart_aspects, parse_flipkart_html, parse_flipkart_product, parse_flipkart_state

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


def test_parse_state_snapshot():
    """Real /product-reviews/ page over plain HTTP (MSI Katana 15, saved 2026-11-04, session ids redacted)."""
    html = (SNAPSHOTS_DIR / "flipkart_reviews_state.html").read_text(encoding="utf-8")
    reviews = parse_flipkart_state(html, product_query="msi katana", today=date(2026, 11, 4))

    assert len(reviews) == 10
    first = reviews[0]
    assert first.review_id == "fk_4a8722aa-69d4-4e1c-8f82-0d8759b1f19a"
    assert (first.rating, first.title, first.reviewer_name) == (5, "Best in the market!", "Flipkart Customer")
    assert first.text.endswith("Graphics and build quality is very good .")  # full text, no "... more" cut-off
    assert (first.helpful_votes, first.verified_purchase, first.review_date) == (16, True, "2026-10-05")
    assert "😍" in reviews[1].text
    assert parse_flipkart_html(html, "msi katana", date(2026, 11, 4)) == reviews  # the JSON path is the one used


def test_parse_flipkart_aspect_names_snapshot():
    """Flipkart's review filter tabs name the product's aspects; "Overall" is not one."""
    html = (SNAPSHOTS_DIR / "flipkart_reviews_state.html").read_text(encoding="utf-8")
    assert parse_flipkart_aspects(html) == [
        "performance", "battery", "design", "display", "value_for_money", "design_features", "sound_quality",
    ]
    assert parse_flipkart_aspects("<html>no state</html>") == []


def state_page(*reviews) -> str:
    """A page with Flipkart's embedded state, reviews nested the way the real page nests them."""
    state = {"pageDataV4": {"page": {"data": {"1": [{"widget": {"data": {"renderableComponents": [
        {"value": r} for r in reviews] + [{"value": {"type": "RatingValue", "rating": 1}}]}}}]}}}}
    return f"<html><head><script>window.__INITIAL_STATE__ = {json.dumps(state)};</script></head><body></body></html>"


def review_json(n, **extra):
    return {"type": "ProductReviewValue", "id": f"R{n}", "rating": 4, "title": f"Review {n}",
            "text": f"Battery is mast, not bad 👍 {n}", "created": "6 months ago", "certifiedBuyer": True, **extra}


def test_parse_embedded_state():
    html = state_page(
        review_json(1, author="Asha", helpfulCount=12, location={"city": "Pune"}),
        review_json(2, certifiedBuyer=False, created="Sep, 2025", helpfulCount=3),
        review_json(3, rating=9),  # invalid rating: skipped, not fatal
        review_json(4, text="", title=""),  # nothing to analyse: skipped
        review_json(1),  # same review twice in the state: kept once
    )
    reviews = parse_flipkart_html(html, product_query="x", today=date(2026, 11, 4))

    assert [r.review_id for r in reviews] == ["fk_R1", "fk_R2"]
    first, second = reviews
    assert (first.reviewer_name, first.helpful_votes, first.verified_purchase) == ("Asha", 12, True)
    assert first.text == "Battery is mast, not bad 👍 1"  # negations and emojis kept
    assert first.review_date == "2026-05-08"  # "6 months ago"
    assert (second.verified_purchase, second.review_date, second.helpful_votes) == (False, "2025-09-01", 3)


def test_state_wins_over_cards_and_cards_are_the_fallback():
    card = CARD.format(n=0)
    assert [r.title for r in parse_flipkart_html(state_page(review_json(7)) + card, "x")] == ["Review 7"]
    assert [r.title for r in parse_flipkart_html(card, "x")] == ["Review 0"]
    assert parse_flipkart_html("<script>window.__INITIAL_STATE__ = {broken;</script>" + card, "x")[0].title == "Review 0"


class FakeClient:
    """Stands in for httpx.AsyncClient: each get() returns the next page, the last one repeats."""

    def __init__(self, htmls, status=200):
        self.htmls, self.gotos, self.status = list(htmls), [], status

    async def get(self, url, **_):
        self.gotos.append(url)
        html = self.htmls.pop(0) if len(self.htmls) > 1 else self.htmls[0]
        return SimpleNamespace(status_code=self.status, text=html, raise_for_status=lambda: None)


@pytest.mark.asyncio
async def test_collect_opens_pages_until_nothing_new(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    drawer = (SNAPSHOTS_DIR / "flipkart_live_reviews.html").read_text(encoding="utf-8")
    page_html = (SNAPSHOTS_DIR / "flipkart_product_reviews_page.html").read_text(encoding="utf-8")
    client = FakeClient([drawer, page_html, page_html])

    reviews = await _collect(client, "https://www.flipkart.com/x/p/itm1?pid=P1", time.monotonic() + 60)

    assert [u.rsplit("page=", 1)[1] for u in client.gotos] == ["1", "2", "3"]  # page 3 added nothing new, so it stopped
    assert len(reviews) == 16  # 8 + 10, minus 2 short reviews identical in both layouts (deduplicated)


CARD = "<div><div><div><div>4</div><div>Review {n}</div></div><div><div>12 Aug, 2026</div></div></div>" \
       "<div>text {n}</div><div><div>Buyer {n}</div></div></div>"


@pytest.mark.asyncio
async def test_collect_stops_at_max_pages(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    client = FakeClient([CARD.format(n=n) for n in range(10)])

    reviews = await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)

    assert len(client.gotos) == 8 and len(reviews) == 8


@pytest.mark.asyncio
async def test_collect_stops_at_50_reviews(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    pages = ["".join(CARD.format(n=p * 15 + i) for i in range(15)) for p in range(8)]
    client = FakeClient(pages)

    reviews = await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)

    assert len(client.gotos) == 4  # 15 + 15 + 15 + 15 = 60 ≥ 50, so page 5 is never requested
    assert len(reviews) == 50 and list(reviews.values())[-1].title == "Review 49"  # trimmed, first 50 kept


@pytest.mark.asyncio
async def test_collect_saves_page_when_no_cards(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    monkeypatch.setattr("app.scraper.flipkart.FAILED_PAGE_PATH", tmp_path / "failed.html")
    client = FakeClient(["<html><script>x()</script><body>nothing here</body></html>"])

    assert await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60) == {}
    assert len(client.gotos) == 1  # an empty first page ends the scrape; later pages would be empty too
    saved = (tmp_path / "failed.html").read_text(encoding="utf-8")
    assert "nothing here" in saved and "x()" in saved  # scripts kept: the embedded JSON lives there


@pytest.mark.asyncio
async def test_collect_reads_embedded_state_across_pages(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    pages = [state_page(*(review_json(p * 10 + i) for i in range(10))) for p in range(2)]
    client = FakeClient(pages + [pages[-1]])

    reviews = await _collect(client, "https://www.flipkart.com/x/p/itm1?pid=P1", time.monotonic() + 60)

    assert len(reviews) == 20 and len(client.gotos) == 3  # page 3 repeats page 2, so it stopped


@pytest.mark.asyncio
async def test_collect_reads_aspect_names_from_page_one(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    tab = lambda name: {"type": "UgcAspectTabValue", "name": name}
    pages = [state_page(review_json(1), tab("Overall"), tab("Sound Quality"), tab("Battery")),
             state_page(review_json(2), tab("Comfort"))]
    client = FakeClient(pages)
    aspects: list[str] = []

    await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60, aspects=aspects)

    assert aspects == ["sound_quality", "battery"]  # page 1 only


@pytest.mark.asyncio
async def test_collect_raises_on_captcha():
    client = FakeClient(["<html>Are you a human?</html>"])
    with pytest.raises(ScrapeBlockedError):
        await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [403, 429])
async def test_collect_raises_on_block_status(status):
    client = FakeClient(["<html>blocked</html>"], status=status)
    with pytest.raises(ScrapeBlockedError):
        await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)
    assert len(client.gotos) == 1  # no retry


@pytest.mark.asyncio
async def test_collect_raises_on_stripped_item_page():
    """Live 2026-11-03: Flipkart served a suspected bot a generic 'Item Reviews' page with no cards."""
    client = FakeClient(["<title>Item Reviews: Latest Review of Item | Price in India | Flipkart.com</title>"])
    with pytest.raises(ScrapeBlockedError):
        await _collect(client, "https://www.flipkart.com/x/p/itm1", time.monotonic() + 60)
    assert len(client.gotos) == 1


def og_page(title="", image=""):
    return f'<html><head><meta property="og:title" content="{title}"><meta property="og:image" content="{image}"></head></html>'


def test_parse_product_page_snapshot():
    """Real product page (MSI Katana 15): the title stops before the price, the image is Flipkart's own."""
    html = (SNAPSHOTS_DIR / "flipkart_live_reviews.html").read_text(encoding="utf-8")
    title, images, specs = parse_flipkart_product(html)
    assert title.startswith("MSI Katana 15 Intel Core i5") and title.endswith("Katana 15 B13UDXK Gaming Laptop")
    assert images == ["https://rukminim2.flixcart.com/image/300/300/xif0q/computer/u/z/z/-original-imahgfdfhgfddc5j.jpeg"]
    assert specs == []  # this copy has no state JSON: the single og:image is all it can give


def test_parse_product_state_snapshot():
    """Real plain-HTTP product page (MSI Katana 15, 2026-11-06): the whole gallery and spec table."""
    html = (SNAPSHOTS_DIR / "flipkart_product_state.html").read_text(encoding="utf-8")
    title, images, specs = parse_flipkart_product(html)
    assert title.startswith("MSI Katana 15")
    assert len(images) == 9
    assert images[0] == "https://rukminim1.flixcart.com/image/800/800/xif0q/computer/u/z/z/-original-imahgfdfhgfddc5j.jpeg?q=80"
    assert [g.name for g in specs][:3] == ["Processor and Memory Features", "In the Box", "General"]
    assert sum(len(g.items) for g in specs) == 66
    assert specs[1].items[0] == SpecItem(name="Sales Package", value="Laptop, Charger, User Guide, MSI Laptop Bag")


def _state_page(items=None, groups=None):
    state = {"multiMediaViewData_0": {"value": items or []}, "rpd_specifications_grid_layout_1": {"value": {"gridData_0": {"value": groups or []}}}}
    return f"<html><script>window.__INITIAL_STATE__ = {json.dumps(state)};</script></html>"


def _media(url, content_type="IMAGE"):
    return {"value": {"image_0": {"value": {"selected": {"value": {"dynamicImageUrl": url, "contentType": content_type}}}}}}


def test_gallery_keeps_only_flipkart_photos():
    good = "https://rukminim1.flixcart.com/image/{@width}/{@height}/a.jpeg?q={@quality}"
    items = [_media(good), _media(good), _media("https://rukminim1.flixcart.com/v.mp4", "VIDEO"), _media("https://evil.example/a.jpg"), {"value": {}}, "junk"]
    assert parse_flipkart_product(_state_page(items))[1] == ["https://rukminim1.flixcart.com/image/800/800/a.jpeg?q=80"]


def test_gallery_is_capped():
    items = [_media(f"https://rukminim1.flixcart.com/image/{n}.jpeg") for n in range(MAX_IMAGES + 3)]
    assert len(parse_flipkart_product(_state_page(items))[1]) == MAX_IMAGES


def test_specs_skip_malformed_rows_and_empty_groups():
    def row(name, value):
        return {"value": {"label_0": {"value": {"text": name}}, "label_1": {"value": {"text": value}}}}

    def group(name, *rows):
        return {"value": {"label_0": {"value": {"text": name}}, "rpd_grid_0": {"value": {"gridData_0": {"value": list(rows)}}}}}

    groups = [group("Ok", row("RAM", ["16 GB", "DDR5"]), row("Colour", "Black"), row("", ["x"]), row("Empty", []), row("Bad", 5), "junk"),
              group("Nothing inside"), "junk"]
    specs = parse_flipkart_product(_state_page(groups=groups))[2]
    assert specs == [SpecGroup(name="Ok", items=[SpecItem(name="RAM", value="16 GB, DDR5"), SpecItem(name="Colour", value="Black")])]


def test_og_image_is_the_fallback_when_the_gallery_is_empty():
    html = _state_page() + og_page(image="https://rukminim1.flixcart.com/image/1.jpeg")
    assert parse_flipkart_product(html)[1] == ["https://rukminim1.flixcart.com/image/1.jpeg"]


@pytest.mark.parametrize(
    "image",
    ["http://rukminim2.flixcart.com/a.jpg", "https://evil.example/a.jpg", "https://rukminim2.flixcart.com.evil.example/a.jpg",
     "javascript:alert(1)", ""],
)
def test_product_image_must_be_on_flipkart_cdn(image):
    assert parse_flipkart_product(og_page(image=image))[1] == []


def test_product_title_needs_the_price_tail():
    assert parse_flipkart_product(og_page("Dot Key Moisturizer - Price in India, Buy Online"))[0] == "Dot Key Moisturizer"
    assert parse_flipkart_product(og_page("Online Shopping Site for Mobiles"))[0] is None  # not a product's page
    assert parse_flipkart_product("<html></html>") == (None, [], [])


def test_product_page_url_from_any_link():
    assert product_page_url("https://www.flipkart.com/x/p/itm1?pid=P1&ref=abc") == "https://www.flipkart.com/x/p/itm1?pid=P1"
    assert product_page_url("https://www.flipkart.com/x/product-reviews/itm1?pid=P1&page=2") == "https://www.flipkart.com/x/p/itm1?pid=P1"


@pytest.mark.asyncio
async def test_product_details_reads_one_page(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    client = FakeClient([og_page("Buds - Price in India", "https://rukminim1.flixcart.com/image/1.jpeg")])
    details = await _product_details(client, URL, time.monotonic() + 60)
    assert details == ("Buds", ["https://rukminim1.flixcart.com/image/1.jpeg"], [])
    assert client.gotos == [URL + "?"]


@pytest.mark.asyncio
async def test_product_details_block_costs_only_the_details(monkeypatch):
    monkeypatch.setattr("app.scraper.flipkart.asyncio.sleep", AsyncMock())
    client = FakeClient(["<html>Are you a human?</html>"])
    assert await _product_details(client, URL, time.monotonic() + 60) == (None, [], [])
    assert len(client.gotos) == 1  # no retry


@pytest.mark.asyncio
async def test_product_details_skipped_when_budget_is_spent():
    client = FakeClient(["<html></html>"])
    assert await _product_details(client, URL, time.monotonic() + 1) == (None, [], [])
    assert client.gotos == []


def _live_review():
    return RawReview(review_id="fk_1", product_query="x", rating=4, text="Bass is mast", review_date="2026-09-01")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "title, images, specs, name",
    [("Acme Buds", ["https://rukminim2.flixcart.com/image/1.jpeg"], [SpecGroup(name="General", items=[SpecItem(name="Brand", value="Acme")])], "Acme Buds"),
     (None, [], [], "realme buds t310")],  # product page failed: the name comes from the link, and there are no details
    ids=["product_page", "product_page_failed"],
)
async def test_url_job_uses_product_details(title, images, specs, name):
    jobs.JOBS["j"] = AnalysisJob(job_id="j", status="queued", message="")
    with patch("app.jobs.fetch_url_reviews", AsyncMock(return_value=([_live_review()], [], title, images, specs))):
        product, reviews, _ = await jobs._url_source("j", URL)
    assert (product.name, product.images, product.specs, product.data_source) == (name, images, specs, "live_scrape")
    assert len(reviews) == 1  # the reviews survive either way


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
    result = (live, ["battery"], "Realme Buds", ["https://rukminim2.flixcart.com/image/1.jpeg"], [])
    with patch("app.scraper.fetcher.scrape_flipkart_url", return_value=result):
        assert await fetch_url_reviews(URL) == result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [asyncio.TimeoutError(), ScrapeBlockedError("CAPTCHA"), RuntimeError("boom"), ([], [], None, [], [])],
    ids=["timeout", "captcha", "unexpected_error", "empty_result"],
)
async def test_fetcher_never_raises(outcome):
    """Timeout, CAPTCHA, any error or an empty page all give [] so the job can fall back (SPEC §D)."""
    kwargs = {"return_value": outcome} if isinstance(outcome, tuple) else {"side_effect": outcome}
    with patch("app.scraper.fetcher.scrape_flipkart_url", **kwargs) as scraper:
        assert await fetch_url_reviews(URL) == ([], [], None, [], [])
    scraper.assert_called_once()  # one attempt, no retries


@pytest.mark.asyncio
async def test_live_scrapes_are_capped(monkeypatch):
    """Only LIVE_SCRAPE_SLOTS browsers run at once; the rest wait their turn."""
    running, peak = 0, 0

    async def fake_scrape(url, timeout, **_):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.05)
        running -= 1
        return [], [], None, [], []

    monkeypatch.setattr("app.scraper.fetcher._live_slots", asyncio.Semaphore(2))
    with patch("app.scraper.fetcher.scrape_flipkart_url", fake_scrape):
        await asyncio.gather(*(fetch_url_reviews(URL) for _ in range(5)))
    assert peak == 2


@pytest.mark.asyncio
async def test_force_fallback_skips_live_scrape(monkeypatch):
    monkeypatch.setenv("FORCE_FALLBACK", "1")
    with patch("app.scraper.fetcher.scrape_flipkart_url") as scraper:
        assert await fetch_url_reviews(URL) == ([], [], None, [], [])
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
