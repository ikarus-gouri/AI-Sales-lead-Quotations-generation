
"""
Refactored scraper with proper handling of all customization scenarios.

Key improvements:
1. Uses UnifiedPageClassifier for clear product vs customization distinction
2. SmartExtractionRouter handles all extraction scenarios correctly
3. DeduplicationHelper prevents redundant scraping
4. Reuses cached content from crawl phase (no duplicate fetches)
"""

import time
from typing import Dict, Optional
from .config import ScraperConfig
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..extractors.product_extractor import ProductExtractor
from ..extractors.configurator_detector import ConfiguratorDetector
from ..extractors.external_configurator_scraper import ExternalConfiguratorScraper
from ..classifiers.unified_classifier import UnifiedPageClassifier, FastPageRouter
from ..classifiers.smart_extraction_router import SmartExtractionRouter
from ..classifiers.ai_classifier import AIClassifier
from ..crawlers.web_crawler import IntelligentWebCrawler
from ..storage.json_storage import JSONStorage
from ..storage.csv_storage import CSVStorage
from ..storage.google_sheets import GoogleSheetsStorage
from ..classifiers.smart_extraction_router import DeduplicationHelper
from ..storage.quotation_template import QuotationTemplate


class TheraluxeScraper:
    """
    Main scraper with intelligent routing and deduplication.
    
    Architecture:
    1. IntelligentWebCrawler discovers pages with URL pattern learning
    2. UnifiedPageClassifier distinguishes product vs customization pages
    3. SmartExtractionRouter extracts using optimal strategy
    4. DeduplicationHelper prevents redundant work
    """
    
    def __init__(self, config: ScraperConfig):
        """Initialize the scraper with all components."""
        self.config = config
        
        # Core components
        self.http_client = HTTPClient(timeout=config.request_timeout)
        self.link_extractor = LinkExtractor()
        self.product_extractor = ProductExtractor()
        self.configurator_detector = ConfiguratorDetector()
        self.external_scraper = ExternalConfiguratorScraper(
            http_client=self.http_client,
            product_extractor=self.product_extractor
        )
        
        # NEW: Unified classifier (replaces separate product classification)
        self.unified_classifier = UnifiedPageClassifier(
            configurator_detector=self.configurator_detector
        )
        
        # NEW: Smart extraction router
        self.extraction_router = SmartExtractionRouter(
            http_client=self.http_client,
            product_extractor=self.product_extractor,
            external_scraper=self.external_scraper,
            crawl_delay=config.crawl_delay
        )
        
        # NEW: Deduplication helper
        self.dedup_helper = DeduplicationHelper()
        
        # AI classifier (optional, for learning phase)
        self.ai_classifier = None
        if config.use_ai_classification and config.gemini_api_key:
            self.ai_classifier = AIClassifier(
                api_key=config.gemini_api_key,
                model_name=config.gemini_model
            )
        
        # Initialize crawler with unified classifier
        self.crawler = IntelligentWebCrawler(
            base_url=config.base_url,
            http_client=self.http_client,
            link_extractor=self.link_extractor,
            classifier=self.unified_classifier,  # Uses unified classifier
            crawl_delay=config.crawl_delay,
            learning_phase_pages=min(10, config.max_pages // 5)
        )
        
        # Storage
        self.json_storage = JSONStorage()
        self.csv_storage = CSVStorage()
        self.quotation_template = QuotationTemplate()
        self.google_sheets = None
    
    def scrape_product(self, url: str) -> Optional[Dict]:
        """
        Scrape a single product page with intelligent extraction routing.
        
        Args:
            url: Product or customization page URL
            
        Returns:
            Complete product data or None
        """
        print(f"\n{'─'*80}")
        print(f"Scraping: {url}")
        print(f"{'─'*80}")
        
        # OPTIMIZATION: Get cached content from crawl phase
        markdown = self.crawler.get_cached_content(url)
        
        if not markdown:
            # Not in cache, fetch it
            markdown = self.http_client.scrape_with_jina(url)
            if not markdown:
                print("  ✗ Failed to fetch page")
                return None
        else:
            print("  ✓ Using cached content (crawl phase)")
        
        # STEP 1: Classify the page comprehensively
        page_classification = self.unified_classifier.classify(url, markdown)
        
        print(f"  🏷️  Page Type: {page_classification.page_type.upper()}")
        print(f"     Confidence: {page_classification.confidence:.1%}")
        print(f"     Has Customization: {page_classification.has_customization}")
        print(f"     Customization Location: {page_classification.customization_location}")
        
        if page_classification.customization_url:
            print(f"     Customization URL: {page_classification.customization_url}")
        
        # STEP 2: Check for deduplication
        should_scrape, reason = self.dedup_helper.should_scrape(url, page_classification)
        
        if not should_scrape:
            print(f"  ⊘ Skipping: {reason}")
            return None
        
        # Mark as being scraped
        self.dedup_helper.mark_visited(url, page_classification.page_type)
        
        # STEP 3: Extract basic product information
        product_name = self.product_extractor.extract_product_name(url, markdown)
        base_price = self.product_extractor.extract_base_price(markdown)
        
        print(f"  📦 Product: {product_name}")
        if base_price:
            print(f"     Base Price: {base_price}")
        
        # STEP 4: Determine extraction strategy
        strategy = self.extraction_router.determine_strategy(
            page_classification=page_classification,
            already_visited=self.crawler.visited_pages
        )
        
        # Link configurator to product (for deduplication)
        if strategy.target_url and strategy.strategy_type != "same_page":
            self.dedup_helper.link_configurator_to_product(strategy.target_url, url)
        
        # STEP 5: Extract customizations using optimal strategy
        extraction_result = self.extraction_router.extract_customizations(
            strategy=strategy,
            current_url=url,
            current_markdown=markdown,
            product_name=product_name,
            page_cache=self.crawler.page_cache
        )
        
        # Print extraction results
        if extraction_result['success']:
            customizations = extraction_result['customizations']
            total_options = sum(len(opts) for opts in customizations.values())
            print(f"  ✓ Extracted: {len(customizations)} categories, {total_options} options")
        else:
            print(f"  ⚠ Extraction incomplete: {extraction_result.get('error', 'Unknown')}")
            customizations = {}
        
        # STEP 6: Build complete product data
        product_data = {
            # Basic info
            "product_name": product_name,
            "url": url,
            "base_price": base_price,
            
            # Page classification
            "page_type": page_classification.page_type,
            "classification_confidence": page_classification.confidence,
            
            # Customization metadata
            "has_customization": page_classification.has_customization,
            "customization_location": page_classification.customization_location,
            "customization_url": page_classification.customization_url,
            
            # Extraction info
            "extraction_strategy": strategy.strategy_type,
            "extraction_source": extraction_result['source'],
            "extraction_success": extraction_result['success'],
            
            # External platform (if applicable)
            "external_platform": extraction_result.get('external_platform'),
            
            # Customization data
            "customization_categories": list(customizations.keys()),
            "customizations": customizations,
            "total_customization_options": sum(len(opts) for opts in customizations.values()),
            
            # Signals (for debugging)
            "signals": page_classification.signals
        }
        
        return product_data
    
    def scrape_all_products(self) -> Dict[str, Dict]:
        """
        Main method: intelligent crawl and scrape all products.
        
        Returns:
            Complete product catalog with no duplicates
        """
        print("\n" + "="*80)
        print("INTELLIGENT PRODUCT CATALOG SCRAPER v2.0")
        print("="*80)
        print("Features:")
        print("  • URL pattern learning")
        print("  • Smart extraction routing")
        print("  • Automatic deduplication")
        print("  • Cache reuse (no duplicate fetches)")
        print("="*80)
        
        # PHASE 1: Intelligent crawling with pattern learning
        discovered_urls = self.crawler.crawl(
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth
        )
        
        if not discovered_urls:
            print("\n⚠ No product pages found!")
            return {}
        
        print(f"\n✓ Discovered {len(discovered_urls)} potential product pages")
        
        # PHASE 2: Scrape each discovered page
        print("\n" + "="*80)
        print("SCRAPING PRODUCT DETAILS")
        print("="*80)
        
        catalog = {}
        skipped_count = 0
        
        for url in discovered_urls:
            product_data = self.scrape_product(url)
            
            if product_data:
                # Use product name as key
                product_id = self._generate_product_id(product_data['product_name'])
                
                # Check for duplicate product IDs (different URLs, same product)
                if product_id in catalog:
                    print(f"  ⚠ Duplicate product ID: {product_id}")
                    # Merge or use better version
                    if self._is_better_version(product_data, catalog[product_id]):
                        print(f"     → Using newer version")
                        catalog[product_id] = product_data
                    else:
                        print(f"     → Keeping existing version")
                else:
                    catalog[product_id] = product_data
            else:
                skipped_count += 1
            
            # Delay between product scrapes
            time.sleep(self.config.crawl_delay)
        
        # Print statistics
        print(f"\n{'='*80}")
        print(f"SCRAPING COMPLETE")
        print(f"{'='*80}")
        print(f"✓ Products scraped: {len(catalog)}")
        print(f"⊘ Pages skipped (duplicates/errors): {skipped_count}")
        print(f"{'='*80}")
        
        # Print deduplication stats
        self.dedup_helper.print_stats()
        
        return catalog
    
    def _generate_product_id(self, product_name: str) -> str:
        """Generate consistent product ID from name."""
        import re
        # Remove special characters, convert to lowercase, replace spaces
        clean_name = re.sub(r'[^a-z0-9\s-]', '', product_name.lower())
        product_id = re.sub(r'[\s-]+', '_', clean_name).strip('_')
        return product_id or "unknown_product"
    
    def _is_better_version(self, new_data: Dict, existing_data: Dict) -> bool:
        """
        Determine if new product data is better than existing.
        
        Criteria:
        1. More customization options
        2. Has price when existing doesn't
        3. Higher classification confidence
        """
        new_options = new_data['total_customization_options']
        existing_options = existing_data['total_customization_options']
        
        # More options = better
        if new_options > existing_options:
            return True
        
        # Same options but new has price
        if new_options == existing_options:
            if new_data['base_price'] and not existing_data['base_price']:
                return True
        
        # Higher confidence
        if new_options == existing_options:
            if new_data['classification_confidence'] > existing_data['classification_confidence']:
                return True
        
        return False
    def save_catalog(self, catalog: Dict, export_formats: list = ['json']):
        """Save catalog to file(s)."""
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
        """Print comprehensive catalog summary."""
        print("\n" + "="*80)
        print("CATALOG SUMMARY")
        print("="*80 + "\n")
        
        # Overall statistics
        total_products = len(catalog)
        
        # Group by page type
        product_pages = [p for p in catalog.values() if p['page_type'] == 'product']
        customization_pages = [p for p in catalog.values() if p['page_type'] == 'customization']
        
        # Group by customization location
        same_page = [p for p in catalog.values() if p['customization_location'] == 'same_page']
        embedded = [p for p in catalog.values() if p['customization_location'] == 'embedded_url']
        external = [p for p in catalog.values() if p['customization_location'] == 'external_url']
        no_custom = [p for p in catalog.values() if p['customization_location'] == 'none']
        
        # Totals
        total_categories = sum(len(p['customization_categories']) for p in catalog.values())
        total_options = sum(p['total_customization_options'] for p in catalog.values())
        
        print(f"📊 Overview:")
        print(f"   Total Products: {total_products}")
        print(f"   └─ Product Pages: {len(product_pages)}")
        print(f"   └─ Customization Pages: {len(customization_pages)}")
        print(f"\n   Customization Locations:")
        print(f"   └─ Same Page: {len(same_page)}")
        print(f"   └─ Embedded URL: {len(embedded)}")
        print(f"   └─ External URL: {len(external)}")
        print(f"   └─ No Customization: {len(no_custom)}")
        print(f"\n   Total Categories: {total_categories}")
        print(f"   Total Options: {total_options}")
        
        # URL Intelligence stats
        if self.crawler.site_profile:
            print(f"\n🧠 URL Intelligence:")
            print(f"   Pattern Hit Rate: {self.crawler.site_profile.pattern_hit_rate:.1%}")
            classifications_saved = self.crawler.stats['classifications_skipped']
            total_classifications = classifications_saved + self.crawler.stats['classifications_performed']
            efficiency = (classifications_saved / total_classifications * 100) if total_classifications > 0 else 0
            print(f"   Classifications Saved: {classifications_saved}/{total_classifications} ({efficiency:.1f}%)")
        
        # Extraction success rate
        successful_extractions = sum(1 for p in catalog.values() if p['extraction_success'])
        success_rate = (successful_extractions / total_products * 100) if total_products > 0 else 0
        print(f"\n📈 Extraction Success Rate: {success_rate:.1f}%")
        
        print(f"\n{'─'*80}\n")
        
        # Detailed product list
        for product_id, data in catalog.items():
            print(f"📦 {data['product_name']}")
            print(f"   URL: {data['url']}")
            print(f"   Type: {data['page_type']} (confidence: {data['classification_confidence']:.0%})")
            
            if data['base_price']:
                print(f"   Price: {data['base_price']}")
            
            print(f"   Customization: {data['customization_location']}")
            
            if data['customization_url']:
                print(f"   └─ URL: {data['customization_url']}")
            
            if data.get('external_platform'):
                print(f"   └─ Platform: {data['external_platform']}")
            
            print(f"   Extraction: {data['extraction_strategy']} → {data['extraction_source']}")
            print(f"   Options: {len(data['customization_categories'])} categories, {data['total_customization_options']} total")
            print()


            