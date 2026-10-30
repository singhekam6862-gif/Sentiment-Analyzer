from datetime import date
import re
from typing import Sequence

from app.schemas import (
    AnalyzeResponse,
    GenuineReview,
    ProductMetadata,
    RawReview,
    ReviewStats,
    SentimentSplit,
    TemporalDrift,
)
from app.nlp.absa_engine import extract_aspects_and_logistics
from app.nlp.summarizer import generate_summary
from app.nlp.trust_scorer import calculate_platform_trust, calculate_trust_scores

LONG_TERM_PATTERNS = [
    r"\bafter\s+\d+\s+months?\b",
    r"\bmonths?\s+later\b",
    r"\busing\s+since\b",
    r"\bmonths?\s+use\b",
    r"\bafter\s+\d+\s+weeks?\b",
    r"\bstopped\s+charging\b",
    r"\bstopped\s+working\b",
    r"\bab\s+kharab\b",
    r"\bstill\s+working\b",
    r"\byear\s+later\b",
]


def detect_temporal_drift(reviews: Sequence[RawReview]) -> TemporalDrift:
    """Calculates initial vs long-term sentiment and flags durability drops."""
    initial_scores: list[int] = []
    long_term_scores: list[int] = []

    for r in reviews:
        text_lower = r.text.lower()
        is_long_term = any(re.search(pat, text_lower) for pat in LONG_TERM_PATTERNS)
        score = int(r.rating * 20)  # Map 1-5 to 20-100

        if is_long_term:
            long_term_scores.append(score)
        else:
            initial_scores.append(score)

    init_avg = int(round(sum(initial_scores) / len(initial_scores))) if initial_scores else 75
    lt_avg = int(round(sum(long_term_scores) / len(long_term_scores))) if long_term_scores else init_avg

    warning: str | None = None
    if (init_avg - lt_avg) >= 15:
        drop = init_avg - lt_avg
        warning = (
            f"Durability Warning: Long-term buyer satisfaction drops by {drop} points "
            f"after 2-4 months of daily use, frequently citing battery degradation or charging issues."
        )

    return TemporalDrift(
        initial_sentiment=max(0, min(100, init_avg)),
        long_term_sentiment=max(0, min(100, lt_avg)),
        durability_warning=warning,
    )


def _parse_review_date(raw_date_str: str) -> date:
    """Safely converts review date string to date object."""
    clean = re.sub(r"[^\d\-]", "", raw_date_str)
    try:
        return date.fromisoformat(clean[:10])
    except Exception:
        return date.today()


def _build_review_stats(
    reviews: Sequence[RawReview],
    trust_results: list[dict],
    sentiment_split: SentimentSplit,
    fulfillment_rate: float,
) -> ReviewStats:
    """Aggregates rating, trust, verified ratio and complaint rate for the product."""
    if not reviews:
        return ReviewStats(
            overall_rating=0.0,
            sentiment_split=sentiment_split,
            trust_score=50,
            verified_purchase_ratio=0.0,
            fulfillment_complaint_rate=0.0,
        )
    verified_count = sum(1 for r in reviews if r.verified_purchase)
    return ReviewStats(
        overall_rating=round(sum(r.rating for r in reviews) / len(reviews), 1),
        sentiment_split=sentiment_split,
        trust_score=calculate_platform_trust(reviews, trust_results),
        verified_purchase_ratio=round(verified_count / len(reviews), 2),
        fulfillment_complaint_rate=fulfillment_rate,
    )


def analyze_product_pipeline(
    query: str,
    reviews: Sequence[RawReview],
    data_source: str = "cached_fallback",
) -> AnalyzeResponse:
    """Main pipeline orchestrator: computes Trust, ABSA, Drift, AI Summary, and Response."""
    # 1. Trust Scoring
    trust_results = calculate_trust_scores(reviews)
    trust_map = {item["review_id"]: item for item in trust_results}

    # 2. Aspect-Based Sentiment Analysis & Logistics
    absa_data = extract_aspects_and_logistics(reviews)
    aspect_scores = absa_data["aspect_scores"]
    aspects_map = absa_data["review_aspects_map"]
    sentiment_map = absa_data["review_sentiment_map"]

    # 3. Product-level stats
    review_stats = _build_review_stats(
        reviews, trust_results, absa_data["sentiment_split"], absa_data["fulfillment_rate"]
    )

    # 4. Temporal Sentiment Drift
    temporal_drift = detect_temporal_drift(reviews)

    # 5. Top Genuine Reviews (filter out suspicious, sort by helpful votes and trust score)
    genuine_candidates: list[tuple[RawReview, dict]] = []
    for r in reviews:
        t_info = trust_map.get(r.review_id, {"review_trust_score": 50, "is_suspicious": False})
        if not t_info["is_suspicious"]:
            genuine_candidates.append((r, t_info))

    genuine_candidates.sort(
        key=lambda pair: (pair[0].helpful_votes, pair[1]["review_trust_score"]),
        reverse=True,
    )

    top_genuine: list[GenuineReview] = []
    for r, t_info in genuine_candidates[:5]:
        top_genuine.append(
            GenuineReview(
                review_id=r.review_id,
                author=r.author,
                rating=r.rating,
                title=r.title,
                text=r.text,
                review_date=_parse_review_date(r.review_date),
                verified_purchase=r.verified_purchase,
                helpful_votes=r.helpful_votes,
                sentiment=sentiment_map.get(r.review_id, "positive"),
                aspects_mentioned=aspects_map.get(r.review_id, []),
                review_trust_score=t_info["review_trust_score"],
            )
        )

    # 6. Product Metadata
    product_name = query.title()
    category = "TWS Earbuds" if any(w in query.lower() for w in ["buds", "earbuds", "audio", "headphone"]) else "Electronics"
    image_url = "https://images.unsplash.com/photo-1590658268037-6bf12165a8df"

    # 7. AI Summary over non-suspicious reviews (Groq/Gemini chain or rule-based fallback)
    ai_summary = generate_summary(
        product_name, [r for r, _ in genuine_candidates], aspect_scores, review_stats
    )

    return AnalyzeResponse(
        product_metadata=ProductMetadata(
            name=product_name,
            category=category,
            image_url=image_url,
            total_reviews_analyzed=len(reviews),
            data_source="live_scrape" if data_source == "live_scrape" else "cached_fallback",
        ),
        review_stats=review_stats,
        aspect_scores=aspect_scores,
        temporal_drift=temporal_drift,
        ai_summary=ai_summary,
        top_genuine_reviews=top_genuine,
    )
