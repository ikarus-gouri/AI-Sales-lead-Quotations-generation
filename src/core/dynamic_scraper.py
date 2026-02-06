"""Model-D: Simplified static scraper (Browser-based Model D removed).

This scraper now only uses static scraping (Model-S approach) for all pages.
The dynamic/browser-based routing has been removed for simplicity.

Features:
    - Static scraping for all product pages
    - Enhanced page classification
    - Configurator detection (static analysis)
    - Export to multiple formats

Workflow:
    1. Crawl website with DynamicClassifier
    2. For each product page:
        - Use Model-S (static extraction)
    3. Extract product data using static methods
    4. Export to multiple formats

Usage:
    scraper = DynamicScraper(
        config,
        strictness="balanced"
    )
    catalog = scraper.scrape_all_products()
    scraper.save_catalog(catalog, export_formats=['json'])
"""

import asyncio
import time
from typing import Dict, List, Optional
from ..core.config import ScraperConfig
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..extractors.product_extractor import ProductExtractor
from ..extractors.configurator_detector import ConfiguratorDetector
from ..extractors.external_configurator_scraper import ExternalConfiguratorScraper
from ..classifiers.dynamic_classifier import DynamicClassifier
from ..classifiers.balanced_classifier import StrictnessLevel
from ..crawlers.web_crawler import WebCrawler
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.google_sheets import GoogleSheetsStorage
from ..storage.quotation_template import QuotationTemplate


