"""Reads reviews out of Flipkart HTML.

First choice is the JSON Flipkart embeds in the server-rendered page (window.__INITIAL_STATE__): full text, real ids,
no guessing. When a page has none, review cards are read from the markup instead.
Flipkart's CSS class names are generated and change between deploys, so cards are found by structure.
Both layouts seen live (2026-10-30) are handled:
- reviews drawer on the product page: [stars · title · date] [text] [name · badge · 👍 · 👎]
- /product-reviews/ page:             [stars · title] [Review for: variant] [text] [name · city · Helpful for N · badge · date]
"""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from app.schemas import RawReview, SpecGroup, SpecItem

DATE_RE = re.compile(
    r"^(?:(\d+|an?)\s+(minute|hour|day|week|month|year)s?\s+ago|today|yesterday"
    r"|\d{1,2}\s+[A-Za-z]+,?\s+\d{4}|[A-Za-z]+,?\s+\d{4})$",
    re.IGNORECASE,
)
RATING_RE = re.compile(r"^[1-5](?:\.0)?$")
STATE_RE = re.compile(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});?\s*</script>", re.S)
UNIT_DAYS = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}
BADGES = {"verified buyer", "verified purchase", "certified buyer"}
PRICE_TAIL_RE = re.compile(r"\s*(?:-\s*)?(?:Rs\.?\s*[\d,]+\s*)?Price in India.*$", re.IGNORECASE | re.DOTALL)
IMAGE_HOST_RE = re.compile(r"rukminim\d*\.flixcart\.com")
MAX_IMAGES = 12  # SPEC §C.5


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


def _walk_state(node, value_type: str, found: list[dict]) -> None:
    if isinstance(node, dict):
        if node.get("type") == value_type:
            found.append(node)
        for v in node.values():
            _walk_state(v, value_type, found)
    elif isinstance(node, list):
        for v in node:
            _walk_state(v, value_type, found)


def _load_state(html: str) -> dict | None:
    """The page's window.__INITIAL_STATE__ JSON; None if it has none."""
    m = STATE_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def _find_in_state(html: str, value_type: str) -> list[dict] | None:
    """Every object of this type in the page's state JSON; None if the page has no state."""
    state = _load_state(html)
    if state is None:
        return None
    found: list[dict] = []
    _walk_state(state, value_type, found)
    return found


def parse_flipkart_aspects(html: str) -> list[str]:
    """Flipkart's own aspect names for this product (the review filter tabs), as snake_case keys, "Overall" dropped."""
    names = [str(o.get("name") or "") for o in _find_in_state(html, "UgcAspectTabValue") or []]
    keys = (re.sub(r"[^a-z0-9]+", "_", n.lower()).strip("_") for n in names)
    return list(dict.fromkeys(k for k in keys if k and k != "overall"))


def _first_key(node, key: str):
    """Depth first: the value of the first dict entry with this key anywhere under node, else None."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        node = list(node.values())
    if isinstance(node, list):
        for child in node:
            if (found := _first_key(child, key)) is not None:
                return found
    return None


def _dig(node, *keys: str):
    for key in keys:
        node = node.get(key) if isinstance(node, dict) else None
    return node


def _as_list(node) -> list:
    return node if isinstance(node, list) else []


def _is_flipkart_image(url: str) -> bool:
    """The URL ends up in our page, so it must be on Flipkart's image CDN."""
    parts = urlparse(url)
    return parts.scheme == "https" and bool(IMAGE_HOST_RE.fullmatch(parts.hostname or ""))


def _parse_gallery(state: dict | None) -> list[str]:
    """The product's own photos, in gallery order. The rest of the page also holds other products' images and icons."""
    urls = []
    for item in _as_list(_dig(_first_key(state, "multiMediaViewData_0"), "value")):
        selected = _dig(item, "value", "image_0", "value", "selected", "value")
        url = _dig(selected, "dynamicImageUrl")
        if _dig(selected, "contentType") == "IMAGE" and isinstance(url, str):
            url = url.replace("{@width}", "800").replace("{@height}", "800").replace("{@quality}", "80")
            if _is_flipkart_image(url):
                urls.append(url)
    return list(dict.fromkeys(urls))[:MAX_IMAGES]


