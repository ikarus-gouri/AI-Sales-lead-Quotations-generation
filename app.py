"""
FastAPI wrapper for the Product Catalog Web Scraper
HF Spaces (Docker) compatible - WITH BALANCED SCRAPER AND GOOGLE SHEETS
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

from src.core.config import ScraperConfig
from src.core.balanced_scraper import BalancedScraper
from src.storage.google_sheets import GoogleSheetsStorage


# ============================================================
# APP INITIALIZATION
# ============================================================

app = FastAPI(
    title="Product Catalog Scraper API",
    description="Extract structured product catalogs from e-commerce websites using balanced scraping approach",
    version="2.1.0",
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
# GOOGLE SHEETS CONFIGURATION
# ============================================================

# Initialize Google Sheets (will be None if credentials not available)
google_sheets = None

def init_google_sheets():
    """Initialize Google Sheets with environment-based credentials."""
    global google_sheets
    
    try:
        # Check for credentials in environment variable (preferred for HF Spaces)
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDS_JSON')
        
        if creds_json:
            # GoogleSheetsStorage will handle the JSON string internally
            google_sheets = GoogleSheetsStorage()
            print("✓ Google Sheets initialized from environment variable")
        else:
            # Try file-based credentials
            creds_file = os.environ.get('GOOGLE_SHEETS_CREDS_FILE', 'credentials.json')
            if os.path.exists(creds_file):
                google_sheets = GoogleSheetsStorage(credentials_file=creds_file)
                print(f"✓ Google Sheets initialized from {creds_file}")
            else:
                print("ℹ Google Sheets credentials not found - feature disabled")
                print("  To enable: Set GOOGLE_SHEETS_CREDS_JSON environment variable")
                google_sheets = None
            
    except Exception as e:
        print(f"⚠ Failed to initialize Google Sheets: {e}")
        traceback.print_exc()
        google_sheets = None

# Initialize on startup
init_google_sheets()


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
    model: str = Field("S", pattern="^(S|LAM)$", description="Scraping model: S (static) or LAM (Gemini + Playwright)")
    headless: bool = Field(True, description="Deprecated parameter (no browser mode)")
    google_sheets_upload: bool = Field(False, description="Upload results to Google Sheets")
    google_sheets_id: Optional[str] = Field(None, description="Existing spreadsheet ID (uses env default if not provided)")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://example.com",
                "max_pages": 50,
                "max_depth": 3,
                "crawl_delay": 0.5,
                "export_formats": ["json", "csv"],
                "strictness": "balanced",
                "model": "LAM",
                "headless": False,
                "google_sheets_upload": False,
                "google_sheets_id": None
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


class GoogleSheetsUploadRequest(BaseModel):
    job_id: str
    spreadsheet_id: Optional[str] = Field(None, description="Existing spreadsheet ID (uses env default if not provided)")
    spreadsheet_title: Optional[str] = Field("Product Catalog", description="Title for new spreadsheet")
    include_prices: bool = Field(True, description="Include prices in the sheet")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "abc-123",
                "spreadsheet_id": None,
                "spreadsheet_title": "My Product Catalog",
                "include_prices": True
            }
        }


# ============================================================
# SCRAPER EXECUTION (BACKGROUND)
# ============================================================

async def run_scraper_job_async(job_id: str, request: ScrapeRequest):
    """Execute scraping job (supports LAM with Gemini + Playwright or static S)"""
    try:
        jobs[job_id]["status"] = "running"
        jobs[job_id]["message"] = f"Scraping started (model: {request.model}, strictness: {request.strictness})"
        jobs[job_id]["progress"] = {
            "stage": "initializing",
            "model": request.model,
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

        # Choose scraper based on model
        if request.model == "LAM":
            try:
                from src.core.lam_scraper import LAMScraper
                scraper = LAMScraper(config, strictness=request.strictness, enable_gemini=True)
                model_used = "LAM"
                
                jobs[job_id]["progress"] = {
                    "stage": "identifying",
                    "message": "[LAM Step 1] Identifying all product pages",
                    "model": "LAM"
                }
            except ImportError as e:
                print(f"⚠️ LAM model not available: {e}")
                print("   Falling back to Model S (static)")
                scraper = BalancedScraper(config, strictness=request.strictness)
                model_used = "S"
                jobs[job_id]["progress"] = {
                    "stage": "crawling",
                    "message": f"LAM unavailable, using static model (strictness: {request.strictness})",
                    "model": "S"
                }
        else:
            # Use static scraper (Model S)
            scraper = BalancedScraper(config, strictness=request.strictness)
            model_used = "S"
            jobs[job_id]["progress"] = {
                "stage": "crawling",
                "message": f"Discovering pages (strictness: {request.strictness})",
                "model": "S"
            }
        
        # Scrape with selected model
        # LAM scraper's scrape_all_products is async, BalancedScraper's is sync
        if model_used == "LAM":
            catalog = await scraper.scrape_all_products()
        else:
            catalog = scraper.scrape_all_products()

        # Handle both catalog formats
        if isinstance(catalog, dict) and 'products' in catalog:
            # New LAM format
            products = catalog['products']
            total_products = len(products)
        else:
            # Old format (dict of product_name: data)
            products = catalog
            total_products = len(catalog) if catalog else 0
        
        if total_products == 0:
            raise RuntimeError(
                f"No products found with {request.strictness} strictness using Model {model_used}. "
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

        result_data = {
            "total_products": total_products,
            "strictness": request.strictness,
            "model_used": model_used,
            "files": files,
        }
        
        # Add LAM-specific stats if available
        if isinstance(catalog, dict) and 'configurators_detected' in catalog:
            result_data["configurators_detected"] = catalog.get('configurators_detected', 0)
            result_data["workflow"] = catalog.get('workflow', 'standard')

        # Google Sheets upload if requested
        if request.google_sheets_upload:
            if google_sheets is None or google_sheets.service is None:
                jobs[job_id]["progress"] = {
                    "stage": "google_sheets_skipped",
                    "message": "Google Sheets not configured - skipping upload",
                }
                result_data["google_sheets"] = {
                    "uploaded": False,
                    "error": "Google Sheets not configured on this server"
                }
            else:
                try:
                    jobs[job_id]["progress"] = {
                        "stage": "google_sheets_upload",
                        "message": "Uploading to Google Sheets",
                    }
                    
                    # Use provided ID or fall back to environment variable
                    sheets_id = request.google_sheets_id
                    if not sheets_id:
                        sheets_id = os.getenv('GOOGLE_SPREADSHEET_ID')
                        if sheets_id:
                            print(f"ℹ Using default spreadsheet ID from environment")
                    
                    # Upload to Google Sheets (convert to old format if needed)
                    catalog_for_sheets = catalog
                    if isinstance(catalog, dict) and 'products' in catalog:
                        # Convert LAM format to dict format for Google Sheets
                        catalog_for_sheets = {}
                        for i, product in enumerate(catalog['products']):
                            key = f"{product.get('product_name', 'product')}_{i}"
                            catalog_for_sheets[key] = product
                    
                    spreadsheet_id = google_sheets.save_catalog(
                        catalog=catalog_for_sheets,
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

        # Update job as completed
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = f"Scraping completed successfully using Model {model_used}"
        jobs[job_id]["result"] = result_data
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
        
        completion_msg = f"Found {total_products} products"
        if model_used == "LAM" and isinstance(catalog, dict) and 'configurators_detected' in catalog:
            completion_msg += f" ({catalog['configurators_detected']} with configurators)"
        
        jobs[job_id]["progress"] = {
            "stage": "completed",
            "message": completion_msg,
            "model": model_used
        }

    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)
        jobs[job_id]["completed_at"] = datetime.now().isoformat()
        jobs[job_id]["progress"] = {
            "stage": "failed",
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        print(f"Job {job_id} failed: {e}")
        traceback.print_exc()


def run_scraper_job(job_id: str, request: ScrapeRequest):
    """Wrapper to run async scraper job in background thread"""
    import asyncio
    
    try:
        # Create new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run async function
        loop.run_until_complete(run_scraper_job_async(job_id, request))
    finally:
        loop.close()


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def read_root():
    """Redirect to API documentation"""
    return {
        "message": "Product Catalog Scraper API",
        "version": "2.1.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    # Check LAM availability
    lam_available = False
    gemini_available = False
    try:
        from src.core.lam_scraper import LAMScraper
        lam_available = True
        # Check if Gemini API key is available
        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        gemini_available = bool(gemini_api_key)
    except ImportError:
        pass
    
    return {
        "status": "healthy",
        "version": "2.1.0",
        "scraper_type": "balanced",
        "models_available": {
            "S": True,
            "LAM": lam_available,
            "gemini_configured": gemini_available
        },
        "google_sheets_available": google_sheets is not None and google_sheets.service is not None,
        "default_spreadsheet_configured": os.getenv('GOOGLE_SPREADSHEET_ID') is not None,
        "active_jobs": len([j for j in jobs.values() if j["status"] == "running"]),
        "max_active_jobs": MAX_ACTIVE_JOBS
    }


@app.get("/features")
def get_features():
    """Get available features and their status"""
    default_sheets_id = os.getenv('GOOGLE_SPREADSHEET_ID')
    
    # Check LAM availability
    lam_available = False
    gemini_available = False
    try:
        from src.core.lam_scraper import LAMScraper
        lam_available = True
        gemini_api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        gemini_available = bool(gemini_api_key)
    except ImportError:
        pass
    
    return {
        "models": {
            "S": {
                "available": True,
                "description": "Static scraping with balanced classification",
                "features": ["Fast", "No API costs", "Works offline"]
            },
            "LAM": {
                "available": lam_available,
                "gemini_configured": gemini_available,
                "description": "AI-powered with Gemini + Playwright interactive extraction",
                "features": ["Intelligent configurator detection", "Interactive extraction", "Higher accuracy"],
                "workflow": [
                    "Step 1: Identify all product pages",
                    "Step 2: Gemini detects configurators",
                    "Step 3: Playwright + Gemini interactive extraction"
                ]
            }
        },
        "google_sheets": {
            "enabled": google_sheets is not None and google_sheets.service is not None,
            "default_spreadsheet_configured": default_sheets_id is not None,
            "default_spreadsheet_id": default_sheets_id if default_sheets_id else None
        },
        "strictness_levels": ["lenient", "balanced", "strict"],
        "export_formats": ["json", "csv", "csv_prices", "quotation"]
    }


@app.post("/scrape", response_model=JobStatus)
def start_scrape(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start a new scraping job
    
    This endpoint initiates a background scraping job and returns immediately
    with a job_id that can be used to track progress.
    """
    # Check active jobs limit
    active = len([j for j in jobs.values() if j["status"] == "running"])
    if active >= MAX_ACTIVE_JOBS:
        raise HTTPException(
            status_code=429, 
            detail=f"Too many active jobs ({active}/{MAX_ACTIVE_JOBS}). Please wait."
        )
    
    # Create job
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "message": "Job created, starting soon...",
        "progress": None,
        "result": None,
        "created_at": datetime.now().isoformat(),
        "completed_at": None,
        "strictness": request.strictness,
    }

    # Start background task
    background_tasks.add_task(run_scraper_job, job_id, request)
    
    return JobStatus(**jobs[job_id])


