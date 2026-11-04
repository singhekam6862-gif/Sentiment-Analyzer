import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.main import app
from app.schemas import Analysis


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FORCE_FALLBACK", "1")  # URL jobs never go live in tests
    jobs.JOBS.clear()
    return TestClient(app)


def test_products_endpoint(client):
    products = client.get("/api/v3/products").json()
    assert {"id": "realme-buds-t310", "name": "realme Buds T310", "category": "TWS Earbuds", "review_count": 24} in products


def test_catalogue_analysis_runs_to_done(client):
    """TestClient runs the background task before returning, so the job is finished on the next GET."""
    started = client.post("/api/v3/analyses", json={"product_id": "realme-buds-t310"})
    assert started.status_code == 202
    assert started.json()["job_id"] == "realme-buds-t310"

    job = client.get("/api/v3/analyses/realme-buds-t310").json()
    assert job["status"] == "done" and job["error"] is None
    result = Analysis.model_validate(job["result"])
    assert result.product.data_source == "catalogue"
    assert result.funnel.analysed == 16


def test_reposting_reuses_the_job(client):
    client.post("/api/v3/analyses", json={"product_id": "sony-wf-c700n"})
    again = client.post("/api/v3/analyses", json={"product_id": "sony-wf-c700n"}).json()
    assert again["status"] == "done"


def test_url_job_falls_back_to_matching_catalogue_product(client):
    url = "https://www.flipkart.com/realme-buds-t310-46db-anc/p/itm123?pid=ACCX"
    job_id = client.post("/api/v3/analyses", json={"url": url}).json()["job_id"]

    job = client.get(f"/api/v3/analyses/{job_id}").json()
    assert job["status"] == "done"
    assert job["result"]["product"]["source_url"] == url
    assert job["result"]["product"]["data_source"] == "catalogue"


def test_url_job_without_reviews_fails_with_a_reason(client):
    job_id = client.post("/api/v3/analyses", json={"url": "https://www.flipkart.com/boat-airdopes-141/p/itm9"}).json()["job_id"]
    job = client.get(f"/api/v3/analyses/{job_id}").json()
    assert job["status"] == "failed"
    assert "catalogue" in job["error"]
    assert "demo mode" in job["error"]  # don't blame Flipkart when we never asked it


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"product_id": "realme-buds-t310", "url": "https://www.flipkart.com/x/p/y"},
        {"url": "https://www.amazon.in/dp/B0X"},
        {"url": "https://www.flipkart.com/" + "a" * 2048},
    ],
    ids=["neither", "both", "not_flipkart", "too_long"],
)
def test_bad_requests_are_422(client, body):
    assert client.post("/api/v3/analyses", json=body).status_code == 422


def test_full_job_store_drops_oldest_finished_job(client, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_JOBS", 2)
    jobs.JOBS["old"] = jobs.AnalysisJob(job_id="old", status="done", message="")
    jobs.JOBS["busy"] = jobs.AnalysisJob(job_id="busy", status="fetching", message="")
    assert client.post("/api/v3/analyses", json={"product_id": "realme-buds-t310"}).status_code == 202
    assert list(jobs.JOBS) == ["busy", "realme-buds-t310"]


def test_job_store_full_of_running_jobs_is_429(client, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_JOBS", 1)
    jobs.JOBS["busy"] = jobs.AnalysisJob(job_id="busy", status="fetching", message="")
    assert client.post("/api/v3/analyses", json={"product_id": "realme-buds-t310"}).status_code == 429


def test_unknown_product_and_job_are_404(client):
    assert client.post("/api/v3/analyses", json={"product_id": "nope"}).status_code == 404
    assert client.get("/api/v3/analyses/nope").status_code == 404
