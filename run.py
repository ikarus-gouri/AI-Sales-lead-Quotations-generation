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
    parser.add_argument('--model', type=str, default=None, choices=['S', 'D', 'LAM', 'AI'], help='[DEPRECATED] Use --crawler and --scraper instead')
    parser.add_argument('--crawler', type=str, default='web', choices=['web', 'ai', 'unified'], help='Crawler type: web (traditional), ai (AI-powered), unified (discover + filter)')
    parser.add_argument('--scraper', type=str, default='static', choices=['static', 'lam', 'ai'], help='Scraper type: static (HTML), lam (Gemini+Playwright), ai (AI extraction)')
    parser.add_argument('--strictness', type=str, default='balanced', choices=['lenient', 'balanced', 'strict'], help='Classification strictness level')
    parser.add_argument('--max-pages', type=int, default=50, help='Maximum pages to crawl')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum crawl depth')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between requests')
    parser.add_argument('--export', type=str, default='json', help='Export formats (comma-separated)')
    parser.add_argument('--output', type=str, default='product_catalog.json', help='Output filename')
    parser.add_argument('--google-sheets', action='store_true', help='Upload results to Google Sheets')
    parser.add_argument('--sheets-id', type=str, default=None, help='Google Sheets spreadsheet ID (optional)')
    parser.add_argument('--forceai', action='store_true', help='Force Gemini AI extraction even for static sites (LAM scraper only)')
    parser.add_argument('--intent', type=str, default=None, help='User intent for AI crawler/scraper (e.g., "Extract RV models with prices")')
    
    args = parser.parse_args()
    
    # Handle backward compatibility with --model parameter
    if args.model:
        print(f"\n⚠️  Note: --model is deprecated. Use --crawler and --scraper instead.")
        model_map = {
            'S': ('web', 'static'),
            'D': ('web', 'static'),  # Model D removed
            'LAM': ('unified', 'lam'),
            'AI': ('unified', 'ai')  # Updated to use unified crawler
        }
        if args.model in model_map:
            args.crawler, args.scraper = model_map[args.model]
            print(f"    Mapped to: --crawler {args.crawler} --scraper {args.scraper}\\n")
    
    # Parse export formats
    if args.export.lower() == 'all':
        export_formats = ['json', 'csv', 'csv_prices', 'quotation']
    else:
        export_formats = [fmt.strip().lower() for fmt in args.export.split(',')]
        # Remove 'google sheets' from export formats if present
        export_formats = [fmt for fmt in export_formats if fmt not in ['google sheets', 'google_sheets', 'sheets']]
        if not export_formats:
            export_formats = ['json']  # Default to json if only google sheets was specified
    
    # Validate intent requirement for AI/unified crawler
    if args.crawler in ['ai', 'unified'] and not args.intent:
        print(f"⚠️  {args.crawler.upper()} crawler requires --intent parameter")
        print("   Example: --intent 'Extract custom projects with pricing info'\n")
        sys.exit(1)
    
    # Display configuration
    crawler_names = {'web': 'Web Crawler (Traditional)', 'ai': 'AI Crawler (Gemini-powered)', 'unified': 'Unified Crawler (Discover + Filter)'}
    scraper_names = {'static': 'Static (HTML parsing)', 'lam': 'LAM (Gemini+Playwright)', 'ai': 'AI (AI-powered extraction)'}
    
    print("\n" + "="*80)
    print(f"PRODUCT CATALOG SCRAPER")
    print("="*80)
    print(f"Crawler:         {crawler_names[args.crawler]}")
    print(f"Scraper:         {scraper_names[args.scraper]}")
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
    if args.forceai and args.scraper == 'lam':
        print(f"Force AI:        Enabled (No fallback to static)")
    if args.intent:
        print(f"User Intent:     {args.intent}")
    print("="*80 + "\n")
    
    # Create configuration
    config = ScraperConfig(
        base_url=args.url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        crawl_delay=args.delay,
        output_filename=args.output,
        user_intent=args.intent if args.crawler == 'ai' or args.scraper in ['lam', 'ai'] else None
    )
    
    # Step 1: Initialize Crawler
    product_urls = None
    
    if args.crawler == 'unified':
        # New unified crawler: discover + filter
        try:
            from src.crawlers.crawler import Crawler
            from src.utils.http_client import HTTPClient
            from src.extractors.link_extractor import LinkExtractor
            import os
            
            gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
            if not gemini_key:
                raise ValueError("GEMINI_API_KEY required for unified crawler")
            
            http_client = HTTPClient(use_cache=config.use_cache)
            link_extractor = LinkExtractor()
            unified_crawler = Crawler(
                base_url=config.base_url,
                http_client=http_client,
                link_extractor=link_extractor,
                gemini_api_key=gemini_key,
                crawl_delay=config.crawl_delay
            )
            
            # Run both phases
            results = unified_crawler.crawl(
                user_intent=args.intent,
                max_pages=config.max_pages,
                max_depth=config.max_depth
            )
            
            # Extract URLs from filtered results
            product_urls = set([item.url for item in results['filtered_urls']])
            print(f"\n✓ Unified Crawler: {len(product_urls)} relevant URLs found (from {results['stats']['total_discovered']} discovered)")
            
        except (ImportError, ValueError) as e:
            print(f"⚠️  Unified crawler not available: {e}")
            print("   Falling back to Web Crawler\n")
            product_urls = None
    
    elif args.crawler == 'ai':
        # Legacy AI crawler
        try:
            from src.crawlers.ai_crawler import AICrawler
            import os
            
            jina_key = os.getenv('JINA_API_KEY')
            gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
            
            if not jina_key or not gemini_key:
                raise ValueError("JINA_API_KEY and GEMINI_API_KEY required for AI crawler")
            
            ai_crawler = AICrawler(jina_key, gemini_key, use_cache=config.use_cache)
            product_urls = ai_crawler.crawl(config.base_url, args.intent, config.max_pages)
            print(f"\n✓ AI Crawler discovered {len(product_urls)} product URLs")
        except (ImportError, ValueError) as e:
            print(f"⚠️  AI crawler not available: {e}")
            print("   Falling back to Web Crawler\n")
            product_urls = None  # Will use web crawler in scraper
    
    # Step 2: Initialize Scraper
    is_async = args.scraper in ['lam', 'ai']
    
    if args.scraper == 'lam':
        try:
            from src.core.lam_scraper import LAMScraper
            scraper = LAMScraper(config, strictness=args.strictness, enable_gemini=True, force_ai=args.forceai)
        except ImportError as e:
            print(f"⚠️  LAM scraper not available: {e}")
            print("   Falling back to Static scraper\n")
            scraper = BalancedScraper(config, strictness=args.strictness)
            is_async = False
    
    elif args.scraper == 'ai':
        try:
            from src.core.ai_scraper import AIScraper
            scraper = AIScraper(config, user_intent=args.intent)
        except ImportError as e:
            print(f"⚠️  AI scraper not available: {e}")
            print("   Falling back to Static scraper\n")
            scraper = BalancedScraper(config, strictness=args.strictness)
            is_async = False
    
    else:  # static
        scraper = BalancedScraper(config, strictness=args.strictness)
    
    # Step 3: Scrape all products
    if is_async:
        catalog = await scraper.scrape_all_products(product_urls)
    else:
        catalog = scraper.scrape_all_products(product_urls)
    
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
    
    # Fix for Windows: Set event loop policy for subprocess support (Playwright)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(run_scraper_async())