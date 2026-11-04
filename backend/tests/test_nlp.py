import json
from pathlib import Path
import pytest

from app import catalogue
from app.schemas import Product, RawReview
from app.nlp.analysis import analyse, build_use_cases
from app.nlp.opinions import extract_opinions
from app.nlp.preprocessor import normalize_review_text
from app.nlp.trust_scorer import calculate_trust_scores
from app.nlp.absa_engine import classify_review_sentiment, split_into_clauses

SEED_PATH = Path(__file__).resolve().parent.parent / "app" / "data" / "seed_reviews.json"


def load_seed_for_query(query: str = "realme buds t310") -> list[RawReview]:
    """Loads all seed reviews for a product."""
    assert SEED_PATH.exists(), f"Missing seed_reviews.json at {SEED_PATH}"
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return [RawReview(**item) for item in data["products"][query]["reviews"]]


# --- Test Suite 1: Hinglish & Negation Accuracy ---


def test_hinglish_and_negation_normalization():
    """Verify Hinglish mapping, emoji conversion, and negation integrity."""
    # 1. Paisa vasool and fire emoji
    res1 = normalize_review_text("Paisa vasool earbuds 🔥")
    assert "great value for money" in res1["cleaned_text"]
    assert "excellent" in res1["cleaned_text"]
    assert "paisa vasool" in res1["detected_hinglish"]
    assert classify_review_sentiment(res1["cleaned_text"], rating=4) == "positive"

    # 2. Bakwas and thumbs down emoji
    res2 = normalize_review_text("Bilkul bakwas mic quality 👎")
    assert "terrible" in res2["cleaned_text"]
    assert classify_review_sentiment(res2["cleaned_text"], rating=1) == "negative"

    # 3. Negation flip: "not good"
    res3 = normalize_review_text("Sound is not good at all")
    assert "not" in res3["cleaned_text"]
    assert classify_review_sentiment(res3["cleaned_text"], rating=2) == "negative"

    # 4. Hinglish negation: "badiya nahi hai"
    res4 = normalize_review_text("Sound badiya nahi hai")
    assert "not" in res4["cleaned_text"] or "nahi" in res4["cleaned_text"]
    assert classify_review_sentiment(res4["cleaned_text"], rating=2) == "negative"


# --- Test Suite 2: Mixed-Clause Opinion Units ---


def test_mixed_clause_opinions_keep_verbatim_quotes():
    """Contrasting clauses give opposite polarities, and every quote is copied from the review."""
    text = "ANC and bass are mind-blowing, but mic quality outdoors is terrible. Worth 2.5k though."
    assert len(split_into_clauses(text)) >= 2
    review = RawReview(review_id="t1", product_query="x", rating=3, text=text, review_date="2026-08-15")

    units = {key: (polarity, quote) for key, polarity, quote in extract_opinions(review)}

    assert units["anc_noise_cancellation"][0] == "praise"
    assert units["sound_quality"][0] == "praise"
    assert units["mic_call_quality"][0] == "complaint"
    assert all(quote in text for _, quote in units.values())
    assert any("2.5k" in quote for _, quote in units.values()), "decimals must not split clauses"


def test_long_term_failure_is_a_reliability_complaint():
    review = RawReview(review_id="t2", product_query="x", rating=2, review_date="2026-09-02",
                       text="After 3 months the right earbud stopped charging completely in case.")
    units = {key: polarity for key, polarity, _ in extract_opinions(review)}
    assert units["long_term_reliability"] == "complaint"


# --- Test Suite 3: Fake Review Burst & Duplication Detection ---


def test_fake_review_burst_detection():
    """Verify unverified generic 5-star reviews on the same date receive low trust scores."""
    reviews = load_seed_for_query("realme buds t310")
    trust_scores = calculate_trust_scores(reviews)
    trust_map = {item["review_id"]: item for item in trust_scores}

    # Unverified generic 5-star bot reviews posted on 2026-07-15
    bot_ids = ["fk_rt310_104", "fk_rt310_105", "fk_rt310_004", "fk_rt310_005"]

    for b_id in bot_ids:
        b_info = trust_map[b_id]
        assert b_info["review_trust_score"] < 45, f"{b_id} score {b_info['review_trust_score']} >= 45"
        assert b_info["is_suspicious"] is True
        assert any(flag in b_info["trust_flags"] for flag in ["unverified_date_burst", "repetitive_phrasing", "unverified_purchase"])

    # High quality verified review must have high trust score
    top_rev = trust_map["fk_rt310_101"]
    assert top_rev["review_trust_score"] >= 80
    assert top_rev["is_suspicious"] is False


# --- Test Suite 4: Full analysis on every catalogue product (SPEC §C.6 invariants) ---


def _analyse(product_id: str):
    item, reviews = catalogue.get_product(product_id)
    product = Product(id=item.id, name=item.name, category=item.category, source_url=None,
                      data_source="catalogue", collected_on=None)
    return analyse(product, reviews)


@pytest.mark.parametrize("product_id", [p.id for p in catalogue.list_products()])
def test_analysis_invariants(product_id):
    result = _analyse(product_id)
    by_id = {r.review_id: r for r in result.reviews}
    f = result.funnel

    assert f.analysed == f.collected - f.suspicious.count - f.fulfillment.count
    assert sum(r.group == "product" for r in result.reviews) == f.analysed
    assert sum(result.rating.distribution) == result.rating.count == f.collected
    for aspect in result.aspects:
        for q in aspect.quotes:
            assert by_id[q.review_id].group == "product"
            assert q.text in by_id[q.review_id].text
    for claim in result.pros + result.cons:
        assert all(rid in by_id for rid in claim.review_ids)
    assert result.verdict.generated_by == "rule_based"


def test_realme_verdict_matches_the_reviews():
    """The seeded realme story: good for music/commuting, poor for calls/lasting, 4-review burst set aside."""
    result = _analyse("realme-buds-t310")
    verdicts = {u.name: u.verdict for u in result.use_cases}

    assert verdicts["Music"] == "good" and verdicts["Commuting"] == "good"
    assert verdicts["Office calls"] == "poor" and verdicts["Lasting a year"] == "poor"
    assert result.funnel.suspicious.count == 4 and "15 Jul 2026" in result.funnel.suspicious.reason
    assert result.funnel.fulfillment.count == 4
    assert result.verdict.warning is not None
    assert {r.review_id for r in result.reviews if r.group == "suspicious"} == {
        "fk_rt310_004", "fk_rt310_005", "fk_rt310_104", "fk_rt310_105"}


def test_use_case_needs_two_mentions():
    assert build_use_cases([("Gaming", ["latency"])], [])[0].verdict == "too_few"
