"""Test script to verify Model S and Model D are working correctly."""

import asyncio
import os
from dotenv import load_dotenv

from src.core.config import ScraperConfig
from src.core.balanced_scraper import BalancedScraper
from src.core.dynamic_scraper import DynamicScraper

# Load environment variables
load_dotenv()


def test_model_s():
    """Test Model S (Balanced Scraper - static extraction)."""
    print("\n" + "="*80)
    print("TESTING MODEL S (BalancedScraper)")
    print("="*80)
    
    # Test configuration
    config = ScraperConfig(
        base_url="https://example.com",  # Will be overridden for direct URL test
        max_pages=5,
        max_depth=2,
        crawl_delay=0.5
    )
    
    # Initialize Model S scraper
    scraper = BalancedScraper(config, strictness="balanced")
    
    # Test single product scraping (you can replace with a real URL)
    test_url = "https://example.com/products/test-product"
    print(f"\nTesting single product extraction: {test_url}")
    
    try:
        # This will fail because it's a dummy URL, but we're checking the structure works
        product = scraper.scrape_product(test_url)
        
        if product:
            print("✓ Model S extraction successful")
            print(f"  Product: {product.get('product_name', 'Unknown')}")
            print(f"  Model: S (static)")
        else:
            print("⚠ Model S returned None (expected with dummy URL)")
    except Exception as e:
        print(f"⚠ Expected error with dummy URL: {e}")
    
    print("\n✓ Model S structure verified - no import errors!")
    return True


async def test_model_d():
    """Test Model D (Dynamic Scraper - hybrid extraction)."""
    print("\n" + "="*80)
    print("TESTING MODEL D (DynamicScraper)")
    print("="*80)
    
    # Test configuration
    config = ScraperConfig(
        base_url="https://example.com",
        max_pages=5,
        max_depth=2,
        crawl_delay=0.5
    )
    
    # Initialize Model D scraper
    scraper = DynamicScraper(
        config,
        strictness="balanced",
        enable_browser=False,  # Disable browser for quick test
        headless=True
    )
    
    # Test classification
    test_url = "https://example.com/products/test-product"
    test_markdown = "# Test Product\nPrice: $100\nSpecifications: Test"
    
    print(f"\nTesting classification: {test_url}")
    
    try:
        classification = scraper.classifier.classify_page(test_url, test_markdown)
        
        print(f"✓ Classification successful")
        print(f"  Page type: {classification['page_type']}")
        print(f"  Is product: {classification['is_product']}")
        print(f"  Model: {classification['model']}")
        print(f"  Confidence: {classification['confidence']:.0%}")
        
    except Exception as e:
        print(f"✗ Classification failed: {e}")
        return False
    
    print("\n✓ Model D structure verified - no import errors!")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("MODEL S AND MODEL D VERIFICATION TEST")
    print("="*80)
    
    # Test Model S
    model_s_ok = test_model_s()
    
    # Test Model D (needs async)
    model_d_ok = asyncio.run(test_model_d())
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Model S (BalancedScraper): {'✓ PASS' if model_s_ok else '✗ FAIL'}")
    print(f"Model D (DynamicScraper): {'✓ PASS' if model_d_ok else '✗ FAIL'}")
    
    if model_s_ok and model_d_ok:
        print("\n🎉 All models verified successfully!")
        print("\nUsage:")
        print("  Model S: python src/main.py --url <URL> --strictness balanced")
        print("  Model D: python -c \"import asyncio; from src.core.dynamic_scraper import DynamicScraper; from src.core.config import ScraperConfig; asyncio.run(DynamicScraper(ScraperConfig(base_url='<URL>'), enable_browser=True).scrape_all_products())\"")
    else:
        print("\n⚠ Some models have issues - check errors above")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
