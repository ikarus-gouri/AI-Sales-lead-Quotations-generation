# """Main entry point for the scraper."""

# import argparse
# import sys
# from src.core.config import ScraperConfig
# from src.core.scraper import TheraluxeScraper


# def main():
#     """Main function to run the scraper."""
#     # Parse command line arguments
#     parser = argparse.ArgumentParser(
#         description='Dynamic Product Catalog Scraper - Scrape any e-commerce website',
#         formatter_class=argparse.RawDescriptionHelpFormatter,
#         epilog="""
# Examples:
#   # Basic usage with URL
#   python run.py --url https://example.com/products
  
#   # With export formats
#   python run.py --url https://example.com/products --export csv
#   python run.py --url https://example.com/products --export all
  
#   # With AI classification
#   python run.py --url https://example.com/products --ai
  
#   # Adjust crawl settings
#   python run.py --url https://example.com/products --max-pages 100 --max-depth 4
  
#   # Custom output filename
#   python run.py --url https://example.com/products --output my_catalog.json
  
# Environment Variables (optional):
#   BASE_URL              - Default URL to scrape (can be overridden by --url)
#   GEMINI_API_KEY        - Gemini API key for AI classification
#   GOOGLE_CREDENTIALS_FILE - Google service account credentials
#   GOOGLE_SPREADSHEET_ID - Target Google Sheets ID
#         """
#     )
    
#     # Required: Target URL
#     parser.add_argument(
#         '--url',
#         type=str,
#         help='Target website URL to scrape (required unless set in .env)'
#     )
    
#     # Export options
#     parser.add_argument(
#         '--export',
#         type=str,
#         default='json',
#         help='Export formats: json, csv, csv_prices, quotation, google_sheets, all (comma-separated)'
#     )
    
#     # Crawling options
#     parser.add_argument(
#         '--max-pages',
#         type=int,
#         default=50,
#         help='Maximum pages to crawl (default: 50)'
#     )
    
#     parser.add_argument(
#         '--max-depth',
#         type=int,
#         default=3,
#         help='Maximum crawl depth (default: 3)'
#     )
    
#     parser.add_argument(
#         '--delay',
#         type=float,
#         default=0.5,
#         help='Delay between requests in seconds (default: 0.5)'
#     )
    
#     # Output options
#     parser.add_argument(
#         '--output',
#         type=str,
#         default='product_catalog.json',
#         help='Output filename (default: product_catalog.json)'
#     )
    
#     # AI options
#     parser.add_argument(
#         '--ai',
#         action='store_true',
#         help='Use AI (Gemini) for page classification'
#     )
    
#     args = parser.parse_args()
    
#     # Parse export formats
#     if args.export.lower() == 'all':
#         export_formats = ['json', 'csv', 'csv_prices', 'quotation', 'google_sheets']
#     else:
#         export_formats = [fmt.strip() for fmt in args.export.split(',')]
    
#     # Create configuration
#     config = ScraperConfig(
#         base_url=args.url,  # Will use .env BASE_URL if not provided
#         use_ai_classification=args.ai,
#         max_pages=args.max_pages,
#         max_depth=args.max_depth,
#         output_filename=args.output,
#         crawl_delay=args.delay
#     )
    
#     # Validate configuration
#     if not config.validate():
#         print("\n Configuration validation failed. Please fix the errors above.\n")
#         sys.exit(1)
    
#     # Show configuration
#     print("\n" + "="*80)
#     print("SCRAPER CONFIGURATION")
#     print("="*80)
#     print(f"Target URL:      {config.base_url}")
#     print(f"Max Pages:       {config.max_pages}")
#     print(f"Max Depth:       {config.max_depth}")
#     print(f"Crawl Delay:     {config.crawl_delay}s")
#     print(f"AI Classification: {'Enabled' if config.use_ai_classification else 'Disabled'}")
#     print(f"Export Formats:  {', '.join(export_formats)}")
#     print(f"Output File:     {config.full_output_path}")
#     print("="*80 + "\n")
    
#     # Confirm before starting
#     try:
#         user_input = input("Press Enter to start scraping (or Ctrl+C to cancel)... ")
#     except KeyboardInterrupt:
#         print("\n\n Scraping cancelled by user.\n")
#         sys.exit(0)
    
#     # Initialize scraper
#     scraper = TheraluxeScraper(config)
    
#     # Scrape all products
#     catalog = scraper.scrape_all_products()
    
#     if not catalog:
#         print("\n  No products found. Possible reasons:")
#         print("   • The URL doesn't contain product pages")
#         print("   • The website structure doesn't match expected patterns")
#         print("   • Try increasing --max-pages or --max-depth")
#         print("   • Try using --ai for better product detection\n")
#         sys.exit(1)
    
#     # Save to specified formats
#     print(f"\n{'='*80}")
#     print("EXPORTING CATALOG")
#     print(f"{'='*80}\n")
    
#     scraper.save_catalog(catalog, export_formats=export_formats)
    
#     # Print summary
#     scraper.print_summary(catalog)
    
#     print(f"\n Done! Exported to {len(export_formats)} format(s).\n")
    
#     # Show file locations
#     print(" Output files:")
#     if 'json' in export_formats:
#         print(f"   • JSON: {config.full_output_path}")
#     if 'csv' in export_formats:
#         print(f"   • CSV: {config.full_output_path.replace('.json', '.csv')}")
#     if 'csv_prices' in export_formats:
#         print(f"   • CSV (with prices): {config.full_output_path.replace('.json', '_with_prices.csv')}")
#     if 'quotation' in export_formats:
#         print(f"   • Quotation Template: {config.full_output_path.replace('.json', '_quotation_template.json')}")
#     if 'google_sheets' in export_formats:
#         print(f"   • Google Sheets: Check console output for URL")
#     print()


# if __name__ == "__main__":
#     main()


"""Main entry point for the balanced scraper."""

import argparse
import sys
import os
from src.core.config import ScraperConfig
from src.core.balanced_scraper import BalancedScraper


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

Examples:
  # Balanced mode (recommended)
  python main.py --url https://example.com/products
  
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
    
    # NEW: Strictness level
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
    print(f"Strictness:      {args.strictness.upper()}")
    print(f"Max Pages:       {config.max_pages}")
    print(f"Max Depth:       {config.max_depth}")
    print(f"Crawl Delay:     {config.crawl_delay}s")
    print(f"Export Formats:  {', '.join(export_formats)}")
    print(f"Output File:     {config.full_output_path}")
    print("="*80 + "\n")
    
    # Explain strictness level
    strictness_info = {
        "lenient": "High recall - catches all products, some false positives",
        "balanced": "Good precision + recall - recommended for most sites",
        "strict": "High precision - very clean results, may miss some products"
    }
    print(f"ℹ️  Strictness: {strictness_info[args.strictness]}\n")
    
    # Confirm before starting
    try:
        user_input = input("Press Enter to start scraping (or Ctrl+C to cancel)... ")
    except KeyboardInterrupt:
        print("\n\n⛔ Scraping cancelled by user.\n")
        sys.exit(0)
    
    # Initialize scraper with strictness level
    scraper = BalancedScraper(config, strictness=args.strictness)
    
    # Scrape all products
    catalog = scraper.scrape_all_products()
    
    if not catalog:
        print("\n⚠️  No products found. Possible solutions:")
        print("   • Try --strictness lenient for higher recall")
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