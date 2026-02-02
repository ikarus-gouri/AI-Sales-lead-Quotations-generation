"""Entry point for product catalog scraper - run with: python run.py"""

import sys
import os
import argparse

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_scraper():
    """Run product scraper (static only)"""
    from src.core.config import ScraperConfig
    from src.core.balanced_scraper import BalancedScraper
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Product Catalog Scraper')
    parser.add_argument('--url', type=str, required=True, help='Target website URL')
    parser.add_argument('--max-pages', type=int, default=50, help='Maximum pages to crawl')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum crawl depth')
    parser.add_argument('--delay', type=float, default=0.5, help='Delay between requests')
    parser.add_argument('--strictness', type=str, default='balanced', choices=['lenient', 'balanced', 'strict'])
    parser.add_argument('--output', type=str, default='product_catalog.json', help='Output filename')
    parser.add_argument('--export', type=str, default='json', help='Export formats (comma-separated)')
    parser.add_argument('--model', type=str, choices=['S', 'D'], help='Deprecated: Model D removed, always uses static scraping')
    
    args = parser.parse_args()
    
    # Warn if Model D was requested
    if args.model == 'D':
        print("\n⚠️  Note: Model D has been removed. Using static scraping (Model S).\n")
    
    # Parse export formats
    if args.export.lower() == 'all':
        export_formats = ['json', 'csv', 'csv_prices', 'quotation']
    else:
        export_formats = [fmt.strip() for fmt in args.export.split(',')]
    
    print("\n" + "="*80)
    print("PRODUCT CATALOG SCRAPER")
    print("="*80)
    print(f"Target URL:      {args.url}")
    print(f"Strictness:      {args.strictness.upper()}")
    print(f"Max Pages:       {args.max_pages}")
    print(f"Max Depth:       {args.max_depth}")
    print(f"Crawl Delay:     {args.delay}s")
    print(f"Export Formats:  {', '.join(export_formats)}")
    print(f"Output File:     {args.output}")
    print("="*80 + "\n")
    
    # Create configuration
    config = ScraperConfig(
        base_url=args.url,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        crawl_delay=args.delay,
        output_filename=args.output
    )
    
    # Initialize scraper
    scraper = BalancedScraper(config, strictness=args.strictness)
    
    # Scrape all products (NOT async)
    catalog = scraper.scrape_all_products()
    
    if not catalog:
        print("\n⚠️  No products found.")
        sys.exit(1)
    
    # Save catalog
    scraper.save_catalog(catalog, export_formats=export_formats)
    
    # Print summary
    scraper.print_summary(catalog)
    
    print(f"\n✅ Done! Exported to {len(export_formats)} format(s).\n")


if __name__ == "__main__":
    print("🔧 Product Catalog Scraper\n")
    run_scraper()