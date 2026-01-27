"""
FastAPI wrapper for the Product Catalog Web Scraper
HF Spaces (Docker) compatible
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import os
import json
import uvicorn
import traceback

from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper


# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(
    title="Product Catalog Scraper API",
    description="Extract structured product catalogs from e-commerce websites",
    version="1.0.0",
    docs_url="/",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# GLOBAL STATE (HF-SAFE)
# ============================================================

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

jobs: Dict[str, dict] = {}
MAX_ACTIVE_JOBS = 2  # HF protection


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ScrapeRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(50, ge=1, le=300)
    max_depth: int = Field(3, ge=1, le=5)
    crawl_delay: float = Field(0.5, ge=0.1, le=5.0)
    export_formats: List[str] = ["json"]

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "max_pages": 50,
                "max_depth": 3,
                "crawl_delay": 0.5,
                "export_formats": ["json", "csv"],
            }
        }


class JobStatus(BaseModel):
    job_id: str
    status: str
    message: str
    progress: Optional[dict]
    result: Optional[dict]
    created_at: str
    completed_at: Optional[str]


# ============================================================
# SCRAPER EXECUTION (BACKGROUND)
# ============================================================

def run_scraper_job(job_id: str, request: ScrapeRequest):
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = "Scraping started"
        jobs[job_id]["progress"] = {"stage": "initializing"}

        config = ScraperConfig(
            base_url=str(request.url),
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            crawl_delay=request.crawl_delay,
            output_dir=RESULTS_DIR,
            output_filename=f"{job_id}.json",
        )

        scraper = TheraluxeScraper(config)

        jobs[job_id]["progress"] = {
            "stage": "crawling",
            "message": "Discovering pages",
        }

        catalog = scraper.scrape_all_products()

        if not catalog:
            raise RuntimeError("No products found")

        jobs[job_id]["progress"] = {
            "stage": "exporting",
            "message": "Saving results",
        }

        scraper.save_catalog(catalog, export_formats=request.export_formats)

        files = {"json": f"{RESULTS_DIR}/{job_id}.json"}
        if "csv" in request.export_formats:
            files["csv"] = f"{RESULTS_DIR}/{job_id}.csv"
        if "csv_prices" in request.export_formats:
            files["csv_prices"] = f"{RESULTS_DIR}/{job_id}_with_prices.csv"
        if "quotation" in request.export_formats:
            files["quotation"] = f"{RESULTS_DIR}/{job_id}_quotation_template.json"

        jobs[job_id].update(
            status="completed",
            message=f"Scraped {len(catalog)} products",
            result={
                "total_products": len(catalog),
                "files": files,
            },
            completed_at=datetime.now().isoformat(),
        )

    except Exception as e:
        jobs[job_id].update(
            status="failed",
            message=str(e),
            completed_at=datetime.now().isoformat(),
        )
        print(traceback.format_exc())


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "active_jobs": len([j for j in jobs.values() if j["status"] == "running"]),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/scrape", response_model=JobStatus)
def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    active_jobs = len([j for j in jobs.values() if j["status"] == "running"])
    if active_jobs >= MAX_ACTIVE_JOBS:
        raise HTTPException(
            status_code=429,
            detail="Too many active jobs. Try again later.",
        )

    valid_formats = {"json", "csv", "csv_prices", "quotation"}
    invalid = [f for f in request.export_formats if f not in valid_formats]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid export formats: {invalid}",
        )

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "message": "Job queued",
        "progress": None,
        "result": None,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
    }

    background_tasks.add_task(run_scraper_job, job_id, request)
    return JobStatus(**jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**jobs[job_id])


@app.get("/jobs")
def list_jobs():
    return {"jobs": list(jobs.values())}


@app.get("/download/{job_id}/{format}")
def download(job_id: str, format: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    suffix = {
        "json": ".json",
        "csv": ".csv",
        "csv_prices": "_with_prices.csv",
        "quotation": "_quotation_template.json",
    }.get(format)

    if not suffix:
        raise HTTPException(status_code=400, detail="Invalid format")

    path = f"{RESULTS_DIR}/{job_id}{suffix}"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path, filename=os.path.basename(path))


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    for f in os.listdir(RESULTS_DIR):
        if f.startswith(job_id):
            os.remove(os.path.join(RESULTS_DIR, f))

    del jobs[job_id]
    return {"message": "Job deleted"}


# ============================================================
# ENTRY POINT (HF DOCKER)
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 7860)),
        reload=False,
    )
