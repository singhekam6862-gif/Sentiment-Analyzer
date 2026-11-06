"""Saved analyses (SPEC §C.3): finished jobs go into data/cache.sqlite so the same product isn't scraped
or sent to an LLM again, and result links survive a server restart.

A storage failure only costs a fresh analysis; it never fails a job.
"""

from contextlib import closing
import logging
from pathlib import Path
import sqlite3
import time

from pydantic import ValidationError

from app.schemas import AnalysisJob

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent / "data" / "cache.sqlite"  # same file as the LLM answer cache
MAX_AGE_SECONDS = 7 * 24 * 3600  # Flipkart reviews change; after a week the product is analysed again


def _open() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS analyses (job_id TEXT PRIMARY KEY, saved_at REAL, job TEXT)")
    return conn


def save(job: AnalysisJob) -> None:
    try:
        with closing(_open()) as conn, conn:
            conn.execute("INSERT OR REPLACE INTO analyses VALUES (?, ?, ?)", (job.job_id, time.time(), job.model_dump_json()))
    except sqlite3.Error as exc:
        logger.warning("Saving analysis %s failed: %s", job.job_id, exc)


def load(job_id: str) -> AnalysisJob | None:
    """The saved job if it is younger than MAX_AGE_SECONDS, else None."""
    try:
        with closing(_open()) as conn:
            row = conn.execute(
                "SELECT job FROM analyses WHERE job_id = ? AND saved_at > ?", (job_id, time.time() - MAX_AGE_SECONDS)
            ).fetchone()
        return AnalysisJob.model_validate_json(row[0]) if row else None
    except (sqlite3.Error, ValidationError) as exc:  # a row from an older schema counts as a miss
        logger.warning("Loading analysis %s failed: %s", job_id, exc)
        return None