def _parse_spec_item(row) -> SpecItem | None:
    name = _dig(row, "value", "label_0", "value", "text")
    value = _dig(row, "value", "label_1", "value", "text")  # a list of strings on the page seen live (2026-11-06)
    value = ", ".join(v for v in value if isinstance(v, str)) if isinstance(value, list) else value
    return SpecItem(name=name, value=value) if name and value and isinstance(name, str) and isinstance(value, str) else None


def _parse_specs(state: dict | None) -> list[SpecGroup]:
    """Flipkart's specification table, in its own groups and order."""
    groups = []
    for group in _as_list(_dig(_first_key(state, "rpd_specifications_grid_layout_1"), "value", "gridData_0", "value")):
        name = _dig(group, "value", "label_0", "value", "text")
        rows = _dig(group, "value", "rpd_grid_0", "value", "gridData_0", "value")
        items = [item for row in _as_list(rows) if (item := _parse_spec_item(row))]
        if name and isinstance(name, str) and items:
            groups.append(SpecGroup(name=name, items=items))
    return groups


def parse_flipkart_product(html: str) -> tuple[str | None, list[str], list[SpecGroup]]:
    """(title, image URLs, specs) from a product page. A title with no "Price in India" tail isn't a product's.
    Photos and specs come from the page's state JSON; a page without it still gives its single og:image."""
    soup = BeautifulSoup(html, "html.parser")
    og = lambda prop: str((soup.find("meta", property=prop) or {}).get("content") or "")
    title, tails = PRICE_TAIL_RE.subn("", og("og:title"))
    state = _load_state(html)
    og_images = [og("og:image")] if _is_flipkart_image(og("og:image")) else []
    return (title.strip() if tails else None) or None, _parse_gallery(state) or og_images, _parse_specs(state)


def parse_flipkart_state(html: str, product_query: str, today: date | None = None) -> list[RawReview] | None:
    """Reviews from the JSON Flipkart embeds in the page (window.__INITIAL_STATE__); None if the page has none."""
    found = _find_in_state(html, "ProductReviewValue")
    if found is None:
        return None
    today = today or date.today()
    reviews: dict[str, RawReview] = {}
    for o in found:
        try:
            title, text = (o.get("title") or "").strip() or None, (o.get("text") or "").strip()
            if not (text or title):
                continue
            review = RawReview(
                review_id=f"fk_{o['id']}", product_query=product_query, rating=int(o["rating"]),
                title=title, text=text or title, review_date=_normalize_date(o.get("created") or "", today),
                verified_purchase=bool(o.get("certifiedBuyer")), helpful_votes=max(int(o.get("helpfulCount") or 0), 0),
                reviewer_name=o.get("author") or "Anonymous",
            )
        except (KeyError, ValueError, TypeError):  # pydantic's ValidationError is a ValueError
            continue
        reviews.setdefault(review.review_id, review)
    return list(reviews.values())


def parse_flipkart_html(html: str, product_query: str, today: date | None = None) -> list[RawReview]:
    """Every review on a Flipkart page, in page order, without duplicates: embedded JSON first, else the cards."""
    if not html:
        return []
    today = today or date.today()
    from_state = parse_flipkart_state(html, product_query, today)
    if from_state:
        return from_state
    soup = BeautifulSoup(html, "html.parser")
    reviews: dict[str, RawReview] = {}
    for node in soup.find_all(string=lambda s: s and DATE_RE.match(_clean(s))):
        card = _card_for(node)
        review = _parse_card(card, _clean(node), today, product_query) if card else None
        if review:
            reviews.setdefault(review.review_id, review)
    return list(reviews.values())
