"""Main entry point for the balanced scraper.

This module provides the CLI interface for the product catalog scraper.
It supports two extraction models:
    - Model-S: Fast static extraction using Jina AI markdown conversion
    - Model-D: Hybrid mode with automatic routing to browser-based extraction

Architecture:
    1. Parse CLI arguments
    2. Create ScraperConfig
    3. Select scraper (BalancedScraper for Model-S, DynamicScraper for Model-D)
    4. Run scraper (crawl + extract + export)
    5. Display results
"""
# -*- coding: utf-8 -*-

import argparse
import sys
import os

# Fix Windows terminal encoding issues
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
from src.core.config import ScraperConfig
from src.core.balanced_scraper import BalancedScraper
from src.core.dynamic_scraper import DynamicScraper


def main():
    """Main function to run the balanced scraper."""
    
    parser = argparse.ArgumentParser(
        description='Dynamic Product Catalog Scraper - BALANCED MODE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
BALANCED MODE combines lenient and strict approaches for optimal results.

Strictness Levels:
  lenient  - High recall, catches all products (some false positives)
  balanced - Good precision + recall (RECOMMENDED)
  strict   - High precision, clean results (may miss some products)

Model Selection:
  S    - Model-S (static extraction only, fast)
  D    - Model-D (dynamic browser-based, slow but accurate)
  auto - Hybrid (auto-selects S or D per page, RECOMMENDED)

Examples:
  # Balanced mode with auto model selection (recommended)
  python main.py --url https://example.com/products
  
  # Force static extraction only (Model-S)
  python main.py --url https://example.com/products --model S
  
  # Force dynamic extraction with visible browser
  python main.py --url https://example.com/products --model D --no-headless
  
  # Lenient mode (catch everything)
  python main.py --url https://example.com/products --strictness lenient
  
  # Strict mode (very clean results)
  python main.py --url https://example.com/products --strictness strict
  
  # With export formats
  python main.py --url https://example.com/products --export all
  
  # Adjust crawl settings
  python main.py --url https://example.com/products --max-pages 100 --max-depth 4
  
Environment Variables (optional):
  BASE_URL              - Default URL to scrape
  GEMINI_API_KEY        - Gemini API key for AI features
  GOOGLE_CREDENTIALS_FILE - Google service account credentials
  GOOGLE_SPREADSHEET_ID - Target Google Sheets ID
        """
    )
    
    # Required: Target URL
    parser.add_argument(
        '--url',
        type=str,
        help='Target website URL to scrape (required unless set in .env)'
    )
    
    # NEW: Model selection
    parser.add_argument(
        '--model',
        type=str,
        default='auto',
        choices=['S', 'D', 'auto'],
        help="""
        Extraction model:
          S    = Model-S (static extraction only, fast)
          D    = Hybrid mode (auto-selects Model-S or Model-D per page)
          auto = Hybrid mode (same as D, recommended)
        (default: auto)
        """
    )
    
    # Strictness level
    parser.add_argument(
        '--strictness',
        type=str,
        default='balanced',
        choices=['lenient', 'balanced', 'strict'],
        help='Classification strictness (default: balanced)'
    )
    
    # Export options
    parser.add_argument(
        '--export',
        type=str,
        default='json',
        help='Export formats: json, csv, csv_prices, quotation, google_sheets, all (comma-separated)'
    )
    
    # Crawling options
    parser.add_argument(
        '--max-pages',
        type=int,
        default=50,
        help='Maximum pages to crawl (default: 50)'
    )
    
    parser.add_argument(
        '--max-depth',
        type=int,
        default=3,
        help='Maximum crawl depth (default: 3)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )
    
    # Output options
    parser.add_argument(
        '--output',
        type=str,
        default='product_catalog.json',
        help='Output filename (default: product_catalog.json)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='data/catalogs',
        help='Output directory (default: data/catalogs)'
    )
    
    # Model-D specific options
    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='Run browser in headless mode (Model-D only, default: True)'
    )
    
    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Show browser UI for debugging (Model-D only)'
    )
    
    parser.add_argument(
        '--disable-browser',
        action='store_true',
        help='Disable browser execution (forces Model-S even in auto mode)'
    )
    
    # Verbose output
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Get URL from args or env
    url = args.url or os.getenv('BASE_URL')
    
    if not url:
        print("\n❌ Error: No URL provided")
        print("   Use --url flag or set BASE_URL in .env file\n")
        sys.exit(1)
    
    # Parse export formats
    if args.export.lower() == 'all':
        export_formats = ['json', 'csv', 'csv_prices', 'quotation', 'google_sheets']
    else:
        export_formats = [fmt.strip() for fmt in args.export.split(',')]
    
    # Create configuration
    config = ScraperConfig(
        base_url=url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        output_filename=args.output,
        output_dir=args.output_dir,
        crawl_delay=args.delay
    )
    
    # Validate configuration
    if not config.validate():
        print("\n❌ Configuration validation failed. Please fix the errors above.\n")
        sys.exit(1)
    
    # Show configuration
    print("\n" + "="*80)
    print("SCRAPER CONFIGURATION - BALANCED MODE")
    print("="*80)
    print(f"Target URL:      {config.base_url}")
    print(f"Model:           {args.model.upper()}")
    print(f"Strictness:      {args.strictness.upper()}")
    print(f"Max Pages:       {config.max_pages}")
    print(f"Max Depth:       {config.max_depth}")
    print(f"Crawl Delay:     {config.crawl_delay}s")
    print(f"Export Formats:  {', '.join(export_formats)}")
    print(f"Output Dir:      {config.output_dir}")
    print(f"Output File:     {config.output_filename}")
    print("="*80 + "\n")
    
    # Explain model and strictness level
    model_info = {
        "S": "Static extraction only - Fast, efficient, no browser required",
        "D": "Hybrid/Auto mode - Intelligently selects Model-S or Model-D per page (RECOMMENDED)",
        "auto": "Hybrid mode - Auto-selects Model-S or Model-D per page (RECOMMENDED)"
    }
    
    strictness_info = {
        "lenient": "High recall - catches all products, some false positives",
        "balanced": "Good precision + recall - recommended for most sites",
        "strict": "High precision - very clean results, may miss some products"
    }
    
    print(f"[INFO] Model: {model_info[args.model]}")
    print(f"[INFO] Strictness: {strictness_info[args.strictness]}\n")
    
    # Initialize scraper based on model selection
    if args.model == "S":
        # Model-S: Static extraction only
        print("[Model-S] Using Static Extraction Only")
        print("   - Fast, efficient")
        print("   - Works for standard product pages")
        print("   - No browser required\n")
        
        scraper = BalancedScraper(config, strictness=args.strictness)
    
    elif args.model == "D":
        # Model-D: Dynamic extraction only
        print("[Model-D] Using Hybrid Mode (Auto-Select S/D)")
        print("   - Intelligently chooses between static and dynamic extraction")
        print("   - Uses Model-S for standard pages (fast)")
        print("   - Uses Model-D for JavaScript configurators (accurate)")
        print("   - Requires browser (Playwright) for dynamic pages\n")
        
        # Check if Playwright is installed
        try:
            import playwright
        except ImportError:
            print("[ERROR] Playwright not installed!")
            print("\nTo use Model-D, install Playwright:")
            print("  pip install playwright")
            print("  playwright install chromium\n")
            sys.exit(1)
        
        scraper = DynamicScraper(
            config,
            strictness=args.strictness,
            enable_browser=True,
            headless=(not args.no_headless)
        )
    
    else:  # auto
        # Hybrid mode (recommended)
        print("[Model-AUTO] Using Hybrid S+D")
        print("   - Best of both worlds")
        print("   - Auto-selects Model-S or Model-D per page")
        print("   - Requires browser (Playwright)\n")
        
        # Check if browser should be enabled
        enable_browser = not args.disable_browser
        
        if enable_browser:
            try:
                import playwright
            except ImportError:
                print("[WARNING] Playwright not installed")
                print("   Falling back to Model-S only")
                print("\nTo enable Model-D:")
                print("  pip install playwright")
                print("  playwright install chromium\n")
                enable_browser = False
        
        scraper = DynamicScraper(
            config,
            strictness=args.strictness,
            enable_browser=enable_browser,
            headless=(not args.no_headless)
        )
    
    # Confirm before starting
    try:
        user_input = input("Press Enter to start scraping (or Ctrl+C to cancel)... ")
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Scraping cancelled by user.\n")
        sys.exit(0)
    
    # Scrape all products
    try:
        # Handle async scraper (DynamicScraper) vs sync scraper (BalancedScraper)
        if isinstance(scraper, DynamicScraper):
            # DynamicScraper.scrape_all_products() is async
            import asyncio
            catalog = asyncio.run(scraper.scrape_all_products())
        else:
            # BalancedScraper.scrape_all_products() is sync
            catalog = scraper.scrape_all_products()
        
        if not catalog:
            print("\n[WARNING] No products found. Possible solutions:")
            print("   • Try --strictness lenient for higher recall")
            print("   • Try --model D for dynamic extraction")
            print("   • Increase --max-pages or --max-depth")
            print("   • The website structure might not match expected patterns")
            print("   • Verify the base URL is correct\n")
            sys.exit(1)
        
        # Save to specified formats
        print(f"\n{'='*80}")
        print("EXPORTING CATALOG")
        print(f"{'='*80}\n")
        
        scraper.save_catalog(catalog, export_formats=export_formats)
        
        # Print summary
        scraper.print_summary(catalog)
        
        print(f"\n[SUCCESS] Done! Exported to {len(export_formats)} format(s).\n")
        
        # Show file locations
        print("[OUTPUT] Output files:")
        base_path = os.path.join(config.output_dir, config.output_filename)
        
        if 'json' in export_formats:
            print(f"   • JSON: {base_path}")
        if 'csv' in export_formats:
            print(f"   • CSV: {base_path.replace('.json', '.csv')}")
        if 'csv_prices' in export_formats:
            print(f"   • CSV (with prices): {base_path.replace('.json', '_with_prices.csv')}")
        if 'quotation' in export_formats:
            print(f"   • Quotation Template: {base_path.replace('.json', '_quotation_template.json')}")
        if 'google_sheets' in export_formats:
            print(f"   • Google Sheets: Check console output for URL")
        print()
        
        return 0
    
    except KeyboardInterrupt:
        print("\n\n[WARNING] Scraping interrupted by user")
        return 130
    
    except Exception as e:
        print(f"\n[ERROR] Error during scraping: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())