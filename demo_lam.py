"""
Quick demonstration of Model LAM usage.

This script shows how to use Model LAM for intelligent configurator extraction.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.lam_scraper import LAMScraper
from src.core.config import ScraperConfig


def demo_lam_scraper():
    """Demonstrate Model LAM usage."""
    
    print("="*80)
    print("MODEL LAM DEMONSTRATION")
    print("="*80)
    print()
    
    # Check for Gemini API key
    gemini_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
    
    if not gemini_key:
        print("⚠️  GEMINI_API_KEY not found in environment")
        print("   LAM will fall back to Model S (static extraction)")
        print()
        print("   To enable Gemini:")
        print("   export GEMINI_API_KEY=your_api_key_here")
        print()
    else:
        print("✓ Gemini API key found")
        print()
    
    # Example 1: Simple product (will use static)
    print("-"*80)
    print("Example 1: Simple Product (Static Extraction Expected)")
    print("-"*80)
    
    config = ScraperConfig(
        base_url="https://example.com",
        max_pages=5
    )
    
    scraper = LAMScraper(
        config,
        strictness="balanced",
        enable_gemini=True
    )
    
    print(f"Scraper initialized:")
    print(f"  - Gemini enabled: {scraper.enable_gemini}")
    print(f"  - Gemini available: {scraper.gemini_consultant.enabled}")
    print()
    
    # Example 2: Complex configurator (would use Gemini if available)
    print("-"*80)
    print("Example 2: Complex Configurator (Interactive Expected)")
    print("-"*80)
    print()
    print("For a real configurator URL, LAM would:")
    print("  1. Detect configurator (ConfiguratorDetector)")
    print("  2. Calculate confidence score")
    print("  3. If confidence ≥ 60%, consult Gemini")
    print("  4. Gemini decides: Interactive or Static")
    print("  5. Extract using chosen method")
    print("  6. Fall back to static if anything fails")
    print()
    
    # Show LAM statistics structure
    print("-"*80)
    print("LAM Statistics Tracked")
    print("-"*80)
    print()
    print("During extraction, LAM tracks:")
    for key, value in scraper.lam_stats.items():
        print(f"  - {key}: {value}")
    print()
    
    # Usage tips
    print("-"*80)
    print("Usage Tips")
    print("-"*80)
    print()
    print("1. Use Model LAM for:")
    print("   • Complex product configurators")
    print("   • Interactive option selection")
    print("   • Multi-step configuration wizards")
    print()
    print("2. Use Model S for:")
    print("   • Simple product pages")
    print("   • Standard e-commerce")
    print("   • Fast batch scraping")
    print()
    print("3. LAM automatically falls back to Model S when:")
    print("   • Gemini API not available")
    print("   • Configurator confidence too low")
    print("   • Gemini recommends static extraction")
    print("   • Any error occurs")
    print()
    
    # CLI examples
    print("-"*80)
    print("CLI Examples")
    print("-"*80)
    print()
    print("# Basic LAM usage")
    print("python run.py --url https://example.com/configure --model LAM")
    print()
    print("# With all options")
    print("python run.py \\")
    print("  --url https://example.com/configure \\")
    print("  --model LAM \\")
    print("  --max-pages 20 \\")
    print("  --strictness balanced \\")
    print("  --export json,csv,quotation")
    print()
    print("# Will fall back to Model S if LAM unavailable")
    print("python run.py --url https://example.com --model LAM")
    print()
    
    print("="*80)
    print("DEMONSTRATION COMPLETE")
    print("="*80)
    print()
    print("To test with a real website:")
    print("  python run.py --url <your-url> --model LAM --max-pages 5")
    print()


if __name__ == "__main__":
    demo_lam_scraper()
