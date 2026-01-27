from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper

app = FastAPI(title=" Product Scraper API")


# -----------------------------
# Request schema
# -----------------------------
class ScrapeRequest(BaseModel):
    url: str
    max_pages: int = 50
    max_depth: int = 3
    delay: float = 0.5
    ai: bool = False


# -----------------------------
# API endpoint
# -----------------------------
@app.post("/scrape")
def scrape(req: ScrapeRequest):
    # Create configuration
    config = ScraperConfig(
        base_url=req.url,
        use_ai_classification=req.ai,
        max_pages=req.max_pages,
        max_depth=req.max_depth,
        crawl_delay=req.delay
    )

    # Validate config
    if not config.validate():
        raise HTTPException(
            status_code=400,
            detail="Configuration validation failed"
        )

    # Initialize scraper
    scraper = TheraluxeScraper(config)

    # Run scraper
    catalog = scraper.scrape_all_products()

    if not catalog:
        raise HTTPException(
            status_code=404,
            detail="No products found"
        )

    # ✅ Google Sheets export ONLY
    try:
        print("\n📊 Exporting to Google Sheets...")
        scraper.google_sheets_exporter.export(catalog)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Google Sheets export failed: {str(e)}"
        )

    return {
        "status": "success",
        "products_scraped": len(catalog),
        "export": "google_sheets"
    }
