"""Main entry point for the scraper."""

import argparse
from src.core.config import ScraperConfig
from src.core.scraper import TheraluxeScraper


def main():
    """Main function to run the scraper."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Scrape Theraluxe product catalog',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                           # Basic scrape (JSON only)
  python run.py --export csv              # Export to CSV
  python run.py --export csv,csv_prices   # Multiple formats
  python run.py --export all              # All formats
  python run.py --export google_sheets    # Upload to Google Sheets
  python run.py --ai                      # Use AI classification
        """
    )
    
    parser.add_argument(
        '--ai',
        action='store_true',
        help='Use AI (Gemini) for page classification'
    )
    
    parser.add_argument(
        '--max-pages',
        type=int,
        default=20,
        help='Maximum pages to crawl (default: 50)'
    )
    
    parser.add_argument(
        '--max-depth',
        type=int,
        default=3,
        help='Maximum crawl depth (default: 3)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default='product_catalog.json',
        help='Output filename (default: product_catalog.json)'
    )
    
    parser.add_argument(
        '--delay',
        type=float,
        default=0.5,
        help='Delay between requests in seconds (default: 0.5)'
    )
    
    parser.add_argument(
        '--export',
        type=str,
        default='json',
        help='Export formats: json, csv, csv_prices, quotation, google_sheets, all (comma-separated)'
    )
    
    args = parser.parse_args()
    
    # Parse export formats
    if args.export.lower() == 'all':
        export_formats = ['json', 'csv', 'csv_prices', 'quotation', 'google_sheets']
    else:
        export_formats = [fmt.strip() for fmt in args.export.split(',')]
    
    # Create configuration
    config = ScraperConfig(
        use_ai_classification=args.ai,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        output_filename=args.output,
        crawl_delay=args.delay
    )
    
    # Validate configuration
    if not config.validate():
        print("⚠ Warning: Configuration validation failed, continuing anyway...")
    
    # Initialize scraper
    scraper = TheraluxeScraper(config)
    
    # Scrape all products
    catalog = scraper.scrape_all_products()
    
    if not catalog:
        print("\n❌ No products found. Exiting.")
        return
    
    # Save to specified formats
    print(f"\n{'='*80}")
    print("EXPORTING CATALOG")
    print(f"{'='*80}\n")
    
    scraper.save_catalog(catalog, export_formats=export_formats)
    
    # Print summary
    scraper.print_summary(catalog)
    
    print(f"\n✅ Done! Exported to {len(export_formats)} format(s).\n")
    
    # Show file locations
    print("📁 Output files:")
    if 'json' in export_formats:
        print(f"   • JSON: {config.full_output_path}")
    if 'csv' in export_formats:
        print(f"   • CSV: {config.full_output_path.replace('.json', '.csv')}")
    if 'csv_prices' in export_formats:
        print(f"   • CSV (with prices): {config.full_output_path.replace('.json', '_with_prices.csv')}")
    if 'quotation' in export_formats:
        print(f"   • Quotation Template: {config.full_output_path.replace('.json', '_quotation_template.json')}")
    if 'google_sheets' in export_formats:
        print(f"   • Google Sheets: Check console output for URL")
    print()


if __name__ == "__main__":
    main()