@app.post("/google-sheets/upload")
def upload_to_google_sheets(request: GoogleSheetsUploadRequest):
    """
    Upload completed job results to Google Sheets
    
    This endpoint allows uploading results after scraping is complete.
    Useful if you didn't enable google_sheets_upload during scraping.
    """
    if google_sheets is None or google_sheets.service is None:
        raise HTTPException(
            status_code=503,
            detail="Google Sheets integration not available on this server"
        )
    
    # Check if job exists
    if request.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[request.job_id]
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed (status: {job['status']})"
        )
    
    # Load catalog from JSON file
    json_file = f"{RESULTS_DIR}/{request.job_id}.json"
    if not os.path.exists(json_file):
        raise HTTPException(status_code=404, detail="Catalog file not found")
    
    try:
        with open(json_file, 'r') as f:
            catalog_data = json.load(f)
        
        # Handle different JSON structures
        if isinstance(catalog_data, list):
            catalog_dict = {f"product_{i}": product for i, product in enumerate(catalog_data)}
        elif isinstance(catalog_data, dict) and "products" in catalog_data:
            catalog_dict = {f"product_{i}": product for i, product in enumerate(catalog_data["products"])}
        else:
            catalog_dict = catalog_data
        
        # Use provided ID or fall back to environment variable
        sheets_id = request.spreadsheet_id
        if not sheets_id:
            sheets_id = os.getenv('GOOGLE_SPREADSHEET_ID')
            if sheets_id:
                print(f"ℹ Using default spreadsheet ID from environment")
        
        # Upload to Google Sheets
        spreadsheet_id = google_sheets.save_catalog(
            catalog=catalog_dict,
            spreadsheet_id=sheets_id,
            title=request.spreadsheet_title,
            include_prices=request.include_prices
        )
        
        if spreadsheet_id:
            return {
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
                "message": "Successfully uploaded to Google Sheets"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload to Google Sheets"
            )
            
    except Exception as e:
        print(f"✗ Upload to Google Sheets failed: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload to Google Sheets: {str(e)}"
        )


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
        "version": "3.0.0",
        "scraper_type": "static",
        "models": {
            "S": {
                "name": "Model S (Static)",
                "description": "Static HTML scraping",
                "use_case": "All product pages",
                "speed": "Fast",
                "browser_required": False
            }
        },
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
        "integrations": {
            "google_sheets": {
                "available": google_sheets is not None and google_sheets.service is not None,
                "default_configured": os.getenv('GOOGLE_SPREADSHEET_ID') is not None,
                "description": "Upload results directly to Google Sheets",
                "methods": [
                    "Set google_sheets_upload=True in /scrape request",
                    "Use /google-sheets/upload endpoint after scraping"
                ]
            }
        },
        "limits": {
            "max_active_jobs": MAX_ACTIVE_JOBS,
            "max_pages": 300,
            "max_depth": 5,
            "max_crawl_delay": 5.0,
            "min_crawl_delay": 0.1
        }
    }


@app.post("/scrape/static", response_model=JobStatus)
def start_scrape_static(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Start Model S (Static) scraping job
    
    Force static scraping regardless of page type.
    Fast but may not work on JavaScript-heavy pages.
    """
    request.model = "S"
    return start_scrape(request, background_tasks)

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