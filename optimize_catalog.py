"""Standalone utility to optimize existing catalog JSON files.

This script uses the CatalogOptimizer to clean up and filter existing
scraper results by removing duplicates and invalid entries.

Usage:
    python optimize_catalog.py results/catalog.json
    python optimize_catalog.py results/catalog.json --formats json sheets
    python optimize_catalog.py results/catalog.json --intent "Extract luxury RV models"
"""

import sys
import os
import asyncio
import argparse

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.catalog_optimizer import CatalogOptimizer


async def main():
    """Main entry point for catalog optimization."""
    parser = argparse.ArgumentParser(
        description='Optimize existing scraper results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python optimize_catalog.py results/catalog.json
  python optimize_catalog.py results/catalog.json --formats json sheets csv
  python optimize_catalog.py results/catalog.json --intent "Extract luxury RV models"
        """
    )
    
    parser.add_argument(
        'input',
        help='Input JSON catalog file to optimize'
    )
    parser.add_argument(
        '--formats',
        nargs='+',
        default=['json', 'sheets'],
        choices=['json', 'csv', 'sheets'],
        help='Export formats for optimized results (default: json sheets)'
    )
    parser.add_argument(
        '--intent',
        help='Original user intent for better context (optional but recommended)'
    )
    parser.add_argument(
        '--output',
        help='Output filename (default: <input>_optimized.json)'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    if not os.path.exists(args.input):
        print(f"❌ Error: Input file not found: {args.input}")
        sys.exit(1)
    
    if not args.input.endswith('.json'):
        print(f"❌ Error: Input must be a JSON file")
        sys.exit(1)
    
    # Initialize optimizer
    print("\n" + "="*80)
    print("CATALOG OPTIMIZER")
    print("="*80)
    print(f"Input: {args.input}")
    print(f"Formats: {', '.join(args.formats)}")
    if args.intent:
        print(f"Intent: {args.intent}")
    print("="*80 + "\n")
    
    try:
        optimizer = CatalogOptimizer(user_intent=args.intent)
    except Exception as e:
        print(f"❌ Failed to initialize optimizer: {e}")
        print("\nMake sure GEMINI_API_KEY is set in your environment:")
        print("  export GEMINI_API_KEY=your_key_here")
        sys.exit(1)
    
    # Load and optimize
    try:
        optimized = optimizer.load_and_optimize(
            args.input,
            export_formats=args.formats
        )
        
        print("\n" + "="*80)
        print("✅ OPTIMIZATION COMPLETE")
        print("="*80)
        print(f"Original items: {optimizer.stats['input_items']}")
        print(f"Optimized items: {optimizer.stats['output_items']}")
        print(f"Items removed: {optimizer.stats['input_items'] - optimizer.stats['output_items']}")
        print(f"  - Invalid entries: {optimizer.stats['invalid_items_removed']}")
        print(f"  - Duplicates: {optimizer.stats['duplicates_removed']}")
        print("="*80 + "\n")
        
    except FileNotFoundError:
        print(f"❌ Error: Could not find file: {args.input}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Optimization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
