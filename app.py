"""
FastAPI wrapper for Product Catalog Web Scraper.
Supports both Model-S (static) and Model-D (dynamic) extraction.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import os
import json
import uvicorn
import traceback
import asyncio

from src.core.config import ScraperConfig
from src.core.balanced_scraper import BalancedScraper  # Model-S
from src.core.dynamic_scraper import DynamicScraper    # Model-D
from src.storage.google_sheets import GoogleSheetsStorage


# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(
    title="Product Catalog Scraper API (Model-S + Model-D)",
    description="""
Extract structured product catalogs using static or dynamic extraction.

**Models:**
- **Model-S**: Fast static extraction for standard product pages
- **Model-D**: Browser-based extraction for JavaScript configurators  
- **Auto**: Hybrid mode that auto-selects S or D per page (recommended)

**Features:**
- Crawl and classify product pages
- Extract customization options
- Export to JSON, CSV, Google Sheets
- Background job processing
    """,
    version="3.0.0",
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
# GLOBAL STATE
# ============================================================

RESULTS_DIR = "results"
os.makedirs(RESULTS_DIR, exist_ok=True)

jobs: Dict[str, dict] = {}
MAX_ACTIVE_JOBS = 3

# Check Playwright availability
PLAYWRIGHT_AVAILABLE = False
try:
    import playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    print("⚠️  Playwright not installed - Model-D disabled")
    print("   Install with: pip install playwright && playwright install chromium")

# Initialize Google Sheets
google_sheets = None

def init_google_sheets():
    """Initialize Google Sheets with environment-based credentials."""
    global google_sheets
    
    try:
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDS_JSON')
        
        if creds_json:
            google_sheets = GoogleSheetsStorage()
            print("✓ Google Sheets initialized from environment variable")
        else:
            creds_file = os.environ.get('GOOGLE_SHEETS_CREDS_FILE', 'credentials.json')
            if os.path.exists(creds_file):
                google_sheets = GoogleSheetsStorage(credentials_file=creds_file)
                print(f"✓ Google Sheets initialized from {creds_file}")
            else:
                print("ℹ Google Sheets credentials not found - feature disabled")
                google_sheets = None
    except Exception as e:
        print(f"⚠ Failed to initialize Google Sheets: {e}")
        google_sheets = None

init_google_sheets()


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class ScrapeRequest(BaseModel):
    url: HttpUrl
    max_pages: int = Field(50, ge=1, le=300, description="Maximum pages to crawl")
    max_depth: int = Field(3, ge=1, le=5, description="Maximum crawl depth")
    crawl_delay: float = Field(0.5, ge=0.1, le=5.0, description="Delay between requests (seconds)")
    strictness: str = Field(
        "balanced",
        pattern="^(lenient|balanced|strict)$",
        description="Classification strictness: lenient (more products) | balanced | strict (fewer products)"
    )
    export_formats: List[str] = Field(
        ["json"],
        description="Export formats: json, csv, csv_with_prices, quotation, google_sheets"
    )
    model: str = Field(
        "auto",
        pattern="^(S|D|auto)$",
        description="Extraction model: S (static) | D (dynamic) | auto (hybrid, recommended)"
    )
    enable_browser: bool = Field(
        True,
        description="Enable Model-D browser execution (only for auto mode)"
    )
    google_sheets_upload: bool = Field(
        False,
        description="Upload results to Google Sheets"
    )
    google_sheets_id: Optional[str] = Field(
        None,
        description="Existing spreadsheet ID (uses env default if not provided)"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "url": "https://example.com",
                "max_pages": 50,
                "max_depth": 3,
                "crawl_delay": 0.5,
                "strictness": "balanced",
                "export_formats": ["json", "csv"],
                "model": "auto",
                "enable_browser": True,
                "google_sheets_upload": False,
                "google_sheets_id": None
            }
        }


class ScrapeResponse(BaseModel):
    job_id: str
    status: str
    message: str
    model_used: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, running, completed, failed
    model_used: Optional[str] = None  # S, D, or hybrid
    progress: Optional[Dict] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ============================================================
# BACKGROUND SCRAPING
# ============================================================

async def run_scraping_job_async(job_id: str, request: ScrapeRequest):
    """Run scraping job asynchronously."""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started_at"] = datetime.now().isoformat()
        
        # Create config
        config = ScraperConfig(
            base_url=str(request.url),
            max_pages=request.max_pages,
            max_depth=request.max_depth,
            crawl_delay=request.crawl_delay,
            output_dir=RESULTS_DIR,
            output_filename=f"{job_id}.json"
        )
        
        # Select model
        if request.model == "S":
            # Force Model-S (static only)
            print(f"[Job {job_id}] Using Model-S (static extraction)")
            scraper = BalancedScraper(config, strictness=request.strictness)
            jobs[job_id]["model_used"] = "S"
        
        elif request.model == "D":
            # Force Model-D (dynamic only)
            if not PLAYWRIGHT_AVAILABLE:
                raise ValueError("Model-D requires Playwright. Install with: pip install playwright")
            
            print(f"[Job {job_id}] Using Model-D (dynamic extraction)")
            scraper = DynamicScraper(
                config,
                strictness=request.strictness,
                enable_browser=True
            )
            jobs[job_id]["model_used"] = "D"
        
        else:  # auto
            # Hybrid mode
            enable_browser = request.enable_browser and PLAYWRIGHT_AVAILABLE
            
            if request.enable_browser and not PLAYWRIGHT_AVAILABLE:
                print(f"[Job {job_id}] ⚠️  Playwright not available, falling back to Model-S only")
            
            print(f"[Job {job_id}] Using hybrid mode (enable_browser={enable_browser})")
            scraper = DynamicScraper(
                config,
                strictness=request.strictness,
                enable_browser=enable_browser
            )
            jobs[job_id]["model_used"] = "hybrid"
        
        # Run scraping (await if DynamicScraper since it's now async)
        if isinstance(scraper, DynamicScraper):
            catalog = await scraper.scrape_all_products()
        else:
            catalog = scraper.scrape_all_products()
        
        # Check if catalog is empty
        if not catalog:
            raise RuntimeError(
                f"No products found with {request.strictness} strictness. "
                f"Try 'lenient' mode for higher recall."
            )
        
        # Save results
        scraper.save_catalog(catalog, export_formats=request.export_formats)
        
        # Prepare file paths
        files = {"json": f"{RESULTS_DIR}/{job_id}.json"}
        if "csv" in request.export_formats:
            files["csv"] = f"{RESULTS_DIR}/{job_id}.csv"
        if "csv_prices" in request.export_formats or "csv_with_prices" in request.export_formats:
            files["csv_prices"] = f"{RESULTS_DIR}/{job_id}_with_prices.csv"
        if "quotation" in request.export_formats:
            files["quotation"] = f"{RESULTS_DIR}/{job_id}_quotation_template.json"
        
        result_data = {
            "total_products": len(catalog),
            "products_found": len(catalog),
            "strictness": request.strictness,
            "model_s_count": scraper.stats.get('model_s_count', scraper.stats.get('static_extractions', 0)),
            "model_d_count": scraper.stats.get('model_d_count', scraper.stats.get('dynamic_extractions', 0)),
            "failed_count": scraper.stats.get('failed_extractions', 0),
            "files": files
        }
        
        # Google Sheets upload if requested
        if request.google_sheets_upload:
            if google_sheets is None or google_sheets.service is None:
                result_data["google_sheets"] = {
                    "uploaded": False,
                    "error": "Google Sheets not configured on this server"
                }
                print("⚠ Google Sheets not configured - skipping upload")
            else:
                try:
                    print(f"[Job {job_id}] Uploading to Google Sheets...")
                    
                    # Use provided ID or fall back to environment variable
                    sheets_id = request.google_sheets_id
                    if not sheets_id:
                        sheets_id = os.getenv('GOOGLE_SPREADSHEET_ID')
                        if sheets_id:
                            print(f"ℹ Using default spreadsheet ID from environment")
                    
                    # Upload to Google Sheets
                    spreadsheet_id = google_sheets.save_catalog(
                        catalog=catalog,
                        spreadsheet_id=sheets_id,
                        title=f"Product Catalog - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                        include_prices=True
                    )
                    
                    if spreadsheet_id:
                        result_data["google_sheets"] = {
                            "uploaded": True,
                            "spreadsheet_id": spreadsheet_id,
                            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
                        }
                        print(f"✓ Uploaded to Google Sheets: {spreadsheet_id}")
                    else:
                        result_data["google_sheets"] = {
                            "uploaded": False,
                            "error": "Failed to upload to Google Sheets"
                        }
                        
                except Exception as e:
                    print(f"✗ Google Sheets upload failed: {e}")
                    traceback.print_exc()
                    result_data["google_sheets"] = {
                        "uploaded": False,
                        "error": str(e)
                    }
        
        # Update job status
        jobs[job_id].update({
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "result": result_data
        })
        
        print(f"[Job {job_id}] ✓ Completed successfully")
    
    except Exception as e:
        print(f"[Job {job_id}] ✗ Failed: {e}")
        jobs[job_id].update({
            "status": "failed",
            "completed_at": datetime.now().isoformat(),
            "error": str(e),
            "traceback": traceback.format_exc()
        })


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": "3.0.0",
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "google_sheets_available": google_sheets is not None and google_sheets.service is not None,
        "default_spreadsheet_configured": os.getenv('GOOGLE_SPREADSHEET_ID') is not None,
        "models": {
            "S": {
                "name": "Model-S (Static)",
                "description": "Fast extraction for standard pages",
                "available": True
            },
            "D": {
                "name": "Model-D (Dynamic)",
                "description": "Browser-based extraction for JS configurators",
                "available": PLAYWRIGHT_AVAILABLE
            },
            "auto": {
                "name": "Hybrid (Auto)",
                "description": "Auto-selects S or D per page",
                "available": True
            }
        },
        "active_jobs": len([j for j in jobs.values() if j["status"] in ["queued", "running"]]),
        "total_jobs": len(jobs)
    }


@app.post("/scrape", response_model=ScrapeResponse)
async def start_scraping(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a scraping job.
    
    **Model Selection:**
    - **S**: Static extraction only (fast, works for standard pages)
    - **D**: Dynamic browser-based (slow, handles JavaScript)
    - **auto**: Hybrid mode - auto-selects per page (recommended)
    
    **Strictness Levels:**
    - **lenient**: Detect more products (higher recall)
    - **balanced**: Good balance (recommended)
    - **strict**: Detect fewer products (higher precision)
    """
    # Check model availability
    if request.model == "D" and not PLAYWRIGHT_AVAILABLE:
        raise HTTPException(
            503,
            detail="Model-D requires Playwright. Install with: pip install playwright && playwright install chromium"
        )
    
    # Check active jobs
    active_jobs = sum(1 for j in jobs.values() if j["status"] in ["queued", "running"])
    if active_jobs >= MAX_ACTIVE_JOBS:
        raise HTTPException(
            429,
            detail=f"Too many active jobs ({active_jobs}/{MAX_ACTIVE_JOBS}). Please wait."
        )
    
    # Create job
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": "queued",
        "request": request.dict(),
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "model_used": None,
        "result": None,
        "error": None
    }
    
    # Start background task
    background_tasks.add_task(run_scraping_job_async, job_id, request)
    
    return ScrapeResponse(
        job_id=job_id,
        status="queued",
        message=f"Scraping job started with Model: {request.model}",
        model_used=None  # Will be set when job starts
    )


