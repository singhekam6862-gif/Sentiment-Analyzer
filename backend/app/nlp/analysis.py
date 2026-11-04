"""Pipeline orchestrator: reviews → Analysis (SPEC §A, §C.5)."""

from collections import Counter, defaultdict
from datetime import date

from app.nlp.absa_engine import classify_review_sentiment, is_logistics_complaint
from app.nlp.categories import RELIABILITY, label, suggested_aspects, use_case_template
from app.nlp.opinions import extract_all_opinions
from app.nlp.preprocessor import normalize_review_text
from app.nlp.summarizer import generate_summary
from app.nlp.trust_scorer import calculate_trust_scores
from app.schemas import (
    Analysis, Aspect, Claim, Funnel, FunnelGroup, Product, Quote, Rating, RawReview, Review, UseCase, Verdict,
)

Votes = dict[str, list[tuple[str, str, str]]]  # aspect key -> [(review_id, polarity, quote)]


def _parse_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return date.today()


def classify_reviews(reviews: list[RawReview]) -> list[Review]:
    """Puts every review in exactly one group: suspicious, fulfillment or product (SPEC §A.3)."""
    trust = {t["review_id"]: t for t in calculate_trust_scores(reviews)}
    out = []
    for r in reviews:
        cleaned = normalize_review_text(r.text)["cleaned_text"]
        sentiment = classify_review_sentiment(r.text, r.rating)
        t = trust[r.review_id]
        if t["is_suspicious"]:
            group = "suspicious"
        elif (sentiment == "negative" or r.rating <= 2) and is_logistics_complaint(cleaned, r.rating):
            group = "fulfillment"
        else:
            group = "product"
        out.append(Review(
            review_id=r.review_id, author=r.author, rating=r.rating, title=r.title, text=r.text,
            review_date=_parse_date(r.review_date), verified_purchase=r.verified_purchase,
            helpful_votes=r.helpful_votes, group=group, sentiment=sentiment, aspects=[], flags=t["trust_flags"],
        ))
    return sorted(out, key=lambda x: x.helpful_votes, reverse=True)


def build_aspects(votes: Votes) -> list[Aspect]:
    aspects = []
    for key, items in votes.items():
        n = Counter(p for _, p, _ in items)
        lead = "complaint" if n["complaint"] > n["praise"] else "praise"
        ordered = sorted(items, key=lambda i: i[1] != lead)
        total = len(items)
        aspects.append(Aspect(
            key=key, label=label(key), praise=n["praise"], complaints=n["complaint"], mixed=n["mixed"],
            confidence="high" if total >= 6 else "medium" if total >= 4 else "low",
            quotes=[Quote(review_id=rid, text=q, polarity=p) for rid, p, q in ordered[:4]],
        ))
    return sorted(aspects, key=lambda a: a.praise + a.complaints + a.mixed, reverse=True)[:8]


def build_use_cases(template: list[tuple[str, list[str]]], aspects: list[Aspect]) -> list[UseCase]:
    """good ≥ 0.75 praise share, okay ≥ 0.40, else poor; too_few under 2 mentions (SPEC §A.6)."""
    out = []
    for name, keys in template:
        used = [a for a in aspects if a.key in keys]
        praise, complaints = sum(a.praise for a in used), sum(a.complaints for a in used)
        count = sum(a.praise + a.complaints + a.mixed for a in used)
        if count < 2 or praise + complaints == 0:
            verdict = "too_few"
        else:
            share = praise / (praise + complaints)
            verdict = "good" if share >= 0.75 else "okay" if share >= 0.40 else "poor"
        quote = next((q.text for a in used for q in a.quotes), None)
        reason = f"“{quote}”" if quote and verdict != "too_few" else "Too few reviews mention it."
        out.append(UseCase(name=name, verdict=verdict, reason=reason, review_count=count))
    return out[:6]


