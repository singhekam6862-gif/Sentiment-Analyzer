"""Analysis jobs run as FastAPI background tasks (SPEC §C.4, §D.2).

Running jobs live in this process; finished ones are also saved to SQLite (app.store) and reused for a week.
"""

import asyncio
import os
from datetime import date
import hashlib
import logging
from urllib.parse import parse_qs, urlparse

from app import catalogue, store
from app.nlp.analysis import analyse
from app.nlp.summarizer import short_product_name
from app.schemas import AnalysisJob, AnalysisRequest, Product, RawReview
from app.scraper.fetcher import fetch_url_reviews

logger = logging.getLogger(__name__)

JOBS: dict[str, AnalysisJob] = {}
MAX_JOBS = 200  # bounds memory; the oldest finished job is dropped to make room


class JobsFullError(Exception):
    """Every slot holds a job that is still queued or running."""

NO_REVIEWS = (
    "Flipkart didn't return any reviews for this link. It may have blocked the request, "
    "or the page has no reviews yet. Try a product from the catalogue."
)
LIVE_OFF = (
    "Live fetching is switched off on this server (demo mode), and this product isn't in the catalogue. "
    "Try a product from the catalogue."
)


def job_id_for(req: AnalysisRequest) -> str:
    if req.product_id:
        return req.product_id
    # Path + pid name the product; tracking params (lid, srno, affid, …) would otherwise make a new job per link.
    parts = urlparse(req.url)
    product_key = parts.path.rstrip("/") + "?pid=" + parse_qs(parts.query).get("pid", [""])[0]
    return "url-" + hashlib.sha1(product_key.encode("utf-8")).hexdigest()[:12]


def get(job_id: str) -> AnalysisJob | None:
    return JOBS.get(job_id) or store.load(job_id)


def submit(req: AnalysisRequest) -> tuple[AnalysisJob, bool]:
    """Returns (job, is_new). A running, finished or saved job is reused; a failed one starts over."""
    job_id = job_id_for(req)
    existing = JOBS.get(job_id)
    if existing and existing.status != "failed":
        return existing, False
    if existing is None:
        _make_room()
    if saved := store.load(job_id):
        JOBS[job_id] = saved
        return saved, False
    JOBS[job_id] = AnalysisJob(job_id=job_id, status="queued", message="Waiting to start")
    return JOBS[job_id], True


def _make_room() -> None:
    """Drops the oldest finished job when the store is full (dicts keep insertion order)."""
    if len(JOBS) < MAX_JOBS:
        return
    oldest = next((k for k, j in JOBS.items() if j.status in ("done", "failed")), None)
    if oldest is None:
        raise JobsFullError
    del JOBS[oldest]


def _set(job_id: str, **changes) -> None:
    JOBS[job_id] = JOBS[job_id].model_copy(update=changes)


Source = tuple[Product, list[RawReview], list[str]]  # product, reviews, Flipkart's aspect names (hints for the LLM)


def _catalogue_source(product_id: str, source_url: str | None) -> Source:
    item, reviews = catalogue.get_product(product_id)
    product = Product(id=item.id, name=item.name, category=item.category, source_url=source_url, images=[], specs=[],
                      data_source="catalogue", collected_on=None)
    return product, reviews, []


async def _url_source(job_id: str, url: str) -> Source | None:
    _set(job_id, status="fetching", message="Fetching reviews from Flipkart")
    reviews, aspect_hints, title, images, specs = await fetch_url_reviews(url, lambda msg: _set(job_id, message=msg))
    if reviews:
        slug_name = urlparse(url).path.strip("/").split("/")[0].replace("-", " ")
        name = await asyncio.to_thread(short_product_name, title or slug_name or "Flipkart product")
        product = Product(id=job_id, name=name, category="Flipkart product", source_url=url, images=images, specs=specs,
                          data_source="live_scrape", collected_on=date.today())
        return product, reviews, aspect_hints
    match = catalogue.match_product(urlparse(url).path)
    return _catalogue_source(match, url) if match else None


async def run(job_id: str, req: AnalysisRequest) -> None:
    """Background task: collect, analyse, store. Never raises; failures land in the job."""
    try:
        source = _catalogue_source(req.product_id, None) if req.product_id else await _url_source(job_id, req.url)
        if source is None:
            reason = LIVE_OFF if os.getenv("FORCE_FALLBACK", "0") == "1" else NO_REVIEWS
            _set(job_id, status="failed", message="No reviews collected", error=reason)
            return
        product, reviews, aspect_hints = source
        _set(job_id, status="analysing", message=f"Reading {len(reviews)} reviews")
        # sync NLP + LLM calls stay off the event loop; progress writes are single dict assignments, safe across threads
        result = await asyncio.to_thread(analyse, product, reviews, lambda msg: _set(job_id, message=msg), aspect_hints)
        _set(job_id, status="done", message=f"Analysed {result.funnel.analysed} product reviews", result=result)
        if not (req.url and result.product.data_source == "catalogue"):  # a blocked scrape should go live next time
            store.save(JOBS[job_id])
    except Exception:
        logger.exception("Analysis job %s failed", job_id)
        _set(job_id, status="failed", message="Analysis failed",
             error="Something went wrong while analysing these reviews. Please try again.")