class DynamicScraper:
    """Model-D: Simplified static scraper (Browser-based routing removed).
    
    This scraper now only uses static extraction (Model-S) for all pages.
    The browser-based Model D routing has been removed for simplicity.
    
    Workflow:
        1. Crawl pages using enhanced web crawler
        2. Classify with DynamicClassifier
        3. Extract using static method (ProductExtractor)
        4. Export to unified catalog
    
    Attributes:
        config: ScraperConfig with crawl settings
        classifier: DynamicClassifier for page classification
        crawler: WebCrawler with classification
    
    Example:
        >>> config = ScraperConfig(base_url="https://example.com")
        >>> scraper = DynamicScraper(config, strictness="balanced")
        >>> catalog = scraper.scrape_all_products()
        >>> scraper.save_catalog(catalog, export_formats=['json'])
    """
    
    def __init__(
        self,
        config: ScraperConfig,
        strictness: str = "balanced",
        enable_browser: bool = False,  # Deprecated, kept for compatibility
        headless: bool = True  # Deprecated, kept for compatibility
    ):
        """
        Initialize dynamic scraper.
        
        Args:
            config: Scraper configuration
            strictness: Classification strictness ('lenient', 'balanced', 'strict')
            enable_browser: Deprecated (Model D removed)
            headless: Deprecated (Model D removed)
        """
        self.config = config
        self.strictness = strictness
        self.enable_browser = False  # Always disabled now
        self.headless = headless
        
        # Map strictness string to enum for consistency
        strictness_map = {
            "lenient": StrictnessLevel.LENIENT,
            "balanced": StrictnessLevel.BALANCED,
            "strict": StrictnessLevel.STRICT
        }
        self.strictness_level = strictness_map.get(strictness.lower(), StrictnessLevel.BALANCED)
        
        # Initialize core components (same as BalancedScraper)
        self.http_client = HTTPClient(timeout=config.request_timeout, use_cache=config.use_cache)
        self.link_extractor = LinkExtractor()
        self.product_extractor = ProductExtractor()
        self.configurator_detector = ConfiguratorDetector()
        self.external_scraper = ExternalConfiguratorScraper(
            http_client=self.http_client,
            product_extractor=self.product_extractor
        )
        
        # Initialize DYNAMIC classifier (hybrid routing)
        self.classifier = DynamicClassifier(strictness=strictness)
        
        # Initialize crawler with dynamic classifier
        self.crawler = WebCrawler(
            base_url=config.base_url,
            http_client=self.http_client,
            link_extractor=self.link_extractor,
            classifier=self.classifier,
            crawl_delay=config.crawl_delay
        )
        
        # Initialize storage
        self.json_storage = JSONStorage()
        self.csv_storage = CSVStorage()
        self.quotation_template = QuotationTemplate()
        self.google_sheets = None
        
        # Statistics
        self.stats = {
            'total_pages_crawled': 0,
            'product_pages_found': 0,
            'static_extractions': 0,
            'failed_extractions': 0,
        }
        
        print(f"\033[32m[✓]\033[0m Dynamic Scraper initialized")
        print(f"  Mode: Static Only (Model-S)")
        print(f"  Strictness: {strictness}")
        print(f"  Max pages: {config.max_pages}")
    
    async def scrape_product(self, url: str, markdown: str = None) -> Optional[Dict]:
        """
        Scrape a single product page using static extraction only.
        
        Args:
            url: The product page URL
            markdown: Optional pre-fetched markdown (from crawler cache)
            
        Returns:
            Product data dictionary or None
        """
        print(f"\n{'-'*80}")
        print(f"Scraping product: {url}")
        print(f"{'-'*80}")
        
        # Get page content (use cache if available)
        if markdown is None:
            markdown = self.http_client.scrape_with_jina(url)
            if not markdown:
                return None
        
        # Classify with DynamicClassifier
        classification = self.classifier.classify_page(url, markdown)
        
        if not classification['is_product']:
            print(f"  \033[33m[WARN]\033[0m Page reclassified as {classification['page_type']}")
            return None
        
        # Log classification
        print(f"  \033[34m[INFO]\033[0m Classification:")
        print(f"     Type: {classification['page_type'].upper()}")
        print(f"     Model: S (Static)")
        print(f"     Confidence: {classification['confidence']:.0%}")
        
        # Always use Model-S: Static extraction
        product_data = self._extract_static(url, markdown, classification)
        if product_data:
            self.stats['static_extractions'] += 1
        else:
            self.stats['failed_extractions'] += 1
        
        if product_data:
            # Add classification metadata
            product_data['classification'] = classification
            product_data['model'] = 'S'
        
        return product_data
    
    def _extract_static(self, url: str, markdown: str, classification: Dict) -> Optional[Dict]:
        """
        Extract product data using Model-S (static approach).
        Same logic as BalancedScraper.
        """
        try:
            print(f"  \033[34m[S]\033[0m Using Model-S (static extraction)")
            
            # Detect configurator
            configurator_info = self.configurator_detector.has_configurator(url, markdown)
            
            # Log detection
            print(f"  \033[36m[CONFIG]\033[0m Configurator:")
            print(f"     Detected: {configurator_info['has_configurator']}")
            if configurator_info['has_configurator']:
                print(f"     Type: {configurator_info['configurator_type']}")
                print(f"     Confidence: {configurator_info['confidence']:.0%}")
            
            # Extract basic info
            product_name = self.product_extractor.extract_product_name(url, markdown)
            base_price = self.product_extractor.extract_base_price(markdown)
            specifications = self.product_extractor.extract_specifications(markdown)
            
            # Determine if should scrape customizations
            should_scrape, reason = self.configurator_detector.should_scrape_configurator(configurator_info)
            
            customizations = {}
            scrape_source = "none"
            external_platform = None
            
            if should_scrape:
                print(f"  → Extracting customizations ({reason})...")
                
                # External configurator
                if configurator_info['configurator_type'] == 'external' and configurator_info['configurator_url']:
                    time.sleep(10)
                    external_result = self.external_scraper.scrape_external_configurator(
                        url=configurator_info['configurator_url'],
                        product_name=product_name,
                        delay=self.config.crawl_delay
                    )
                    
                    if external_result['success']:
                        customizations = external_result['customizations']
                        scrape_source = external_result['source']
                        external_platform = external_result.get('platform', 'unknown')
                        print(f"     ✓ Extracted from external configurator ({external_platform})")
                    else:
                        print(f"     ✗ External failed, falling back")
                        customizations = self.product_extractor.extract_customizations(markdown)
                        scrape_source = "product_page_fallback"
                
                # Embedded configurator URL
                elif configurator_info['configurator_url'] and configurator_info['configurator_type'] == 'embedded':
                    print(f"  → Following embedded configurator URL...")
                    time.sleep(self.config.crawl_delay)
                    
                    config_markdown = self.http_client.scrape_with_jina(configurator_info['configurator_url'])
                    
                    if config_markdown:
                        customizations = self.product_extractor.extract_customizations(config_markdown)
                        scrape_source = "embedded_configurator_page"
                        print(f"     ✓ Extracted from embedded configurator")
                    else:
                        customizations = self.product_extractor.extract_customizations(markdown)
                        scrape_source = "product_page_fallback"
                
                # Extract from current page
                else:
                    customizations = self.product_extractor.extract_customizations(markdown)
                    scrape_source = "product_page"
                    print(f"     ✓ Extracted from product page")
            
            # Build product data
            product_data = {
                'product_name': product_name,
                'url': url,
                'base_price': base_price,
                'specifications': specifications,
                'extraction_method': 'static',
                'model': 'S',
                
                # Configurator metadata
                'has_configurator': configurator_info['has_configurator'],
                'configurator_type': configurator_info['configurator_type'],
                'configurator_url': configurator_info['configurator_url'],
                'configurator_confidence': configurator_info['confidence'],
                'external_platform': external_platform,
                
                # Customization data
                'customization_source': scrape_source,
                'customization_categories': list(customizations.keys()),
                'customizations': customizations,
                'total_customization_options': sum(len(opts) for opts in customizations.values())
            }
            
            # Print summary (matching balanced_scraper format)
            print(f"\n  Summary:")
            print(f"     Name: {product_name}")
            print(f"     Model: S")
            print(f"     Price: {base_price or 'None'}")
            print(f"     Specifications: {len(specifications)}")
            print(f"\n")
            
            return product_data
        
        except Exception as e:
            print(f"  \033[31m[x]\033[0m Static extraction failed: {e}")
            return None
    
    async def scrape_all_products(self) -> Dict:
        """
        Main method: crawl website and scrape all products using static extraction.
        
        Returns:
            Complete product catalog
        """
        print(f"\n{'='*80}")
        print("DYNAMIC SCRAPER (MODEL-D)")
        print(f"{'='*80}")
        print(f"Target: {self.config.base_url}")
        print(f"Strategy: Static Only (Model-S)")
        print(f"Strictness: {self.strictness}")
        print(f"{'='*80}\n")
        
        # Step 1: Crawl and discover product pages
        print("Phase 1: Crawling and classification")
        print("-" * 80)
        
        product_urls = self.crawler.crawl(
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth
        )
        
        if not product_urls:
            print("\n\033[33m[WARN]\033[0m No product pages found!")
            return {}
        
        self.stats['product_pages_found'] = len(product_urls)
        
        # Step 2: Scrape each product
        print(f"\n{'='*80}")
        print("Phase 2: Product data extraction")
        print(f"{'='*80}")
        
        catalog = {}
        
        for i, url in enumerate(product_urls, 1):
            print(f"\n[{i}/{len(product_urls)}] Processing: {url}")
            
            # Try to use cached content from crawler
            markdown = self.crawler.get_page_content(url)
            
            # Await the async scrape_product call
            product_data = await self.scrape_product(url, markdown)
            
            if product_data:
                product_id = f"product_{len(catalog) + 1}"
                catalog[product_id] = product_data
            
            # Delay between products
            time.sleep(self.config.crawl_delay)
        
        print(f"\n{'='*80}")
        print("EXTRACTION COMPLETE")
        print(f"{'='*80}")
        self.print_statistics()
        
        return catalog
    
    def save_catalog(
        self,
        catalog: Dict,
        export_formats: List[str] = None
    ):
        """
        Save catalog in multiple formats.
        
        Args:
            catalog: Product catalog
            export_formats: List of formats
        """
        import os
        
        if export_formats is None:
            export_formats = ['json']
        
        print(f"\nSaving catalog...")
        
        for fmt in export_formats:
            if fmt == 'json':
                self.json_storage.save(catalog, self.config.full_output_path)
            
            elif fmt == 'csv':
                csv_path = self.config.full_output_path.replace('.json', '.csv')
                self.csv_storage.save_simple(catalog, csv_path)
            
            elif fmt == 'csv_prices' or fmt == 'csv_with_prices':
                csv_path = self.config.full_output_path.replace('.json', '_with_prices.csv')
                self.csv_storage.save_with_prices(catalog, csv_path)
            
            elif fmt == 'quotation':
                quot_path = self.config.full_output_path.replace('.json', '_quotation_template.json')
                self.quotation_template.create(catalog, quot_path)
            
            elif fmt == 'google_sheets':
                if self.google_sheets is None:
                    credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
                    self.google_sheets = GoogleSheetsStorage(credentials_file)
                
                spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID')
                
                if self.google_sheets.service:
                    self.google_sheets.save_catalog(
                        catalog,
                        spreadsheet_id=spreadsheet_id,
                        title="Product Catalog"
                    )
    
    def print_statistics(self):
        """Print scraping statistics."""
        print(f"\n\033[36m[STATS]\033[0m Statistics:")
        print(f"   Product pages found: {self.stats['product_pages_found']}")
        print(f"   Static extractions: {self.stats['static_extractions']}")
        print(f"   Failed extractions: {self.stats['failed_extractions']}")
        
        if self.stats['product_pages_found'] > 0:
            success_rate = (
                self.stats['static_extractions']
                / self.stats['product_pages_found'] * 100
            )
            print(f"   Success rate: {success_rate:.1f}%")
    
    def print_summary(self, catalog: Dict):
        """Print catalog summary."""
        print(f"\n{'='*80}")
        print("CATALOG SUMMARY")
        print(f"{'='*80}")
        print(f"Total products: {len(catalog)}")
        
        # Detailed breakdown
        for product_id, data in catalog.items():
            print(f"\n {data['product_name']}")
            print(f"   URL: {data['url']}")
            print(f"   Model: S")
            print(f"   Price: {data.get('base_price', 'N/A')}")
            print(f"   Extraction: {data.get('extraction_method', 'N/A')}")
            print(f"   Configurator: {data.get('configurator_type', 'none')}")
            print(f"   Options: {data.get('total_customization_options', 0)}")
        
        print(f"{'='*80}\n")