@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get status of a specific job."""
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    
    job = jobs[job_id]
    
    return JobStatus(
        job_id=job_id,
        status=job["status"],
        model_used=job.get("model_used"),
        progress=None,  # Could add progress tracking
        result=job.get("result"),
        error=job.get("error"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at")
    )


@app.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = 50
):
    """
    List all jobs.
    
    **Query Parameters:**
    - status: Filter by status (queued, running, completed, failed)
    - limit: Maximum number of jobs to return
    """
    filtered_jobs = []
    
    for job_id, job in jobs.items():
        if status and job["status"] != status:
            continue
        
        filtered_jobs.append({
            "job_id": job_id,
            "status": job["status"],
            "model": job.get("model_used"),
            "created_at": job["created_at"],
            "completed_at": job.get("completed_at"),
            "url": job["request"]["url"],
            "products_found": job.get("result", {}).get("products_found") if job["status"] == "completed" else None
        })
    
    # Sort by creation time (newest first)
    filtered_jobs.sort(key=lambda x: x["created_at"], reverse=True)
    
    return {
        "jobs": filtered_jobs[:limit],
        "total": len(filtered_jobs)
    }


@app.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job and its results."""
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    
    # Delete job files
    for ext in ['.json', '.csv', '_with_prices.csv']:
        filepath = os.path.join(RESULTS_DIR, f"{job_id}{ext}")
        if os.path.exists(filepath):
            os.remove(filepath)
    
    # Remove from jobs dict
    del jobs[job_id]
    
    return {"message": f"Job {job_id} deleted"}


