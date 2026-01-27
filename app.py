"""FastAPI wrapper for the web scraper."""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
import uvicorn
import uuid
import os
import json
from datetime import datetime

from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper

# Initialize FastAPI
app = FastAPI(
    title="Product Catalog Scraper API",
    description="Extract product catalogs from any e-commerce website",
    version="1.0.0",
    docs_url="/",  # Swagger UI at root
    redoc_url="/redoc"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage for scraping jobs
jobs = {}
RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)


# Request/Response Models
class ScrapeRequest(BaseModel):
    url: HttpUrl = Field(..., description="Target website URL to scrape")
    max_pages: int = Field(50, ge=1, le=500, description="Maximum pages to crawl (1-500)")
    max_depth: int = Field(3, ge=1, le=5, description="Maximum crawl depth (1-5)")
    crawl_delay: float = Field(0.5, ge=0.1, le=5.0, description="Delay between requests in seconds")
    export_formats: List[str] = Field(
        ["json"],
        description="Export formats: json, csv, csv_prices, quotation"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com/products",
                "max_pages": 50,
                "max_depth": 3,
                "crawl_delay": 0.5,
                "export_formats": ["json", "csv"]
            }
        }


class JobStatus(BaseModel):
    job_id: str
    status: str  # "pending", "running", "completed", "failed"
    message: str
    progress: Optional[dict] = None
    result: Optional[dict] = None
    created_at: str
    completed_at: Optional[str] = None


# Helper Functions
def run_scraper_job(job_id: str, request: ScrapeRequest):
    """Background task to run the scraper."""
    try:
        # Update job status
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = "Scraping in progress..."
        
        # Create config
        config = ScraperConfig(
            base_url=str(request.url),
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            crawl_delay=request.crawl_delay,
            output_dir=RESULTS_DIR,
            output_filename=f"{job_id}.json"
        )
        
        # Run scraper
        scraper = TheraluxeScraper(config)
        
        # Update progress
        jobs[job_id]["progress"] = {"stage": "crawling", "message": "Discovering pages..."}
        
        catalog = scraper.scrape_all_products()
        
        if not catalog:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["message"] = "No products found on the website"
            jobs[job_id]["completed_at"] = datetime.now().isoformat()
            return
        
        # Update progress
        jobs[job_id]["progress"] = {"stage": "exporting", "message": "Saving results..."}
        
        # Save catalog
        scraper.save_catalog(catalog, export_formats=request.export_formats)
        
        # Build result
        result = {
            "total_products": len(catalog),
            "products": list(catalog.keys()),
            "files": {
                "json": f"{RESULTS_DIR}/{job_id}.json"
            }
        }
        
        # Add other format files
        if "csv" in request.export_formats:
            result["files"]["csv"] = f"{RESULTS_DIR}/{job_id}.csv"
        if "csv_prices" in request.export_formats:
            result["files"]["csv_prices"] = f"{RESULTS_DIR}/{job_id}_with_prices.csv"
        if "quotation" in request.export_formats:
            result["files"]["quotation"] = f"{RESULTS_DIR}/{job_id}_quotation_template.json"
        
        # Update job
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"Successfully scraped {len(catalog)} products"
        jobs[job_id]["result"] = result
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Error: {str(e)}"
        jobs[job_id]["completed_at"] = datetime.now().isoformat()


# API Endpoints
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_jobs": len([j for j in jobs.values() if j["status"] == "running"])
    }


@app.post("/scrape", response_model=JobStatus)
async def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a new scraping job.
    
    Returns a job_id that can be used to check status and download results.
    """
    # Validate export formats
    valid_formats = ["json", "csv", "csv_prices", "quotation"]
    invalid_formats = [f for f in request.export_formats if f not in valid_formats]
    if invalid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid export formats: {', '.join(invalid_formats)}"
        )
    
    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "message": "Job queued",
        "progress": None,
        "result": None,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "request": request.dict()
    }
    
    # Start background task
    background_tasks.add_task(run_scraper_job, job_id, request)
    
    return JobStatus(**jobs[job_id])


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """
    Get the status of a scraping job.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatus(**jobs[job_id])


@app.get("/jobs")
async def list_jobs():
    """
    List all scraping jobs.
    """
    return {
        "total": len(jobs),
        "jobs": [JobStatus(**job) for job in jobs.values()]
    }


@app.get("/download/{job_id}/{format}")
async def download_result(job_id: str, format: str):
    """
    Download scraping results in specified format.
    
    Formats: json, csv, csv_prices, quotation
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is {job['status']}, results not available yet"
        )
    
    # Build file path
    if format == "json":
        filepath = f"{RESULTS_DIR}/{job_id}.json"
        media_type = "application/json"
        filename = f"catalog_{job_id}.json"
    elif format == "csv":
        filepath = f"{RESULTS_DIR}/{job_id}.csv"
        media_type = "text/csv"
        filename = f"catalog_{job_id}.csv"
    elif format == "csv_prices":
        filepath = f"{RESULTS_DIR}/{job_id}_with_prices.csv"
        media_type = "text/csv"
        filename = f"catalog_prices_{job_id}.csv"
    elif format == "quotation":
        filepath = f"{RESULTS_DIR}/{job_id}_quotation_template.json"
        media_type = "application/json"
        filename = f"quotation_{job_id}.json"
    else:
        raise HTTPException(status_code=400, detail="Invalid format")
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        filepath,
        media_type=media_type,
        filename=filename
    )


@app.get("/catalog/{job_id}")
async def get_catalog(job_id: str):
    """
    Get the full catalog JSON for a completed job.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job is {job['status']}, results not available yet"
        )
    
    filepath = f"{RESULTS_DIR}/{job_id}.json"
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Catalog file not found")
    
    with open(filepath, 'r') as f:
        catalog = json.load(f)
    
    return catalog


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a job and its results.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Delete files
    files_to_delete = [
        f"{RESULTS_DIR}/{job_id}.json",
        f"{RESULTS_DIR}/{job_id}.csv",
        f"{RESULTS_DIR}/{job_id}_with_prices.csv",
        f"{RESULTS_DIR}/{job_id}_quotation_template.json"
    ]
    
    for filepath in files_to_delete:
        if os.path.exists(filepath):
            os.remove(filepath)
    
    # Delete job
    del jobs[job_id]
    
    return {"message": "Job deleted successfully"}


# Example endpoint for quick test
@app.post("/scrape-sync")
async def scrape_sync(request: ScrapeRequest):
    """
    Synchronous scraping (for small jobs only).
    WARNING: This will block until scraping is complete.
    Only use for max_pages <= 10
    """
    if request.max_pages > 10:
        raise HTTPException(
            status_code=400,
            detail="For large scrapes, use /scrape endpoint (async)"
        )
    
    try:
        # Create config
        config = ScraperConfig(
            base_url=str(request.url),
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            crawl_delay=request.crawl_delay,
            output_dir=RESULTS_DIR,
            output_filename=f"sync_{uuid.uuid4()}.json"
        )
        
        # Run scraper
        scraper = TheraluxeScraper(config)
        catalog = scraper.scrape_all_products()
        
        if not catalog:
            raise HTTPException(status_code=404, detail="No products found")
        
        return {
            "total_products": len(catalog),
            "catalog": catalog
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Get port from environment (for deployment platforms)
    port = int(os.environ.get("PORT", 8000))
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )