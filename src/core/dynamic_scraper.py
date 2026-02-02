"""Model-D: Hybrid scraper with automatic static/dynamic routing.

This scraper intelligently routes each page to either Model-S (static) or
Model-D (browser-based) extraction based on dynamic configurator detection.

Features:
    - Automatic per-page routing (S or D)
    - Browser automation with Playwright
    - JavaScript configurator handling
    - Interactive control discovery
    - Network activity monitoring
    - Price learning from user interactions
    - Fallback to Model-S on browser failures

Detection Criteria (for Model-D):
    - JavaScript framework detected (React, Vue, Angular)
    - SPA indicators (single-page app)
    - Dynamic pricing signals
    - Price present but NO static options (confidence: 50%)
    - Known e-commerce platforms

Workflow:
    1. Crawl website with DynamicClassifier
    2. For each product page:
        a. Detect if dynamic configurator (DynamicConfiguratorDetector)
        b. If confidence >= 50%: Use Model-D (browser)
        c. Otherwise: Use Model-S (static)
    3. Extract product data using appropriate method
    4. Export to multiple formats

Usage:
    scraper = DynamicScraper(
        config,
        strictness="balanced",
        enable_browser=True,
        headless=True
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
from ..dynamic.browser_engine import BrowserRunner, BrowserConfig
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.google_sheets import GoogleSheetsStorage
from ..storage.quotation_template import QuotationTemplate


class DynamicScraper:
    """Model-D: Hybrid scraper with automatic static/dynamic routing.
    
    This scraper uses DynamicClassifier to intelligently route each page
    to either Model-S (static) or Model-D (browser) extraction based on
    dynamic configurator detection.
    
    Workflow:
        1. Crawl pages using enhanced web crawler
        2. Classify with DynamicClassifier (routes to Model-S or Model-D)
        3. Extract using appropriate method:
           - Model-S: Static extraction (ProductExtractor)
           - Model-D: Browser execution (BrowserRunner)
        4. Merge results into unified catalog
    
    Attributes:
        config: ScraperConfig with crawl and browser settings
        classifier: DynamicClassifier for hybrid routing
        crawler: WebCrawler with dynamic classification
        browser_config: BrowserConfig for Playwright settings
        enable_browser: Whether Model-D is available (requires Playwright)
        headless: Whether to run browser in headless mode
    
    Example:
        >>> config = ScraperConfig(base_url="https://example.com")
        >>> scraper = DynamicScraper(
        ...     config,
        ...     strictness="balanced",
        ...     enable_browser=True,
        ...     headless=True
        ... )
        >>> catalog = scraper.scrape_all_products()
        >>> scraper.save_catalog(catalog, export_formats=['json'])
    """
    
    def __init__(
        self,
        config: ScraperConfig,
        strictness: str = "balanced",
        enable_browser: bool = True,
        headless: bool = True
    ):
        """
        Initialize dynamic scraper.
        
        Args:
            config: Scraper configuration
            strictness: Classification strictness ('lenient', 'balanced', 'strict')
            enable_browser: Enable Model-D (if False, falls back to Model-S only)
            headless: Run browser in headless mode (default: True)
        """
        self.config = config
        self.strictness = strictness
        self.enable_browser = enable_browser
        self.headless = headless
        
        # Map strictness string to enum for consistency
        strictness_map = {
            "lenient": StrictnessLevel.LENIENT,
            "balanced": StrictnessLevel.BALANCED,
            "strict": StrictnessLevel.STRICT
        }
        self.strictness_level = strictness_map.get(strictness.lower(), StrictnessLevel.BALANCED)
        
        # Initialize core components (same as BalancedScraper)
        self.http_client = HTTPClient(timeout=config.request_timeout)
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
            classifier=self.classifier,  # Uses dynamic classifier for routing
            crawl_delay=config.crawl_delay
        )
        
        # Browser config for Model-D
        self.browser_config = BrowserConfig(
            headless=self.headless,
            timeout=60000,  # 60 seconds for slow-loading pages
            wait_after_action=1000
        )
        
        # Initialize storage (same as BalancedScraper)
        self.json_storage = JSONStorage()
        self.csv_storage = CSVStorage()
        self.quotation_template = QuotationTemplate()
        self.google_sheets = None
        
        # Statistics
        self.stats = {
            'total_pages_crawled': 0,
            'product_pages_found': 0,
            'static_extractions': 0,
            'dynamic_extractions': 0,
            'failed_extractions': 0,
            'model_s_count': 0,
            'model_d_count': 0
        }
        
        print(f"\033[32m[✓]\033[0m Dynamic Scraper initialized")
        print(f"  Mode: {'Hybrid (Model-S + Model-D)' if enable_browser else 'Static Only (Model-S)'}")
        print(f"  Strictness: {strictness}")
        print(f"  Max pages: {config.max_pages}")
    
    def _transform_options_to_customizations(self, options_discovered: List[Dict]) -> Dict:
        """
        Transform Model-D options_discovered to Model-S customizations format.
        
        Now supports state-aware options with categories.
        
        Args:
            options_discovered: List of discovered options from state exploration
            
        Returns:
            Dictionary with categorized options matching Model-S format
        """
        customizations = {}
        
        for option in options_discovered:
            # Get category (from state exploration)
            category = option.get('category', option.get('group', 'Options'))
            
            if category not in customizations:
                customizations[category] = []
            
            # Extract price delta (prefer numeric, fallback to text)
            price_delta = option.get('price_delta', 0.0)
            if price_delta is None and option.get('price_text'):
                # Try to parse from text
                import re
                match = re.search(r'\$([0-9,]+\.?\d*)', option.get('price_text', ''))
                if match:
                    try:
                        price_delta = float(match.group(1).replace(',', ''))
                    except:
                        price_delta = 0.0
            
            # Transform to Model-S format
            customizations[category].append({
                'name': option.get('label', 'Unknown'),
                'price_delta': price_delta or 0.0,
                'available': option.get('available', True),
                'type': option.get('type', 'unknown')
            })
        
        return customizations
    
    async def scrape_product(self, url: str, markdown: str = None) -> Optional[Dict]:
        """
        Scrape a single product page with hybrid Model-S/Model-D approach.
        
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
        print(f"     Model: {classification['model']}")
        print(f"     Confidence: {classification['confidence']:.0%}")
        
        # Route to appropriate extraction method
        model = classification['model']
        
        if model == 'D' and self.enable_browser:
            # Model-D: Browser-based extraction (await the async call)
            product_data = await self._extract_dynamic(url, markdown, classification)
            if product_data:
                self.stats['dynamic_extractions'] += 1
                self.stats['model_d_count'] += 1
        else:
            # Model-S: Static extraction
            product_data = self._extract_static(url, markdown, classification)
            if product_data:
                self.stats['static_extractions'] += 1
                self.stats['model_s_count'] += 1
        
        if product_data:
            # Add classification metadata
            product_data['classification'] = classification
            product_data['model'] = model
        else:
            self.stats['failed_extractions'] += 1
        
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
            print(f"\n")
            
            return product_data
        
        except Exception as e:
            print(f"  \033[31m[x]\033[0m Static extraction failed: {e}")
            return None
    
    async def _extract_dynamic(self, url: str, markdown: str, classification: Dict) -> Optional[Dict]:
        """Extract product data using Model-D (browser-based)."""
        try:
            print(f"  \033[36m[D]\033[0m Using Model-D (browser-based extraction)")
            
            # Initialize browser runner
            runner = BrowserRunner(self.browser_config)
            
            # Run dynamic extraction
            result = await runner.extract_dynamic_configurator(url)
            
            if not result['success']:
                print(f"  \033[31m[x]\033[0m Dynamic extraction failed: {result.get('error')}")
                print(f"  \u21bb Falling back to Model-S")
                # Fallback to static
                return self._extract_static(url, markdown, classification)
            
            # Extract basic info from markdown (fallback)
            product_name = self.product_extractor.extract_product_name(url, markdown)
            
            # Transform options_discovered to customizations format (compatible with Model-S)
            customizations = self._transform_options_to_customizations(result['options_discovered'])
            
            # Build product data
            product_data = {
                'product_name': product_name,
                'url': url,
                'base_price': result['pricing_model'].get('base_price'),
                'extraction_method': 'dynamic_browser',
                'model': 'D',
                
                # Model-D specific data
                'pricing_model': result['pricing_model'],
                'options_discovered': result['options_discovered'],
                'network_activity': result['network_activity'][:10],  # Limit
                
                # Compatibility fields (match Model-S format)
                'has_configurator': True,
                'configurator_type': 'dynamic',
                'configurator_url': None,
                'configurator_confidence': 1.0,
                'external_platform': None,
                'customization_source': 'dynamic_browser',
                'customization_categories': list(customizations.keys()),
                'customizations': customizations,
                'total_customization_options': len(result['options_discovered'])
            }
            
            print(f"  ✓ Model-D extraction complete")
            print(f"    Name: {product_name}")
            print(f"    Base price: ${result['pricing_model'].get('base_price', 'N/A')}")
            print(f"    Options: {len(result['options_discovered'])}")
            print(f"    Categories: {len(customizations)}")
            
            return product_data
        
        except Exception as e:
            print(f"  \033[31m[x]\033[0m Dynamic extraction failed: {e}")
            print(f"  \u21bb Falling back to Model-S")
            return self._extract_static(url, markdown, classification)
    
    async def scrape_all_products(self) -> Dict:
        """
        Main method: crawl website and scrape all products using hybrid approach.
        
        Returns:
            Complete product catalog
        """
        print(f"\n{'='*80}")
        print("DYNAMIC SCRAPER (MODEL-D)")
        print(f"{'='*80}")
        print(f"Target: {self.config.base_url}")
        print(f"Strategy: {'Hybrid (Model-S + Model-D)' if self.enable_browser else 'Static Only (Model-S)'}")
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
        print(f"   Model-S extractions: {self.stats['static_extractions']}")
        print(f"   Model-D extractions: {self.stats['dynamic_extractions']}")
        print(f"   Failed extractions: {self.stats['failed_extractions']}")
        
        if self.stats['product_pages_found'] > 0:
            success_rate = (
                (self.stats['static_extractions'] + self.stats['dynamic_extractions'])
                / self.stats['product_pages_found'] * 100
            )
            print(f"   Success rate: {success_rate:.1f}%")
    
    def print_summary(self, catalog: Dict):
        """Print catalog summary."""
        print(f"\n{'='*80}")
        print("CATALOG SUMMARY")
        print(f"{'='*80}")
        print(f"Total products: {len(catalog)}")
        
        model_s = sum(1 for p in catalog.values() if p.get('model') == 'S')
        model_d = sum(1 for p in catalog.values() if p.get('model') == 'D')
        
        print(f"  Model-S (static): {model_s}")
        print(f"  Model-D (dynamic): {model_d}")
        
        # Detailed breakdown
        for product_id, data in catalog.items():
            print(f"\n {data['product_name']}")
            print(f"   URL: {data['url']}")
            print(f"   Model: {data['model']}")
            print(f"   Price: {data.get('base_price', 'N/A')}")
            print(f"   Extraction: {data.get('extraction_method', 'N/A')}")
            
            if data.get('model') == 'S':
                print(f"   Configurator: {data.get('configurator_type', 'none')}")
                print(f"   Options: {data.get('total_customization_options', 0)}")
            elif data.get('model') == 'D':
                pm = data.get('pricing_model', {})
                print(f"   Options discovered: {len(data.get('options_discovered', []))}")
                print(f"   Price deltas: {len(pm.get('option_deltas', {}))}")
        
        print(f"{'='*80}\n")