@app.get("/download/{job_id}/{format}")
async def download_results(job_id: str, format: str):
    """
    Download results file.
    
    **Formats:**
    - json: Complete catalog in JSON
    - csv: Simple CSV format
    - csv_with_prices: CSV with price breakdowns
    """
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    
    if jobs[job_id]["status"] != "completed":
        raise HTTPException(400, detail="Job not completed yet")
    
    # File mapping
    file_map = {
        "json": f"{job_id}.json",
        "csv": f"{job_id}.csv",
        "csv_with_prices": f"{job_id}_with_prices.csv"
    }
    
    if format not in file_map:
        raise HTTPException(
            400,
            detail=f"Invalid format. Available: {', '.join(file_map.keys())}"
        )
    
    filepath = os.path.join(RESULTS_DIR, file_map[format])
    
    if not os.path.exists(filepath):
        raise HTTPException(404, detail=f"File not found: {format}")
    
    return FileResponse(
        filepath,
        media_type="application/octet-stream",
        filename=file_map[format]
    )


@app.get("/catalog/{job_id}")
async def get_catalog_json(job_id: str):
    """Get catalog as JSON response (without downloading)."""
    if job_id not in jobs:
        raise HTTPException(404, detail="Job not found")
    
    if jobs[job_id]["status"] != "completed":
        raise HTTPException(400, detail="Job not completed yet")
    
    filepath = os.path.join(RESULTS_DIR, f"{job_id}.json")
    
    if not os.path.exists(filepath):
        raise HTTPException(404, detail="Catalog not found")
    
    with open(filepath, 'r') as f:
        catalog = json.load(f)
    
    return JSONResponse(catalog)


