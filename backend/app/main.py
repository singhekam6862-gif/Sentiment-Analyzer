from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import catalogue, jobs, store
from app.schemas import AnalysisJob, AnalysisRequest, CatalogueProduct

app = FastAPI(
    title="Flipkart Review Analyser API",
    version="3.0.0",
    description="Turns a product's Flipkart reviews into a verdict with evidence (SPEC.md §C).",
)

# No cookies or auth, so any origin may read the public API.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])


@app.get("/api/v3/products", response_model=list[CatalogueProduct])
def list_products() -> list[CatalogueProduct]:
    return catalogue.list_products()


@app.post("/api/v3/analyses", response_model=AnalysisJob, status_code=202)
def start_analysis(req: AnalysisRequest, background: BackgroundTasks) -> AnalysisJob:
    if req.product_id and catalogue.get_product(req.product_id) is None:
        raise HTTPException(404, f"No catalogue product with id '{req.product_id}'")
    try:
        job, is_new = jobs.submit(req)
    except jobs.JobsFullError:
        raise HTTPException(429, "The server is busy with other analyses. Try again in a minute.")
    if is_new:
        background.add_task(jobs.run, job.job_id, req)
    return job


@app.get("/api/v3/analyses", response_model=list[CatalogueProduct])
def recent_analyses() -> list[CatalogueProduct]:
    return store.recent()


@app.get("/api/v3/analyses/{job_id}", response_model=AnalysisJob)
def get_analysis(job_id: str) -> AnalysisJob:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "This analysis has expired or never existed. Start it again.")
    return job
