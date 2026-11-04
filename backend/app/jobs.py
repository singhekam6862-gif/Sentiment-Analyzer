"""In-memory analysis jobs run as FastAPI background tasks (SPEC §C.4, §D.2).

shortcut: jobs live in this process and vanish on restart; move to SQLite if links must survive restarts.
"""

import asyncio
import os
from datetime import date
import hashlib
import logging
from urllib.parse import urlparse

from app import catalogue
from app.nlp.analysis import analyse
from app.schemas import AnalysisJob, AnalysisRequest, Product, RawReview
from app.scraper.fetcher import fetch_url_reviews

logger = logging.getLogger(__name__)

JOBS: dict[str, AnalysisJob] = {}

NO_REVIEWS = (
    "Flipkart didn't return any reviews for this link. It may have blocked the request, "
    "or the page has no reviews yet. Try a product from the catalogue."
)
LIVE_OFF = (
    "Live fetching is switched off on this server (demo mode), and this product isn't in the catalogue. "
    "Try a product from the catalogue."
)


def job_id_for(req: AnalysisRequest) -> str:
    return req.product_id or "url-" + hashlib.sha1(req.url.encode("utf-8")).hexdigest()[:12]


def submit(req: AnalysisRequest) -> tuple[AnalysisJob, bool]:
    """Returns (job, is_new). A running or finished job is reused; a failed one starts over."""
    job_id = job_id_for(req)
    existing = JOBS.get(job_id)
    if existing and existing.status != "failed":
        return existing, False
    JOBS[job_id] = AnalysisJob(job_id=job_id, status="queued", message="Waiting to start")
    return JOBS[job_id], True


def _set(job_id: str, **changes) -> None:
    JOBS[job_id] = JOBS[job_id].model_copy(update=changes)


def _catalogue_source(product_id: str, source_url: str | None) -> tuple[Product, list[RawReview]]:
    item, reviews = catalogue.get_product(product_id)
    product = Product(id=item.id, name=item.name, category=item.category, source_url=source_url,
                      data_source="catalogue", collected_on=None)
    return product, reviews


async def _url_source(job_id: str, url: str) -> tuple[Product, list[RawReview]] | None:
    _set(job_id, status="fetching", message="Fetching reviews from Flipkart")
    reviews = await fetch_url_reviews(url)
    if reviews:
        name = urlparse(url).path.strip("/").split("/")[0].replace("-", " ") or "Flipkart product"
        product = Product(id=job_id, name=name, category="Flipkart product", source_url=url,
                          data_source="live_scrape", collected_on=date.today())
        return product, reviews
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
        product, reviews = source
        _set(job_id, status="analysing", message=f"Reading {len(reviews)} reviews")
        result = await asyncio.to_thread(analyse, product, reviews)  # sync NLP + LLM calls stay off the event loop
        _set(job_id, status="done", message=f"Analysed {result.funnel.analysed} product reviews", result=result)
    except Exception:
        logger.exception("Analysis job %s failed", job_id)
        _set(job_id, status="failed", message="Analysis failed",
             error="Something went wrong while analysing these reviews. Please try again.")
