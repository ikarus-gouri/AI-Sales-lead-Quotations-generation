"""Catalog Optimizer: Post-processing layer for scraper results.

Uses Gemini to optimize and clean extracted catalogs by:
- Removing duplicate products/services/projects
- Filtering out non-product content (questions, FAQs, generic text)
- Validating that items are actual products/services/projects
- Standardizing data structure

Workflow:
    1. Load catalog JSON from scraper
    2. Send to Gemini for analysis and filtering
    3. Remove duplicates and invalid entries
    4. Return optimized catalog
    5. Export to JSON and Google Sheets

Usage:
    optimizer = CatalogOptimizer(gemini_api_key="...")
    optimized = await optimizer.optimize_catalog(catalog)
    optimizer.save_results(optimized, formats=['json', 'sheets'])
"""

import json
import os
from typing import Dict, List, Optional, Set
import google.generativeai as genai
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.google_sheets import GoogleSheetsStorage


class CatalogOptimizer:
    """Post-processing optimizer for scraper results."""
    
    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        user_intent: Optional[str] = None
    ):
        """
        Initialize catalog optimizer.
        
        Args:
            gemini_api_key: Gemini API key
            user_intent: Original user intent for context
        """
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        self.user_intent = user_intent or "Extract product information"
        
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        # Initialize Gemini
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Initialize storage
        self.json_storage = JSONStorage()
        self.csv_storage = CSVStorage()
        self.google_sheets = None
        
        # Statistics
        self.stats = {
            'input_items': 0,
            'duplicates_removed': 0,
            'invalid_items_removed': 0,
            'output_items': 0,
            'optimization_time': 0
        }
        
        print(f"\033[32m[✓]\033[0m Catalog Optimizer initialized")
        print(f"  Mode: AI-Powered Quality Control (Gemini)")
        print(f"  Intent: {self.user_intent}")
    
    async def optimize_catalog(self, catalog: Dict) -> Dict:
        """
        Optimize catalog by removing duplicates and invalid entries.
        
        Args:
            catalog: Raw catalog from scraper
            
        Returns:
            Optimized catalog with cleaned data
        """
        print(f"\n{'='*80}")
        print("CATALOG OPTIMIZATION")
        print(f"{'='*80}")
        
        import time
        start_time = time.time()
        
        # Extract products list
        if isinstance(catalog, dict) and 'products' in catalog:
            products = catalog['products']
            metadata = {k: v for k, v in catalog.items() if k != 'products'}
        else:
            # Old format: dict of product_name: data
            products = list(catalog.values()) if isinstance(catalog, dict) else []
            metadata = {}
        
        self.stats['input_items'] = len(products)
        print(f"Input items: {len(products)}")
        
        if not products:
            print("⚠️  No items to optimize")
            return catalog
        
        # Step 1: Analyze with Gemini in batches
        print("\nPhase 1: Analyzing items with Gemini...")
        optimized_products = await self._analyze_and_filter(products)
        
        # Step 2: Remove duplicates
        print("\nPhase 2: Removing duplicates...")
        deduplicated = self._remove_duplicates(optimized_products)
        
        self.stats['output_items'] = len(deduplicated)
        self.stats['duplicates_removed'] = len(optimized_products) - len(deduplicated)
        self.stats['invalid_items_removed'] = len(products) - len(optimized_products)
        self.stats['optimization_time'] = time.time() - start_time
        
        # Build optimized catalog
        optimized_catalog = {
            **metadata,
            'products': deduplicated,
            'total_products': len(deduplicated),
            'optimization_stats': self.stats,
            'optimized': True
        }
        
        self._print_optimization_summary()
        
        return optimized_catalog
    
    async def _analyze_and_filter(
        self,
        products: List[Dict],
        batch_size: int = 10
    ) -> List[Dict]:
        """
        Analyze products with Gemini and filter invalid entries.
        
        Args:
            products: List of product dictionaries
            batch_size: Number of products per batch
            
        Returns:
            Filtered list of valid products
        """
        valid_products = []
        
        # Process in batches
        for i in range(0, len(products), batch_size):
            batch = products[i:i+batch_size]
            print(f"  Analyzing batch {i//batch_size + 1}/{(len(products)-1)//batch_size + 1}...")
            
            try:
                filtered_batch = await self._filter_batch(batch)
                valid_products.extend(filtered_batch)
            except Exception as e:
                print(f"  ⚠️  Batch failed: {e}")
                # On error, keep original batch (fail-safe)
                valid_products.extend(batch)
        
        return valid_products
    
    async def _filter_batch(self, products: List[Dict]) -> List[Dict]:
        """Filter a batch of products using Gemini."""
        
        # Prepare product summaries for Gemini
        product_summaries = []
        for idx, p in enumerate(products):
            summary = {
                'index': idx,
                'product_name': p.get('product_name', 'Unknown'),
                'url': p.get('url', ''),
                'base_price': p.get('base_price', 'N/A'),
                'description': p.get('description', '')[:200],  # First 200 chars
                'page_type': p.get('page_type', 'PRODUCT'),
                'specifications': list(p.get('specifications', {}).keys())[:5],  # First 5 specs
                'features': p.get('features', [])[:5]  # First 5 features
            }
            product_summaries.append(summary)
        
        prompt = f"""
You are validating extracted product/service/project data.

ORIGINAL USER INTENT:
{self.user_intent}

EXTRACTED ITEMS:
{json.dumps(product_summaries, indent=2)}

TASK: For each item, determine if it is VALID or INVALID.

VALID ITEMS:
- Actual products for sale
- Services offered
- Project examples
- Portfolio items
- Offerings that match user intent
- Items with substantive information

INVALID ITEMS (REMOVE THESE):
- FAQ questions or answers
- Generic text snippets
- Navigation elements
- "Contact us" pages
- Generic questions like "What is X?"
- Generic informational content
- Duplicate or near-duplicate entries
- Items that are clearly NOT products/services/projects
- Irrelevant content that doesn't match user intent

DECISION RULES:
1. If item looks like a question or FAQ → INVALID
2. If item has no product name or generic name → INVALID
3. If item matches user intent with real product/service data → VALID
4. If item is duplicate of another item → mark which one to keep
5. When in doubt, check if it provides value to the user based on intent

Return JSON array with validation results:
[
  {{
    "index": 0,
    "status": "VALID" | "INVALID",
    "reason": "brief explanation",
    "keep": true | false
  }}
]

CRITICAL: Return valid JSON only, no explanations outside the JSON.
"""
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )
            
            validations = json.loads(response.text)
            
            # Filter products based on validations
            valid_products = []
            for validation in validations:
                idx = validation['index']
                if validation.get('keep', True) and validation.get('status') == 'VALID':
                    valid_products.append(products[idx])
                else:
                    print(f"  ✗ Filtered out: {products[idx].get('product_name', 'Unknown')} - {validation.get('reason', 'Invalid')}")
            
            return valid_products
            
        except json.JSONDecodeError as e:
            print(f"  ⚠️  JSON parse error: {e}")
            return products  # Return original on error
        except Exception as e:
            print(f"  ⚠️  Validation error: {e}")
            return products  # Return original on error
    
    def _remove_duplicates(self, products: List[Dict]) -> List[Dict]:
        """
        Remove duplicate products based on name and URL similarity.
        
        Args:
            products: List of products
            
        Returns:
            Deduplicated list
        """
        seen_signatures = set()
        deduplicated = []
        
        for product in products:
            # Create signature from product name and URL
            name = product.get('product_name', '').lower().strip()
            url = product.get('url', '').lower().strip()
            
            # Normalize signature
            signature = f"{name}|{url}"
            
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                deduplicated.append(product)
            else:
                print(f"  ✗ Duplicate removed: {product.get('product_name', 'Unknown')}")
        
        return deduplicated
    
    def save_results(
        self,
        catalog: Dict,
        export_formats: List[str] = None,
        output_filename: str = "optimized_catalog"
    ):
        """
        Save optimized catalog in multiple formats.
        
        Args:
            catalog: Optimized catalog
            export_formats: List of formats ('json', 'csv', 'sheets')
            output_filename: Base filename (without extension)
        """
        if export_formats is None:
            export_formats = ['json', 'sheets']
        
        print(f"\n{'='*80}")
        print("SAVING OPTIMIZED RESULTS")
        print(f"{'='*80}")
        
        # JSON
        if 'json' in export_formats:
            json_path = f"results/{output_filename}.json"
            self.json_storage.save(catalog, json_path)
            print(f"✓ JSON saved: {json_path}")
        
        # CSV
        if 'csv' in export_formats:
            csv_path = f"results/{output_filename}.csv"
            self.csv_storage.save(catalog, csv_path)
            print(f"✓ CSV saved: {csv_path}")
        
        # Google Sheets
        if 'sheets' in export_formats:
            try:
                if self.google_sheets is None:
                    self.google_sheets = GoogleSheetsStorage()
                
                sheet_url = self.google_sheets.save(catalog, f"{output_filename}")
                print(f"✓ Google Sheets saved: {sheet_url}")
            except Exception as e:
                print(f"⚠️  Google Sheets export failed: {e}")
    
    def _print_optimization_summary(self):
        """Print optimization statistics."""
        print(f"\n{'='*80}")
        print("OPTIMIZATION COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Statistics:")
        print(f"   Input items: {self.stats['input_items']}")
        print(f"   Invalid items removed: {self.stats['invalid_items_removed']}")
        print(f"   Duplicates removed: {self.stats['duplicates_removed']}")
        print(f"   Output items: {self.stats['output_items']}")
        print(f"   Optimization time: {self.stats['optimization_time']:.2f}s")
        
        if self.stats['input_items'] > 0:
            retention_rate = (self.stats['output_items'] / self.stats['input_items']) * 100
            print(f"   Retention rate: {retention_rate:.1f}%")
        
        print(f"{'='*80}\n")
    
    def load_and_optimize(
        self,
        json_path: str,
        export_formats: List[str] = None
    ) -> Dict:
        """
        Load catalog from JSON file, optimize, and save.
        
        Args:
            json_path: Path to input JSON catalog
            export_formats: Export formats for optimized results
            
        Returns:
            Optimized catalog
        """
        print(f"\n{'='*80}")
        print(f"LOADING CATALOG FROM FILE")
        print(f"{'='*80}")
        print(f"Source: {json_path}")
        
        # Load catalog
        with open(json_path, 'r', encoding='utf-8') as f:
            catalog = json.load(f)
        
        # Optimize
        import asyncio
        optimized = asyncio.run(self.optimize_catalog(catalog))
        
        # Save
        base_name = os.path.splitext(os.path.basename(json_path))[0]
        output_name = f"{base_name}_optimized"
        self.save_results(optimized, export_formats, output_name)
        
        return optimized


# Standalone CLI for optimizing existing catalogs
async def main():
    """CLI entry point for catalog optimization."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimize scraper results")
    parser.add_argument('input', help='Input JSON catalog file')
    parser.add_argument('--formats', nargs='+', default=['json', 'sheets'],
                       help='Export formats (json, csv, sheets)')
    parser.add_argument('--intent', help='Original user intent for context')
    
    args = parser.parse_args()
    
    # Initialize optimizer
    optimizer = CatalogOptimizer(user_intent=args.intent)
    
    # Load and optimize
    optimized = optimizer.load_and_optimize(
        args.input,
        export_formats=args.formats
    )
    
    print("\n✓ Optimization complete!")
    return optimized


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
