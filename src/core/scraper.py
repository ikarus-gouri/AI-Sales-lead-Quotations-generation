"""Main scraper orchestrator with dynamic configurator detection."""

import time
from typing import Dict, Optional
from .config import ScraperConfig
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..extractors.product_extractor import ProductExtractor
from ..extractors.configurator_detector import ConfiguratorDetector
from ..extractors.external_configurator_scraper import ExternalConfiguratorScraper
from ..classifiers.rule_based import RuleBasedClassifier
from ..crawlers.web_crawler import WebCrawler
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.google_sheets import GoogleSheetsStorage
from ..storage.quotation_template import QuotationTemplate


class TheraluxeScraper:
    """Main scraper that orchestrates the crawling and extraction."""
    
    def __init__(self, config: ScraperConfig):
        """
        Initialize the scraper.
        
        Args:
            config: Scraper configuration
        """
        self.config = config
        
        # Initialize components
        self.http_client = HTTPClient(timeout=config.request_timeout)
        self.link_extractor = LinkExtractor()
        self.product_extractor = ProductExtractor()
        self.configurator_detector = ConfiguratorDetector()
        self.external_scraper = ExternalConfiguratorScraper(
            http_client=self.http_client,
            product_extractor=self.product_extractor
        )
        
        # Initialize rule-based classifier
        self.classifier = RuleBasedClassifier()
        
        # Initialize crawler
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
        self.google_sheets = None  # Initialized on demand
    
    def scrape_product(self, url: str) -> Optional[Dict]:
        """
        Scrape a single product page with intelligent configurator handling.
        
        Args:
            url: The product page URL
            
        Returns:
            Product data dictionary or None
        """
        print(f"\n{'─'*80}")
        print(f"Scraping product: {url}")
        print(f"{'─'*80}")
        
        # Scrape the page
        markdown = self.http_client.scrape_with_jina(url)
        
        if not markdown:
            return None
        
        # Detect configurator dynamically
        configurator_info = self.configurator_detector.has_configurator(url, markdown)
        
        # Log detection results
        print(f"  📋 Configurator Detection:")
        print(f"     Type: {configurator_info['configurator_type'].upper()}")
        print(f"     Confidence: {configurator_info['confidence']:.2%}")
        print(f"     Signals: {configurator_info['signals']}")
        
        if configurator_info['configurator_url']:
            print(f"     URL: {configurator_info['configurator_url']}")
        
        # Determine if we should scrape customizations
        should_scrape, reason = self.configurator_detector.should_scrape_configurator(configurator_info)
        
        # Extract basic product information
        product_name = self.product_extractor.extract_product_name(url, markdown)
        base_price = self.product_extractor.extract_base_price(markdown)
        
        customizations = {}
        scrape_source = "none"
        external_platform = None
        
        if should_scrape:
            print(f"  → Extracting customizations ({reason})...")
            
            # Strategy 1: External configurator
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
                    print(f"     ✗ External configurator failed: {external_result.get('error', 'Unknown error')}")
                    print(f"     → Falling back to product page")
                    customizations = self.product_extractor.extract_customizations(markdown)
                    scrape_source = "product_page_fallback"
            
            # Strategy 2: Embedded configurator URL
            elif configurator_info['configurator_url'] and configurator_info['configurator_type'] == 'embedded':
                print(f"  → Following embedded configurator URL...")
                time.sleep(self.config.crawl_delay)
                
                config_markdown = self.http_client.scrape_with_jina(configurator_info['configurator_url'])
                
                if config_markdown:
                    customizations = self.product_extractor.extract_customizations(config_markdown)
                    scrape_source = "embedded_configurator_page"
                    print(f"     ✓ Extracted from embedded configurator page")
                else:
                    print(f"     ✗ Failed to load configurator page, using current page")
                    customizations = self.product_extractor.extract_customizations(markdown)
                    scrape_source = "product_page_fallback"
            
            # Strategy 3: Extract from current page
            else:
                customizations = self.product_extractor.extract_customizations(markdown)
                scrape_source = "product_page"
                print(f"     ✓ Extracted from product page")
        else:
            print(f"  → Skipping customization extraction: {reason}")
        
        # Build product data
        product_data = {
            "product_name": product_name,
            "url": url,
            "base_price": base_price,
            
            # Configurator metadata
            "has_configurator": configurator_info['has_configurator'],
            "configurator_type": configurator_info['configurator_type'],
            "configurator_url": configurator_info['configurator_url'],
            "configurator_confidence": configurator_info['confidence'],
            "configurator_signals": configurator_info['signals'],
            
            # External platform info
            "external_platform": external_platform,
            
            # Customization data
            "customization_source": scrape_source,
            "customization_categories": list(customizations.keys()),
            "customizations": customizations,
            "total_customization_options": sum(len(opts) for opts in customizations.values())
        }
        
        # Print summary
        print(f"\n  📦 Product Summary:")
        print(f"     Name: {product_name}")
        print(f"     Price: {base_price or 'Not found'}")
        print(f"     Categories: {len(customizations)}")
        print(f"     Total Options: {product_data['total_customization_options']}")
        
        return product_data
    
    def scrape_all_products(self) -> Dict[str, Dict]:
        """
        Main method: crawl website and scrape all products.
        
        Returns:
            Complete product catalog
        """
        print("\n" + "="*80)
        print("PRODUCT CATALOG SCRAPER")
        print("="*80)
        
        # Step 1: Crawl and discover product pages
        product_urls = self.crawler.crawl(
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth
        )
        
        if not product_urls:
            print("\n⚠️  No product pages found!")
            return {}
        
        # Step 2: Scrape each product
        print("\n" + "="*80)
        print("SCRAPING PRODUCT DETAILS")
        print("="*80)
        
        catalog = {}
        
        for url in product_urls:
            product_data = self.scrape_product(url)
            
            if product_data:
                product_id = product_data['product_name'].lower().replace(' ', '_').replace('-', '_')
                catalog[product_id] = product_data
            
            # Delay between product scrapes
            time.sleep(self.config.crawl_delay)
        
        return catalog
    
    def save_catalog(self, catalog: Dict, export_formats: list = ['json']):
        """
        Save catalog to file(s).
        
        Args:
            catalog: The catalog to save
            export_formats: List of formats ['json', 'csv', 'csv_prices', 'google_sheets', 'quotation']
        """
        import os
        
        for fmt in export_formats:
            if fmt == 'json':
                self.json_storage.save(catalog, self.config.full_output_path)
            
            elif fmt == 'csv':
                csv_path = self.config.full_output_path.replace('.json', '.csv')
                self.csv_storage.save_simple(catalog, csv_path)
            
            elif fmt == 'csv_prices':
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
    
    def print_summary(self, catalog: Dict):
        """
        Print comprehensive catalog summary.
        
        Args:
            catalog: The catalog to summarize
        """
        print("\n" + "="*80)
        print("CATALOG SUMMARY")
        print("="*80 + "\n")
        
        total_products = len(catalog)
        total_with_configurator = sum(1 for p in catalog.values() if p['has_configurator'])
        total_embedded = sum(1 for p in catalog.values() if p['configurator_type'] == 'embedded')
        total_external = sum(1 for p in catalog.values() if p['configurator_type'] == 'external')
        total_categories = sum(len(p['customization_categories']) for p in catalog.values())
        total_options = sum(p['total_customization_options'] for p in catalog.values())
        
        print(f"📊 Overview:")
        print(f"   Total Products: {total_products}")
        print(f"   Products with Configurator: {total_with_configurator}")
        print(f"     → Embedded: {total_embedded}")
        print(f"     → External: {total_external}")
        print(f"   Total Customization Categories: {total_categories}")
        print(f"   Total Customization Options: {total_options}\n")
        
        print(f"{'─'*80}\n")
        
        for product_id, data in catalog.items():
            print(f"📦 {data['product_name']}")
            print(f"   URL: {data['url']}")
            print(f"   Price: {data['base_price'] or 'N/A'}")
            print(f"   Configurator: {data['configurator_type']} (confidence: {data['configurator_confidence']:.0%})")
            
            if data['configurator_url']:
                print(f"   Configurator URL: {data['configurator_url']}")
            
            if data.get('external_platform'):
                print(f"   External Platform: {data['external_platform']}")
            
            print(f"   Categories: {len(data['customization_categories'])}")
            print(f"   Options: {data['total_customization_options']}")
            print(f"   Source: {data['customization_source']}")
            print()