def reliability_warning(aspects: list[Aspect]) -> str | None:
    a = next((a for a in aspects if a.key == RELIABILITY), None)
    if a and a.complaints >= 2 and a.praise <= a.complaints:
        return f"{a.complaints} owners say it failed or got worse after weeks or months of use."
    return None


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def rule_based_headline(use_cases: list[UseCase], aspects: list[Aspect]) -> str:
    good = [u.name.lower() for u in use_cases if u.verdict == "good"]
    poor = [u.name.lower() for u in use_cases if u.verdict == "poor"]
    if not good and not poor:
        good = [a.label.lower() for a in aspects if a.praise > a.complaints][:2]
        poor = [a.label.lower() for a in aspects if a.complaints > a.praise][:2]
        if not good and not poor:
            return "Not enough product reviews to judge yet."
        parts = [f"Buyers praise {_join(good)}." if good else "", f"Common complaints: {_join(poor)}." if poor else ""]
        return " ".join(p for p in parts if p)
    parts = [f"Good for {_join(good)}." if good else "", f"Not for {_join(poor)}." if poor else ""]
    return " ".join(p for p in parts if p)


def _rule_based_claims(votes: Votes, aspects: list[Aspect], polarity: str) -> list[tuple[str, str]]:
    """The first verbatim quote of the strongest aspects for this polarity."""
    side = [a for a in aspects if (a.praise > a.complaints if polarity == "praise" else a.complaints > a.praise)]
    side.sort(key=lambda a: a.praise if polarity == "praise" else a.complaints, reverse=True)
    return [(next(q for _, p, q in votes[a.key] if p == polarity), a.key) for a in side[:3]]


def _with_ids(claims: list[tuple[str, str]], votes: Votes, polarity: str) -> list[Claim]:
    return [Claim(text=t, review_ids=[rid for rid, p, _ in votes[k] if p == polarity]) for t, k in claims]


def build_verdict(name: str, votes: Votes, aspects: list[Aspect], use_cases: list[UseCase]):
    """Verdict + pros/cons: the LLM chain when it answers, else rule-based (SPEC §A.7)."""
    draft = generate_summary(name, aspects, use_cases)
    if draft:
        headline, pros, cons, by = draft.headline, draft.pros, draft.cons, draft.generated_by
    else:
        headline, by = rule_based_headline(use_cases, aspects), "rule_based"
        pros, cons = _rule_based_claims(votes, aspects, "praise"), _rule_based_claims(votes, aspects, "complaint")
    verdict = Verdict(headline=headline, warning=reliability_warning(aspects), generated_by=by)
    return verdict, _with_ids(pros, votes, "praise"), _with_ids(cons, votes, "complaint")


def build_funnel(reviews: list[Review]) -> Funnel:
    groups = Counter(r.group for r in reviews)
    burst = Counter(str(r.review_date) for r in reviews if "unverified_date_burst" in r.flags)
    if burst:
        day = date.fromisoformat(burst.most_common(1)[0][0])
        why = f"Unverified 5★ burst on {day.day} {day:%b %Y} with near-identical text."
    elif groups["suspicious"]:
        why = "Low trust signals: unverified, generic or duplicated text."
    else:
        why = "None of the reviews looked planted."
    return Funnel(
        collected=len(reviews),
        suspicious=FunnelGroup(count=groups["suspicious"], reason=why),
        fulfillment=FunnelGroup(count=groups["fulfillment"], reason="Complaints about delivery, packaging or the seller."),
        analysed=groups["product"],
    )


def analyse(product: Product, raw: list[RawReview]) -> Analysis:
    reviews = classify_reviews(raw)
    product_ids = {r.review_id for r in reviews if r.group == "product"}
    votes: Votes = defaultdict(list)
    opinions = extract_all_opinions(
        [r for r in raw if r.review_id in product_ids], suggested_aspects(product.name, product.category)
    )
    for r in reviews:
        r.aspects = [key for key, _, _ in opinions.get(r.review_id, [])]
        for key, polarity, quote in opinions.get(r.review_id, []):
            votes[key].append((r.review_id, polarity, quote))
    aspects = build_aspects(votes)
    use_cases = build_use_cases(use_case_template(product.name, product.category), aspects)
    verdict, pros, cons = build_verdict(product.name, votes, aspects, use_cases)
    dist = [sum(1 for r in raw if r.rating == star) for star in range(1, 6)]
    return Analysis(
        product=product, verdict=verdict,
        rating=Rating(average=round(sum(r.rating for r in raw) / len(raw), 1) if raw else 0, count=len(raw), distribution=dist),
        funnel=build_funnel(reviews), use_cases=use_cases, aspects=aspects, pros=pros, cons=cons, reviews=reviews,
    )
