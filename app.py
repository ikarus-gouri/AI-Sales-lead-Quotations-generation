"""
FastAPI wrapper for the Product Catalog Web Scraper
HF Spaces (Docker) compatible - WITH BALANCED SCRAPER
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
from src.core.balanced_scraper import BalancedScraper


# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(
    title="Product Catalog Scraper API",
    description="Extract structured product catalogs from e-commerce websites using balanced scraping approach",
    version="2.0.0",
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
    strictness: str = Field("balanced", pattern="^(lenient|balanced|strict)$")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "max_pages": 50,
                "max_depth": 3,
                "crawl_delay": 0.5,
                "export_formats": ["json", "csv"],
                "strictness": "balanced"
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
    strictness: Optional[str] = "balanced"


# ============================================================
# SCRAPER EXECUTION (BACKGROUND)
# ============================================================

def run_scraper_job(job_id: str, request: ScrapeRequest):
    """Execute scraping job in background with balanced scraper"""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = f"Scraping started (strictness: {request.strictness})"
        jobs[job_id]["progress"] = {
            "stage": "initializing",
            "strictness": request.strictness
        }

        # Create scraper configuration
        config = ScraperConfig(
            base_url=str(request.url),
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            crawl_delay=request.crawl_delay,
            output_dir=RESULTS_DIR,
            output_filename=f"{job_id}.json",
        )

        # Initialize balanced scraper with strictness level
        scraper = BalancedScraper(config, strictness=request.strictness)

        jobs[job_id]["progress"] = {
            "stage": "crawling",
            "message": f"Discovering pages (strictness: {request.strictness})",
        }

        # Scrape all products with balanced approach
        catalog = scraper.scrape_all_products()

        if not catalog:
            raise RuntimeError(
                f"No products found with {request.strictness} strictness. "
                f"Try 'lenient' mode for higher recall."
            )

        jobs[job_id]["progress"] = {
            "stage": "exporting",
            "message": "Saving results",
        }

        # Save catalog in requested formats
        scraper.save_catalog(catalog, export_formats=request.export_formats)

        # Prepare file paths
        files = {"json": f"{RESULTS_DIR}/{job_id}.json"}
        if "csv" in request.export_formats:
            files["csv"] = f"{RESULTS_DIR}/{job_id}.csv"
        if "csv_prices" in request.export_formats:
            files["csv_prices"] = f"{RESULTS_DIR}/{job_id}_with_prices.csv"
        if "quotation" in request.export_formats:
            files["quotation"] = f"{RESULTS_DIR}/{job_id}_quotation_template.json"

        # Update job with success
        jobs[job_id].update(
            status="completed",
            message=f"Scraped {len(catalog)} products ({request.strictness} mode)",
            result={
                "total_products": len(catalog),
                "strictness": request.strictness,
                "files": files,
            },
            completed_at=datetime.now().isoformat(),
        )

    except Exception as e:
        error_message = str(e)
        jobs[job_id].update(
            status="failed",
            message=error_message,
            completed_at=datetime.now().isoformat(),
        )
        print(f"❌ Job {job_id} failed:")
        print(traceback.format_exc())


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/health")
def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_jobs": len([j for j in jobs.values() if j["status"] == "running"]),
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "scraper_type": "balanced"
    }


@app.post("/scrape", response_model=JobStatus)
def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a new scraping job with balanced scraper
    
    Strictness levels:
    - lenient: High recall, catches all products (some false positives)
    - balanced: Good precision + recall (RECOMMENDED)
    - strict: High precision, clean results (may miss some products)
    """
    # Check active jobs limit
    active_jobs = len([j for j in jobs.values() if j["status"] == "running"])
    if active_jobs >= MAX_ACTIVE_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many active jobs ({active_jobs}/{MAX_ACTIVE_JOBS}). Try again later.",
        )

    # Validate export formats
    valid_formats = {"json", "csv", "csv_prices", "quotation"}
    invalid = [f for f in request.export_formats if f not in valid_formats]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid export formats: {invalid}. Valid: {valid_formats}",
        )

    # Validate strictness
    if request.strictness not in ["lenient", "balanced", "strict"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strictness: {request.strictness}. Valid: lenient, balanced, strict",
        )

    # Create new job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "message": "Job queued",
        "progress": None,
        "result": None,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "strictness": request.strictness,
    }

    # Start background task
    background_tasks.add_task(run_scraper_job, job_id, request)
    
    return JobStatus(**jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    """Get status of a specific job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(**jobs[job_id])


@app.get("/jobs")
def list_jobs(status: Optional[str] = None, limit: int = 50):
    """
    List all jobs with optional filtering
    
    Args:
        status: Filter by status (pending, running, completed, failed)
        limit: Maximum number of jobs to return
    """
    job_list = list(jobs.values())
    
    # Filter by status if provided
    if status:
        job_list = [j for j in job_list if j["status"] == status]
    
    # Sort by creation time (newest first)
    job_list.sort(key=lambda x: x["created_at"], reverse=True)
    
    # Apply limit
    job_list = job_list[:limit]
    
    return {
        "jobs": job_list,
        "total": len(job_list),
        "filter": {"status": status, "limit": limit}
    }


@app.get("/download/{job_id}/{format}")
def download(job_id: str, format: str):
    """Download results file for a completed job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Job not completed (status: {job['status']})"
        )

    # Map format to file suffix
    suffix_map = {
        "json": ".json",
        "csv": ".csv",
        "csv_prices": "_with_prices.csv",
        "quotation": "_quotation_template.json",
    }
    
    suffix = suffix_map.get(format)
    if not suffix:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid format: {format}. Valid: {list(suffix_map.keys())}"
        )

    path = f"{RESULTS_DIR}/{job_id}{suffix}"
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404, 
            detail=f"File not found. Available formats: {list(job['result'].get('files', {}).keys())}"
        )

    return FileResponse(path, filename=os.path.basename(path))


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    """Delete a job and its associated files"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove all associated files
    files_removed = []
    for f in os.listdir(RESULTS_DIR):
        if f.startswith(job_id):
            file_path = os.path.join(RESULTS_DIR, f)
            os.remove(file_path)
            files_removed.append(f)

    # Remove job from memory
    del jobs[job_id]
    
    return {
        "message": "Job deleted successfully",
        "files_removed": files_removed
    }


@app.get("/info")
def scraper_info():
    """Get information about the scraper capabilities"""
    return {
        "version": "2.0.0",
        "scraper_type": "balanced",
        "strictness_levels": {
            "lenient": {
                "description": "High recall - catches all products, some false positives",
                "use_case": "When you want to find everything, even if it includes some noise"
            },
            "balanced": {
                "description": "Good precision + recall - recommended for most sites",
                "use_case": "Default choice for most scraping tasks"
            },
            "strict": {
                "description": "High precision - very clean results, may miss some products",
                "use_case": "When you need very clean, accurate data"
            }
        },
        "export_formats": ["json", "csv", "csv_prices", "quotation"],
        "limits": {
            "max_active_jobs": MAX_ACTIVE_JOBS,
            "max_pages": 300,
            "max_depth": 5,
            "max_crawl_delay": 5.0,
            "min_crawl_delay": 0.1
        }
    }


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