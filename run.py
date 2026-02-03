"""Entry point for product catalog scraper - run with: python run.py"""

import sys
import os
import argparse
import asyncio
from datetime import datetime
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_scraper_async():
    """Run product scraper (static, or LAM with Gemini)"""
    from src.core.config import ScraperConfig
    from src.core.balanced_scraper import BalancedScraper
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Product Catalog Scraper')
    parser.add_argument('--url', type=str, required=True, help='Target website URL')
    parser.add_argument('--model', type=str, default='S', choices=['S', 'D', 'LAM'], help='Scraping model: S (static) or LAM (with Gemini)')
    parser.add_argument('--strictness', type=str, default='balanced', choices=['lenient', 'balanced', 'strict'], help='Classification strictness level')
    parser.add_argument('--max-pages', type=int, default=50, help='Maximum pages to crawl')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum crawl depth')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between requests')
    parser.add_argument('--export', type=str, default='json', help='Export formats (comma-separated)')
    parser.add_argument('--output', type=str, default='product_catalog.json', help='Output filename')
    parser.add_argument('--google-sheets', action='store_true', help='Upload results to Google Sheets')
    parser.add_argument('--sheets-id', type=str, default=None, help='Google Sheets spreadsheet ID (optional)')
    
    args = parser.parse_args()
    
    # Warn if Model D was requested
    if args.model == 'D':
        print("\n⚠️  Note: Model D has been removed. Use --model LAM for advanced extraction.\n")
        args.model = 'S'
    
    # Parse export formats
    if args.export.lower() == 'all':
        export_formats = ['json', 'csv', 'csv_prices', 'quotation']
    else:
        export_formats = [fmt.strip().lower() for fmt in args.export.split(',')]
        # Remove 'google sheets' from export formats if present
        export_formats = [fmt for fmt in export_formats if fmt not in ['google sheets', 'google_sheets', 'sheets']]
        if not export_formats:
            export_formats = ['json']  # Default to json if only google sheets was specified
    
    # Determine model
    use_lam = args.model == 'LAM'
    model_name = 'LAM (Gemini-Enhanced)' if use_lam else 'S (Static)'
    
    print("\n" + "="*80)
    print(f"PRODUCT CATALOG SCRAPER - MODEL {args.model or 'S'}")
    print("="*80)
    print(f"Model:           {model_name}")
    print(f"Target URL:      {args.url}")
    print(f"Strictness:      {args.strictness.upper()}")
    print(f"Max Pages:       {args.max_pages}")
    print(f"Max Depth:       {args.max_depth}")
    print(f"Crawl Delay:     {args.delay}s")
    print(f"Export Formats:  {', '.join(export_formats)}")
    print(f"Output File:     {args.output}")
    if args.google_sheets or 'google sheets' in args.export.lower():
        print(f"Google Sheets:   Enabled")
        if args.sheets_id:
            print(f"Spreadsheet ID:  {args.sheets_id}")
    print("="*80 + "\n")
    
    # Create configuration
    config = ScraperConfig(
        base_url=args.url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        crawl_delay=args.delay,
        output_filename=args.output
    )
    
    # Initialize scraper based on model
    if use_lam:
        try:
            from src.core.lam_scraper import LAMScraper
            scraper = LAMScraper(config, strictness=args.strictness, enable_gemini=True)
        except ImportError as e:
            print(f"⚠️  LAM model not available: {e}")
            print("   Falling back to Model S (static)\n")
            scraper = BalancedScraper(config, strictness=args.strictness)
    else:
        scraper = BalancedScraper(config, strictness=args.strictness)
    
    # Scrape all products (await if LAM, sync if not)
    if use_lam:
        catalog = await scraper.scrape_all_products()
    else:
        catalog = scraper.scrape_all_products()
    
    if not catalog:
        print("\n⚠️  No products found.")
        sys.exit(1)
    
    # Save catalog
    scraper.save_catalog(catalog, export_formats=export_formats)
    
    # Print summary
    scraper.print_summary(catalog)
    
    print(f"\n✅ Done! Exported to {len(export_formats)} format(s).")
    
    # Upload to Google Sheets if requested
    if args.google_sheets or 'google sheets' in args.export.lower():
        print("\n" + "="*80)
        print("UPLOADING TO GOOGLE SHEETS")
        print("="*80)
        
        try:
            from src.storage.google_sheets import GoogleSheetsStorage
            
            google_sheets = GoogleSheetsStorage()
            
            if not google_sheets.service:
                print("❌ Google Sheets credentials not configured")
                print("   Set GOOGLE_SHEETS_CREDS_JSON environment variable")
                print("   Or place credentials.json in the project root")
            else:
                # Convert catalog to dict format if needed
                if isinstance(catalog, dict) and 'products' in catalog:
                    catalog_dict = {p['product_name']: p for p in catalog['products']}
                elif isinstance(catalog, list):
                    catalog_dict = {p['product_name']: p for p in catalog}
                else:
                    catalog_dict = catalog
                
                spreadsheet_id = google_sheets.save_catalog(
                    catalog=catalog_dict,
                    spreadsheet_id=args.sheets_id or os.getenv('GOOGLE_SPREADSHEET_ID'),
                    title=f"Product Catalog - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    include_prices=True
                )
                
                print(f"✅ Uploaded to Google Sheets!")
                print(f"   Spreadsheet ID: {spreadsheet_id}")
                print(f"   View at: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
                
        except ImportError:
            print("❌ Google Sheets support not available")
            print("   Install required packages: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        except Exception as e:
            print(f"❌ Failed to upload to Google Sheets: {e}")
            import traceback
            traceback.print_exc()
    
    print()


if __name__ == "__main__":
    print("🔧 Product Catalog Scraper\n")
    asyncio.run(run_scraper_async())