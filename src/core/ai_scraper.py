"""Model AI: AI-powered crawler for non-conventional e-commerce sites.

This scraper uses Jina AI for URL discovery and Gemini for semantic filtering.
Ideal for sites where products are:
- Custom projects
- Case studies
- Service offerings
- Non-standard product pages

Workflow:
    1. Jina discovers URLs from base page
    2. Gemini classifies each page based on user intent
    3. Extract product/offering data from accepted pages
    4. Export results

Usage:
    scraper = AIScraper(
        config,
        user_intent="Extract custom RV projects with pricing"
    )
    catalog = await scraper.scrape_all_products()
"""

import os
import time
import json
from typing import Dict, List, Optional

import google.generativeai as genai

from ..core.config import ScraperConfig
from ..crawlers.ai_crawler import AICrawler
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.quotation_template import QuotationTemplate


class AIScraper:
    """AI-powered scraper for non-conventional e-commerce sites.
    
    Uses Jina + Gemini to discover and classify pages based on user intent.
    Extracts product/offering data from accepted pages.
    
    Attributes:
        config: ScraperConfig with crawl settings
        user_intent: Natural language description of what to extract
        ai_crawler: AICrawler instance
        product_extractor: ProductExtractor for data extraction
    
    Example:
        >>> config = ScraperConfig(base_url="https://example.com")
        >>> scraper = AIScraper(
        ...     config,
        ...     user_intent="Extract luxury home projects with pricing"
        ... )
        >>> catalog = await scraper.scrape_all_products()
    """
    
    def __init__(
        self,
        config: ScraperConfig,
        user_intent: str,
        gemini_api_key: Optional[str] = None
    ):
        """
        Initialize AI scraper.
        
        Args:
            config: Scraper configuration
            user_intent: Natural language intent (e.g., "Extract custom projects with pricing")
            gemini_api_key: Optional Gemini API key (uses env if not provided)
        """
        self.config = config
        self.user_intent = user_intent
        
        # Get API keys (Jina API key is optional - r.jina.ai is free to use)
        self.jina_api_key = os.getenv('JINA_API_KEY')  # Optional
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        
        # Initialize AI crawler
        self.ai_crawler = AICrawler(
            jina_api_key=self.jina_api_key,
            gemini_api_key=self.gemini_api_key
        )
        
        # Initialize Gemini for extraction
        genai.configure(api_key=self.gemini_api_key)
        self.gemini_model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Initialize storage
        self.json_storage = JSONStorage()
        self.csv_storage = CSVStorage()
        self.quotation_template = QuotationTemplate()
        self.google_sheets = None
        
        # Statistics
        self.stats = {
            'urls_discovered': 0,
            'pages_accepted': 0,
            'pages_rejected': 0,
            'products_extracted': 0,
            'offerings_extracted': 0,
            'extraction_failures': 0
        }
        
        print(f"\033[32m[✓]\033[0m AI Scraper initialized")
        print(f"  Mode: AI-Powered Crawler (Jina + Gemini)")
        print(f"  Intent: {user_intent}")
        print(f"  Max URLs: {config.max_pages}")
    
    async def scrape_all_products(self, product_urls: set[str] = None) -> Dict:
        """
        Main method: Extract data from product URLs.
        
        Args:
            product_urls: Optional pre-discovered product URLs (from any crawler)
                         If None, uses AI crawler to discover URLs
        
        Returns:
            Complete product/offering catalog
        """
        print(f"\n{'='*80}")
        print("AI SCRAPER (AI-POWERED EXTRACTION)")
        print(f"{'='*80}")
        print(f"Target: {self.config.base_url}")
        print(f"Intent: {self.user_intent}")
        print(f"{'='*80}\n")
        
        # Step 1: Get product URLs (either provided or discover with AI)
        if product_urls is None:
            print("Phase 1: AI-Powered Discovery & Classification")
            print("-" * 80)
            
            product_urls = self.ai_crawler.crawl(
                base_url=self.config.base_url,
                user_intent=self.user_intent,
                max_urls=self.config.max_pages
            )
            
            self.stats['pages_accepted'] = len(product_urls)
        else:
            print(f"Using {len(product_urls)} pre-discovered product URLs")
            self.stats['pages_accepted'] = len(product_urls)
        
        # Fallback: If no URLs found, try scraping the base URL itself
        if not product_urls:
            print("\n⚠️  No product pages found through discovery")
            print("    Attempting to scrape base URL as fallback...")
            product_urls = {self.config.base_url}
            self.stats['pages_accepted'] = 1
        
        # Step 2: Extract data from product pages
        print(f"\n{'='*80}")
        print("Phase 2: Data Extraction")
        print(f"{'='*80}")
        
        catalog = {}
        
        for i, url in enumerate(product_urls, 1):
            print(f"\n[{i}/{len(product_urls)}] Extracting: {url}")
            
            try:
                # Extract product/offering data (may return multiple items from one page)
                products_list = await self._extract_page_data(url)
                
                if products_list:
                    # Store all products from this URL
                    for idx, product_data in enumerate(products_list):
                        # Create unique key for each product (URL + index if multiple)
                        if len(products_list) > 1:
                            catalog_key = f"{url}#item-{idx+1}"
                        else:
                            catalog_key = url
                        
                        catalog[catalog_key] = product_data
                        
                        if product_data.get('page_type') == "PRODUCT":
                            self.stats['products_extracted'] += 1
                        elif product_data.get('page_type') == "OFFERING":
                            self.stats['offerings_extracted'] += 1
                    
                    print(f"  ✓ Added {len(products_list)} item(s) to catalog")
                else:
                    print(f"  ✗ Extraction failed")
                    self.stats['extraction_failures'] += 1
            
            except Exception as e:
                print(f"  ✗ Error: {e}")
                self.stats['extraction_failures'] += 1
            
            # Respect crawl delay
            if i < len(product_urls):
                time.sleep(self.config.crawl_delay)
        
        print(f"\n{'='*80}")
        print("EXTRACTION COMPLETE")
        print(f"{'='*80}")
        self.print_statistics()
        
        return catalog
    
    async def _extract_page_data(self, url: str) -> Optional[List[Dict]]:
        """
        Extract product/offering data from a URL using Gemini.
        
        Args:
            url: Product page URL
            
        Returns:
            List of product data dictionaries or None
        """
        from ..utils.http_client import JinaClient
        
        # Fetch page content with Jina
        jina_client = JinaClient(api_key=self.jina_api_key)
        try:
            page = jina_client.fetch(url)
            markdown = page.text
        except Exception as e:
            print(f"  ✗ Failed to fetch page: {e}")
            return None
        
        print(f"\033[94m  Fetched content (length: {len(markdown) if markdown else 'N/A'})\033[0m")
        if not markdown:
            return None
        
        # Extract all data with Gemini in one call
        prompt = f"""
You are extracting structured product data from a webpage.

USER INTENT:
{self.user_intent}

URL:
{url}

PAGE TITLE:
{page.title}

PAGE CONTENT:
{markdown[:8000]}

TASK:
Extract ALL products/services/projects/offerings from this page.

CRITICAL DISTINCTION:
- If the page shows DIFFERENT PRODUCTS/MODELS (e.g., "Model A", "Model B", "Model C")
  → Extract each as a SEPARATE item in the array
  → Example: Different RV models, different floor plans, different product lines
  
- If the page shows ONE PRODUCT with CUSTOMIZATION OPTIONS (e.g., colors, sizes)
  → Extract as ONE item with customizations in the "customizations" field
  → Example: A product with color options, size variants, add-on features

CLUES FOR SEPARATE PRODUCTS:
- Items have unique model names/numbers (e.g., "2026 King Aire", "2026 Essex")
- Category text like "Select a model", "Choose your product", "Available models"
- Each item is fundamentally different with its own features/specs
- Selecting one means choosing a completely different product

CLUES FOR CUSTOMIZATIONS (single product):
- Options are variations of attributes (colors, sizes, finishes)
- Category text like "Exterior colors", "Interior options", "Add-ons"
- Options modify/enhance the same base product
- Multiple can be selected together

OUTPUT STRICT JSON (ARRAY):

[
  {{
    "product_name": "Name of product or offering",
    "page_type": "PRODUCT or OFFERING",
    "base_price": "Price string or null",
    "price_note": "Custom quote, Starting from, etc.",
    "specifications": {{
      "spec_name": "value"
    }},
    "customizations": {{
      "category": ["option1", "option2"]
    }},
    "description": "Brief product description",
    "features": ["feature1", "feature2"]
  }}
]

RULES:
- If multiple distinct products exist, create SEPARATE array items for each
- If ONE product with options exists, create ONE array item with customizations
- specifications: technical specs, dimensions, materials for THIS specific product
- customizations: options that apply to THIS specific product only
- If no price shown, set base_price to null and price_note to "Custom quote"
- page_type should be PRODUCT for sellable items, OFFERING for projects/services
- Return ONLY JSON array, no explanations
- Even if only one item, return it in an array
"""

        try:
            response = self.gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )
            
            extracted_data = json.loads(response.text)
            
            # Ensure we have a list
            if isinstance(extracted_data, dict):
                # If it's a single dict, wrap it in a list
                extracted_data = [extracted_data]
            elif not isinstance(extracted_data, list):
                print(f"  ✗ Gemini returned invalid format: {type(extracted_data)}")
                return None
            
            if not extracted_data:
                print(f"  ✗ Gemini returned empty list")
                return None
            
            # Build final product data for each extracted item
            products_list = []
            for item in extracted_data:
                if not isinstance(item, dict):
                    continue
                    
                product_data = {
                    "product_name": item.get("product_name", url.split("/")[-1]),
                    "url": url,
                    "page_type": item.get("page_type", "PRODUCT"),
                    "base_price": item.get("base_price"),
                    "price_note": item.get("price_note", ""),
                    "specifications": item.get("specifications", {}),
                    "customizations": item.get("customizations", {}),
                    "description": item.get("description", ""),
                    "features": item.get("features", []),
                    "total_customization_options": sum(
                        len(opts) for opts in item.get("customizations", {}).values()
                    ),
                    
                    # AI metadata
                    "extraction_method": "ai_scraper_gemini",
                    "user_intent": self.user_intent
                }
                products_list.append(product_data)
            
            if products_list:
                print(f"\033[92m  ✓ Extracted {len(products_list)} item(s) from page\033[0m")
                return products_list
            else:
                print(f"  ✗ No valid items extracted")
                return None
            
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parsing failed: {e}")
            print(f"  Response text: {response.text[:200]}...")
            return None
        except Exception as e:
            print(f"  ✗ Gemini extraction failed: {e}")
            return None
    
    def save_catalog(
        self,
        catalog: Dict,
        export_formats: List[str] = None
    ):
        """
        Save catalog in multiple formats.
        
        Args:
            catalog: Product/offering catalog
            export_formats: List of formats ('json', 'csv', 'xlsx', 'sheets')
        """
        if export_formats is None:
            export_formats = ['json']
        
        print(f"\nSaving catalog...")
        
        # JSON
        if 'json' in export_formats:
            output_path = os.path.join(self.config.output_dir, self.config.output_filename)
            self.json_storage.save(catalog, output_path)
            print(f"  ✓ JSON: {output_path}")
        
        # CSV
        if 'csv' in export_formats:
            csv_path = self.config.full_output_path.replace('.json', '.csv')
            self.csv_storage.save(catalog, csv_path)
            print(f"  ✓ CSV: {csv_path}")
        
        # XLSX
        if 'xlsx' in export_formats:
            xlsx_path = self.config.full_output_path.replace('.json', '_quotation.xlsx')
            self.quotation_template.generate_quotation(catalog, xlsx_path)
            print(f"  ✓ XLSX: {xlsx_path}")
        
        # Google Sheets
        if 'sheets' in export_formats and self.google_sheets:
            try:
                self.google_sheets.upload_catalog(catalog)
                print(f"  ✓ Google Sheets uploaded")
            except Exception as e:
                print(f"  ✗ Google Sheets failed: {e}")
    
    def print_statistics(self):
        """Print extraction statistics."""
        print(f"\n📊 AI Scraper Statistics:")
        print(f"   URLs discovered: {self.stats['urls_discovered']}")
        print(f"   Pages accepted: {self.stats['pages_accepted']}")
        print(f"   Pages rejected: {self.stats['pages_rejected']}")
        print(f"   Products extracted: {self.stats['products_extracted']}")
        print(f"   Offerings extracted: {self.stats['offerings_extracted']}")
        print(f"   Extraction failures: {self.stats['extraction_failures']}")
        
        if self.stats['pages_accepted'] > 0:
            success_rate = ((self.stats['products_extracted'] + self.stats['offerings_extracted']) / self.stats['pages_accepted']) * 100
            print(f"   Success rate: {success_rate:.1f}%")
    
    def print_summary(self, catalog: Dict):
        """Print catalog summary."""
        print(f"\n📋 Catalog Summary:")
        print(f"   Total items: {len(catalog)}")
        
        products = sum(1 for p in catalog.values() if p.get('page_type') == 'PRODUCT')
        offerings = sum(1 for p in catalog.values() if p.get('page_type') == 'OFFERING')
        
        print(f"   Products: {products}")
        print(f"   Offerings: {offerings}")
        
        total_specs = sum(len(p.get('specifications', {})) for p in catalog.values())
        total_customizations = sum(p.get('total_customization_options', 0) for p in catalog.values())
        
        print(f"   Total specifications: {total_specs}")
        print(f"   Total customization options: {total_customizations}")