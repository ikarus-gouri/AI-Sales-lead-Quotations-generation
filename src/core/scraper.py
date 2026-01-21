"""Main scraper orchestrator."""

import time
from typing import Dict, Optional, Set
from .config import ScraperConfig
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..extractors.product_extractor import ProductExtractor
from ..classifiers.rule_based import RuleBasedClassifier
from ..classifiers.ai_classifier import AIClassifier
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
        
        # Initialize classifier (AI or rule-based)
        if config.use_ai_classification and config.gemini_api_key:
            self.classifier = AIClassifier(
                api_key=config.gemini_api_key,
                model_name=config.gemini_model
            )
        else:
            if config.use_ai_classification:
                print("⚠ Gemini API key not found, using rule-based classification")
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
        Scrape a single product page.
        
        Args:
            url: The product page URL
            
        Returns:
            Product data dictionary or None
        """
        print(f"\n{'─'*80}")
        print(f"Scraping product: {url}")
        print(f"{'─'*80}")
        time.sleep(15)
        # Scrape the page
        markdown = self.http_client.scrape_with_jina(url)
        
        if not markdown:
            return None
        
        # Extract product information
        product_name = self.product_extractor.extract_product_name(url, markdown)
        base_price = self.product_extractor.extract_base_price(markdown)
        customizations = self.product_extractor.extract_customizations(markdown)
        
        product_data = {
            "product_name": product_name,
            "url": url,
            "base_price": base_price,
            "customization_categories": list(customizations.keys()),
            "customizations": customizations,
            "total_customization_options": sum(len(opts) for opts in customizations.values())
        }
        
        # Print summary
        print(f"  Product: {product_name}")
        print(f"  Base Price: {base_price or 'Not found'}")
        print(f"  Categories: {len(customizations)}")
        print(f"  Total Options: {product_data['total_customization_options']}")
        
        return product_data
    
    def scrape_all_products(self) -> Dict[str, Dict]:
        """
        Main method: crawl website and scrape all products.
        
        Returns:
            Complete product catalog
        """
        print("\n" + "="*80)
        print("DYNAMIC PRODUCT CATALOG SCRAPER")
        print("="*80)
        
        # Step 1: Crawl and discover product pages
        product_urls = self.crawler.crawl(
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth
        )
        
        if not product_urls:
            print("\n⚠ No product pages found!")
            return {}
        
        # Step 2: Scrape each product
        print("\n" + "="*80)
        print("SCRAPING PRODUCT DETAILS")
        print("="*80)
        
        catalog = {}
        
        for url in product_urls:
            product_data = self.scrape_product(url)
            
            if product_data:
                product_id = product_data['product_name'].lower().replace(' ', '_')
                catalog[product_id] = product_data
            
            # Delay between product scrapes
            time.sleep(1)
        
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
                # Initialize Google Sheets on demand
                if self.google_sheets is None:
                    credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
                    self.google_sheets = GoogleSheetsStorage(credentials_file)
                
                # Check if spreadsheet ID is provided
                spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID')
                
                if self.google_sheets.service:
                    self.google_sheets.save_catalog(
                        catalog,
                        spreadsheet_id=spreadsheet_id,
                        title="Theraluxe Product Catalog"
                    )
    
    def print_summary(self, catalog: Dict):
        """
        Print catalog summary.
        
        Args:
            catalog: The catalog to summarize
        """
        print("\n" + "="*80)
        print("CATALOG SUMMARY")
        print("="*80 + "\n")
        
        total_products = len(catalog)
        total_categories = sum(len(p['customization_categories']) for p in catalog.values())
        total_options = sum(p['total_customization_options'] for p in catalog.values())
        
        print(f"Total Products: {total_products}")
        print(f"Total Customization Categories: {total_categories}")
        print(f"Total Customization Options: {total_options}\n")
        
        for product_id, data in catalog.items():
            print(f"📦 {data['product_name']}")
            print(f"   Price: {data['base_price'] or 'N/A'}")
            print(f"   Categories: {len(data['customization_categories'])}")
            print(f"   Options: {data['total_customization_options']}")
            print(f"   URL: {data['url']}\n")