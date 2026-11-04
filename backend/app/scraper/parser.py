"""Reads review cards out of Flipkart HTML.

Flipkart's CSS class names are generated and change between deploys, so cards are found by structure.
Both layouts seen live (2026-10-30) are handled:
- reviews drawer on the product page: [stars · title · date] [text] [name · badge · 👍 · 👎]
- /product-reviews/ page:             [stars · title] [Review for: variant] [text] [name · city · Helpful for N · badge · date]
"""

import hashlib
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup, Tag

from app.schemas import RawReview

DATE_RE = re.compile(
    r"^(?:(\d+|an?)\s+(minute|hour|day|week|month|year)s?\s+ago|today|yesterday"
    r"|\d{1,2}\s+[A-Za-z]+,?\s+\d{4}|[A-Za-z]+,?\s+\d{4})$",
    re.IGNORECASE,
)
RATING_RE = re.compile(r"^[1-5](?:\.0)?$")
UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
BADGES = {"verified buyer", "verified purchase", "certified buyer"}


def _clean(s: str) -> str:
    return s.strip().lstrip("·•").strip()


def _normalize_date(raw: str, today: date) -> str:
    """'28 days ago', '12 Aug, 2026' or 'Aug, 2026' → YYYY-MM-DD. Relative ages are approximate."""
    raw = _clean(raw)
    m = DATE_RE.match(raw)
    if m and m.group(2):
        n = 1 if m.group(1).lower() in ("a", "an") else int(m.group(1))
        return (today - timedelta(days=n * UNIT_DAYS[m.group(2).lower()])).isoformat()
    if raw.lower() in ("today", "yesterday"):
        return (today - timedelta(days=raw.lower() == "yesterday")).isoformat()
    cleaned = raw.replace(",", "")
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %Y", "%B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            pass
    return today.isoformat()


def _children(el: Tag) -> list[Tag]:
    return [c for c in el.children if isinstance(c, Tag)]


def _card_for(date_node) -> Tag | None:
    """Climbs from the date text to the first ancestor that has ≥ 3 parts and starts with the star rating."""
    el = date_node.parent
    for _ in range(8):
        if el is None:
            return None
        kids = _children(el)
        if len(kids) >= 3 and RATING_RE.match(next(kids[0].stripped_strings, "")):
            return el
        el = el.parent
    return None


def _parse_card(card: Tag, date_text: str, today: date, product_query: str) -> RawReview | None:
    kids = _children(card)
    header, footer = kids[0], kids[-1]
    head = [_clean(s) for s in header.stripped_strings]
    title = " ".join(s for s in head[1:] if s and s != date_text) or None
    middle = [k.get_text(" ", strip=True) for k in kids[1:-1]]
    body = " ".join(t for t in middle if not t.startswith("Review for:"))
    text = re.sub(r"\s*(\.\.\.|…)?\s*(read\s+)?more$", "", body, flags=re.IGNORECASE)
    foot = [_clean(s) for s in footer.stripped_strings]
    if not foot or not (text or title):
        return None
    name = foot[0]
    review_date = _normalize_date(date_text, today)
    votes = next((int(m.group(1).replace(",", "")) for s in foot[1:]
                  if (m := re.fullmatch(r"(?:helpful for\s+)?(\d[\d,]*)", s, re.IGNORECASE))), 0)
    key = f"{name}_{review_date}_{title}_{text[:30]}"
    return RawReview(
        review_id="fk_" + hashlib.md5(key.encode()).hexdigest()[:10],
        product_query=product_query,
        reviewer_name=name,
        rating=int(float(head[0])),
        title=title,
        text=text or title,
        review_date=review_date,
        verified_purchase=any(s.lower() in BADGES for s in foot),
        helpful_votes=votes,
    )


def parse_flipkart_html(html: str, product_query: str, today: date | None = None) -> list[RawReview]:
    """Every review card on a Flipkart page, in page order, without duplicates."""
    if not html:
        return []
    today = today or date.today()
    soup = BeautifulSoup(html, "html.parser")
    reviews: dict[str, RawReview] = {}
    for node in soup.find_all(string=lambda s: s and DATE_RE.match(_clean(s))):
        card = _card_for(node)
        review = _parse_card(card, _clean(node), today, product_query) if card else None
        if review:
            reviews.setdefault(review.review_id, review)
    return list(reviews.values())
