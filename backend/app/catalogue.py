"""Offline product catalogue backed by data/seed_reviews.json (SPEC §D.4)."""

from functools import lru_cache
import json
import logging
from pathlib import Path
import re

from app.schemas import CatalogueProduct, RawReview

logger = logging.getLogger(__name__)

SEED_PATH = Path(__file__).resolve().parent / "data" / "seed_reviews.json"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@lru_cache(maxsize=1)
def _load() -> dict[str, dict]:
    """Catalogue entries keyed by slug id; empty when the seed file is missing or broken."""
    try:
        products = json.loads(SEED_PATH.read_text(encoding="utf-8")).get("products", {})
    except (OSError, ValueError) as exc:
        logger.error("Could not read %s: %s", SEED_PATH, exc)
        return {}
    return {slugify(key): entry for key, entry in products.items()}


def list_products() -> list[CatalogueProduct]:
    return [
        CatalogueProduct(
            id=pid,
            name=entry["metadata"]["name"],
            category=entry["metadata"].get("category", "Electronics"),
            review_count=len(entry.get("reviews", [])),
        )
        for pid, entry in _load().items()
    ]


def get_product(product_id: str) -> tuple[CatalogueProduct, list[RawReview]] | None:
    entry = _load().get(product_id)
    if entry is None:
        return None
    product = next(p for p in list_products() if p.id == product_id)
    return product, [RawReview.model_validate(r) for r in entry.get("reviews", [])]


def match_product(text: str) -> str | None:
    """Catalogue id sharing the most words with `text` (e.g. a Flipkart URL slug), needing at least 2."""
    words = set(slugify(text).split("-"))
    best = max(_load(), key=lambda pid: len(words & set(pid.split("-"))), default=None)
    return best if best and len(words & set(best.split("-"))) >= 2 else None
