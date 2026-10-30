import asyncio
import json
from unittest.mock import patch

import pytest

from app.schemas import RawReview
from app.scraper.fetcher import fetch_reviews
from app.scraper.flipkart import ScrapeBlockedError
from app.scraper.hybrid_scraper import (
    SNAPSHOTS_DIR,
    SEED_PATH,
    fetch_product_reviews,
    load_seed_reviews,
)
from app.scraper.parser import parse_flipkart_html


def test_parse_flipkart_snapshot():
    """Verify parse_flipkart_html extracts rating, text, Hinglish/emojis, and certified buyer badges."""
    sample_file = SNAPSHOTS_DIR / "flipkart_sample.html"
    assert sample_file.exists(), "flipkart_sample.html snapshot must exist"

    html = sample_file.read_text(encoding="utf-8")
    reviews = parse_flipkart_html(html, product_query="realme buds t310")

    assert len(reviews) >= 5

    # Check Review 1: Certified Buyer, Hinglish, Emojis, 42 upvotes
    rev1 = reviews[0]
    assert rev1.platform == "flipkart"
    assert rev1.rating == 4
    assert rev1.reviewer_name == "Ramesh Yadav"
    assert rev1.verified_purchase is True
    assert rev1.helpful_votes == 42
    assert rev1.review_date == "2026-08-12"
    assert "🔥" in rev1.title
    assert "mast" in rev1.text.lower()

    # Check Review 2: Negative Mic, Emoji, 1-star
    rev2 = reviews[1]
    assert rev2.rating == 1
    assert "👎" in rev2.title
    assert "bakwas" in rev2.text.lower()
    assert rev2.helpful_votes == 29

    # Check Review 3: Unverified / Bot pattern
    rev3 = reviews[2]
    assert rev3.rating == 5
    assert rev3.verified_purchase is False
    assert "super amazing" in rev3.text.lower()

    # Check Review 4: Seller complaint
    rev4 = reviews[3]
    assert rev4.rating == 1
    assert "unsealed box" in rev4.text.lower()

    # Check Review 5: Temporal durability
    rev5 = reviews[4]
    assert rev5.rating == 1
    assert "6 months use" in rev5.text.lower()


@pytest.mark.asyncio
async def test_fetch_product_reviews_offline():
    """Offline mode returns the seed reviews for the product, all valid Flipkart RawReviews."""
    result = await fetch_product_reviews("realme buds t310", mode="offline")

    assert result.data_source == "cached_fallback"
    assert result.query == "realme buds t310"
    assert len(result.reviews) >= 24
    for rev in result.reviews:
        assert isinstance(rev, RawReview)
        assert rev.platform == "flipkart"
        assert rev.rating in (1, 2, 3, 4, 5)
        assert len(rev.text) > 0


@pytest.mark.asyncio
async def test_fetch_product_reviews_snapshot():
    """Snapshot mode parses the local Flipkart DOM snapshot."""
    result = await fetch_product_reviews("realme buds t310", mode="snapshot")
    assert result.data_source == "cached_fallback"
    assert len(result.reviews) >= 5


@pytest.mark.asyncio
async def test_fetch_product_reviews_live_success():
    """Hybrid mode reports live_scrape when the scraper returns reviews."""
    live = [RawReview(review_id="fk_live_1", product_query="x", rating=4, text="Bass is mast", review_date="2026-09-01")]
    with patch("app.scraper.hybrid_scraper.scrape_flipkart", return_value=live):
        result = await fetch_product_reviews("realme buds t310", mode="hybrid")

    assert result.data_source == "live_scrape"
    assert [r.review_id for r in result.reviews] == ["fk_live_1"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [asyncio.TimeoutError(), ScrapeBlockedError("CAPTCHA"), RuntimeError("boom"), []],
    ids=["timeout", "captcha", "unexpected_error", "empty_result"],
)
async def test_fetch_product_reviews_falls_back_to_seed(outcome):
    """Hybrid mode falls back to the seed on timeout, CAPTCHA, any error, or an empty scrape."""
    kwargs = {"return_value": outcome} if isinstance(outcome, list) else {"side_effect": outcome}
    with patch("app.scraper.hybrid_scraper.scrape_flipkart", **kwargs):
        result = await fetch_product_reviews("realme buds t310", mode="hybrid")

    assert result.data_source == "cached_fallback"
    assert len(result.reviews) >= 24


@pytest.mark.asyncio
async def test_force_fallback_skips_live_scrape(monkeypatch):
    """FORCE_FALLBACK=1 never calls the live scraper."""
    monkeypatch.setenv("FORCE_FALLBACK", "1")
    with patch("app.scraper.hybrid_scraper.scrape_flipkart") as scraper:
        result = await fetch_product_reviews("realme buds t310", mode="hybrid")

    scraper.assert_not_called()
    assert result.data_source == "cached_fallback"


@pytest.mark.asyncio
async def test_fetcher_falls_back_on_block():
    """The SPEC §D.3 wrapper returns seed dicts instead of raising on a CAPTCHA."""
    with patch("app.scraper.fetcher.scrape_flipkart", side_effect=ScrapeBlockedError("CAPTCHA")):
        reviews, source = await fetch_reviews("sony wf-c700n")

    assert source == "cached_fallback"
    assert len(reviews) >= 20
    assert all(r["platform"] == "flipkart" for r in reviews)


def test_seed_lookup_unknown_product_is_empty():
    assert load_seed_reviews("unknown_nonexistent_product_xyz") == []


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