@app.get("/features")
async def get_features():
    """Get available features and their status"""
    default_sheets_id = os.getenv('GOOGLE_SPREADSHEET_ID')
    
    return {
        "google_sheets": {
            "enabled": google_sheets is not None and google_sheets.service is not None,
            "default_spreadsheet_configured": default_sheets_id is not None,
            "default_spreadsheet_id": default_sheets_id if default_sheets_id else None
        },
        "strictness_levels": ["lenient", "balanced", "strict"],
        "export_formats": ["json", "csv", "csv_prices", "quotation"]
    }


@app.get("/stats")
async def get_statistics():
    """Get system statistics."""
    total_jobs = len(jobs)
    completed = sum(1 for j in jobs.values() if j["status"] == "completed")
    failed = sum(1 for j in jobs.values() if j["status"] == "failed")
    running = sum(1 for j in jobs.values() if j["status"] == "running")
    queued = sum(1 for j in jobs.values() if j["status"] == "queued")
    
    # Model usage
    model_s_jobs = sum(1 for j in jobs.values() if j.get("model_used") == "S")
    model_d_jobs = sum(1 for j in jobs.values() if j.get("model_used") == "D")
    hybrid_jobs = sum(1 for j in jobs.values() if j.get("model_used") == "hybrid")
    
    return {
        "total_jobs": total_jobs,
        "status_breakdown": {
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed
        },
        "model_usage": {
            "model_s": model_s_jobs,
            "model_d": model_d_jobs,
            "hybrid": hybrid_jobs
        },
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "results_directory": RESULTS_DIR
    }


# ============================================================
# STARTUP
# ============================================================

@app.on_event("startup")
async def startup_event():
    """Print startup information."""
    print("\n" + "="*80)
    print("PRODUCT CATALOG SCRAPER API")
    print("="*80)
    print(f"Version: 3.0.0")
    print(f"Playwright available: {PLAYWRIGHT_AVAILABLE}")
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Install Playwright to enable Model-D:")
        print("   pip install playwright && playwright install chromium")
    print(f"Results directory: {RESULTS_DIR}")
    print("="*80 + "\n")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)