"""Smart extraction router that handles all customization scenarios correctly."""

import time
from typing import Dict, Optional
from dataclasses import dataclass
from PIL import Image
import io
import requests


# -------------------------------------------------------------------
# Color Normalization Helper
# -------------------------------------------------------------------

class ColorNormalizationHelper:
    """
    Normalizes color customizations:
    - Color name -> hex
    - Color image -> dominant hex
    """

    BASIC_COLOR_MAP = {
        "black": "#000000",
        "white": "#FFFFFF",
        "red": "#FF0000",
        "blue": "#0000FF",
        "green": "#008000",
        "grey": "#808080",
        "gray": "#808080",
        "brown": "#8B4513",
        "beige": "#F5F5DC"
    }

    def normalize(self, customizations: Dict) -> Dict:
        if not customizations:
            return customizations

        for key, options in customizations.items():
            if not isinstance(options, list):
                continue

            normalized = []
            for opt in options:
                normalized.append(self._normalize_option(opt))

            customizations[key] = normalized

        return customizations

    def _normalize_option(self, option: Dict) -> Dict:
        # Case 1: Already has hex
        if "hex" in option:
            return option

        # Case 2: Color name
        name = option.get("label", "").lower()
        if name in self.BASIC_COLOR_MAP:
            option["hex"] = self.BASIC_COLOR_MAP[name]
            return option

        # Case 3: Image-based color
        image_url = option.get("image")
        if image_url:
            hex_color = self._extract_dominant_color(image_url)
            if hex_color:
                option["hex"] = hex_color

        return option

    def _extract_dominant_color(self, image_url: str) -> Optional[str]:
        try:
            response = requests.get(image_url, timeout=10)
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            image = image.resize((50, 50))

            pixels = list(image.getdata())
            avg = tuple(sum(c) // len(pixels) for c in zip(*pixels))

            return "#{:02X}{:02X}{:02X}".format(*avg)
        except Exception:
            return None


# -------------------------------------------------------------------
# Extraction Strategy
# -------------------------------------------------------------------

@dataclass
class ExtractionStrategy:
    """Defines how to extract customizations from a page."""
    strategy_type: str  # "same_page", "embedded_url", "external_url", "no_customization"
    target_url: Optional[str]
    should_fetch_additional: bool
    confidence: float
    reason: str


# -------------------------------------------------------------------
# Smart Extraction Router
# -------------------------------------------------------------------

class SmartExtractionRouter:
    """
    Routes extraction based on page classification and customization location.
    
    Handles 4 scenarios:
    1. Product page with embedded customization (same page) - extract directly
    2. Product page with embedded customization URL (same domain) - fetch and extract
    3. Product page with external customization URL (different domain) - external scraper
    4. Standalone customization page - extract directly
    """

    def __init__(
        self,
        http_client,
        product_extractor,
        external_scraper,
        crawl_delay: float = 0.5
    ):
        """
        Initialize extraction router.
        
        Args:
            http_client: HTTPClient for fetching pages
            product_extractor: ProductExtractor for standard extraction
            external_scraper: ExternalConfiguratorScraper for external platforms
            crawl_delay: Delay between requests
        """
        self.http_client = http_client
        self.product_extractor = product_extractor
        self.external_scraper = external_scraper
        self.crawl_delay = crawl_delay

        # Color normalization
        self.color_normalizer = ColorNormalizationHelper()

    def determine_strategy(
        self,
        page_classification,
        already_visited: set = None
    ) -> ExtractionStrategy:
        """
        Determine the best extraction strategy based on classification.
        
        Args:
            page_classification: PageClassification from UnifiedPageClassifier
            already_visited: Set of already visited URLs (for optimization)
            
        Returns:
            ExtractionStrategy defining how to extract
        """
        if not page_classification.has_customization:
            return ExtractionStrategy(
                strategy_type="no_customization",
                target_url=None,
                should_fetch_additional=False,
                confidence=page_classification.confidence,
                reason="No customization detected"
            )
        
        location = page_classification.customization_location
        custom_url = page_classification.customization_url
        
        # Scenario 1: Customization on same page
        if location == "same_page":
            return ExtractionStrategy(
                strategy_type="same_page",
                target_url=None,
                should_fetch_additional=False,
                confidence=page_classification.confidence,
                reason="Customization embedded on product page"
            )
        
        # Scenario 2: External customization URL (different domain)
        if location == "external_url":
            return ExtractionStrategy(
                strategy_type="external_url",
                target_url=custom_url,
                should_fetch_additional=True,
                confidence=page_classification.confidence,
                reason=f"External configurator at {custom_url}"
            )
        
        # Scenario 3: Embedded URL (same domain)
        if location == "embedded_url":
            # Optimization: Check if we already visited this URL during crawling
            if already_visited and custom_url in already_visited:
                return ExtractionStrategy(
                    strategy_type="same_page",  # Use cached content
                    target_url=custom_url,  # But note the URL for cache lookup
                    should_fetch_additional=False,
                    confidence=page_classification.confidence,
                    reason=f"Embedded configurator already crawled: {custom_url}"
                )
            else:
                return ExtractionStrategy(
                    strategy_type="embedded_url",
                    target_url=custom_url,
                    should_fetch_additional=True,
                    confidence=page_classification.confidence,
                    reason=f"Embedded configurator at {custom_url}"
                )
        
        # Fallback
        return ExtractionStrategy(
            strategy_type="same_page",
            target_url=None,
            should_fetch_additional=False,
            confidence=page_classification.confidence,
            reason="Fallback to same page extraction"
        )

    def extract_customizations(
        self,
        strategy: ExtractionStrategy,
        current_url: str,
        current_markdown: str,
        product_name: str,
        page_cache: Dict[str, str] = None
    ) -> Dict:
        """
        Extract customizations using the determined strategy.
        
        Args:
            strategy: ExtractionStrategy from determine_strategy()
            current_url: URL of current page
            current_markdown: Content of current page
            product_name: Product name for logging
            page_cache: Optional cache of already-fetched pages
            
        Returns:
            {
                'customizations': dict,
                'source': str,
                'external_platform': str or None,
                'success': bool,
                'error': str or None
            }
        """
        print(f"  📋 Extraction Strategy: {strategy.strategy_type}")
        print(f"     Reason: {strategy.reason}")
        
        # Strategy 1: Same page extraction
        if strategy.strategy_type == "same_page":
            result = self._extract_same_page(current_markdown)
        
        # Strategy 2: External URL (different domain)
        elif strategy.strategy_type == "external_url":
            result = self._extract_external(
                strategy.target_url,
                product_name
            )
        
        # Strategy 3: Embedded URL (same domain)
        elif strategy.strategy_type == "embedded_url":
            result = self._extract_embedded(
                strategy.target_url,
                current_markdown,
                page_cache
            )
        
        # Strategy 4: No customization
        elif strategy.strategy_type == "no_customization":
            result = {
                'customizations': {},
                'source': 'none',
                'external_platform': None,
                'success': True,
                'error': None
            }
        
        # Fallback
        else:
            result = self._extract_same_page(current_markdown)
        
        # Normalize colors in customizations
        if result.get("customizations"):
            result["customizations"] = self.color_normalizer.normalize(
                result["customizations"]
            )
        
        return result

    def _extract_same_page(self, markdown: str) -> Dict:
        """Extract from current page content."""
        customizations = self.product_extractor.extract_customizations(markdown)
        
        return {
            'customizations': customizations,
            'source': 'same_page',
            'external_platform': None,
            'success': len(customizations) > 0,
            'error': None if customizations else "No customizations found"
        }

    def _extract_external(self, external_url: str, product_name: str) -> Dict:
        """Extract from external configurator platform."""
        print(f"  → Scraping external configurator...")
        
        # Add delay before external request
        time.sleep(10)  # External sites need more respect
        
        result = self.external_scraper.scrape_external_configurator(
            url=external_url,
            product_name=product_name,
            delay=self.crawl_delay
        )
        
        if result['success']:
            print(f"     ✓ Extracted from external ({result.get('platform', 'unknown')})")
            return {
                'customizations': result['customizations'],
                'source': 'external_configurator',
                'external_platform': result.get('platform', 'unknown'),
                'success': True,
                'error': None
            }
        else:
            print(f"     ✗ External extraction failed: {result.get('error')}")
            return {
                'customizations': {},
                'source': 'external_configurator_failed',
                'external_platform': result.get('platform'),
                'success': False,
                'error': result.get('error')
            }

    def _extract_embedded(
        self,
        embedded_url: str,
        fallback_markdown: str,
        page_cache: Dict[str, str] = None
    ) -> Dict:
        """Extract from embedded configurator URL (same domain)."""
        print(f"  → Checking embedded configurator...")
        
        # Try cache first (optimization!)
        markdown = None
        if page_cache and embedded_url in page_cache:
            print(f"     ✓ Using cached content from crawl phase")
            markdown = page_cache[embedded_url]
        else:
            # Fetch the embedded page
            print(f"     → Fetching: {embedded_url}")
            time.sleep(self.crawl_delay)
            markdown = self.http_client.scrape_with_jina(embedded_url)
        
        if markdown:
            customizations = self.product_extractor.extract_customizations(markdown)
            
            if customizations:
                print(f"     ✓ Extracted from embedded page")
                return {
                    'customizations': customizations,
                    'source': 'embedded_configurator',
                    'external_platform': None,
                    'success': True,
                    'error': None
                }
            else:
                print(f"     ⚠ No customizations found, trying fallback")
        else:
            print(f"     ✗ Failed to fetch embedded page")
        
        # Fallback to current page
        print(f"     → Falling back to product page")
        return self._extract_same_page(fallback_markdown)

    def should_add_to_crawl_queue(
        self,
        strategy: ExtractionStrategy,
        already_in_queue: set
    ) -> bool:
        """
        Determine if strategy's target URL should be added to crawl queue.
        
        This prevents duplicate crawling when configurator URL will be
        discovered naturally during crawling.
        
        Args:
            strategy: ExtractionStrategy
            already_in_queue: URLs already queued for crawling
            
        Returns:
            True if should explicitly add to queue
        """
        # No URL to add
        if not strategy.target_url:
            return False
        
        # Already queued
        if strategy.target_url in already_in_queue:
            return False
        
        # External URLs should be added (won't be discovered by crawler)
        if strategy.strategy_type == "external_url":
            return True
        
        # Embedded URLs might be discovered naturally
        # Only add if high confidence and not in queue
        if strategy.strategy_type == "embedded_url":
            if strategy.confidence >= 0.7:
                return True
        
        return False


# -------------------------------------------------------------------
# Deduplication Helper (RESTORED)
# -------------------------------------------------------------------

class DeduplicationHelper:
    """
    Helps deduplicate URLs and content during crawling/scraping.
    
    Prevents:
    1. Crawling same configurator URL twice
    2. Fetching already-cached pages
    3. Scraping duplicate product pages
    """
    
    def __init__(self):
        self.visited_urls: set = set()
        self.product_urls: set = set()
        self.configurator_urls: set = set()
        self.url_to_product_map: Dict[str, str] = {}  # config URL -> product URL
    
    def mark_visited(self, url: str, page_type: str):
        """Mark URL as visited with its type."""
        self.visited_urls.add(url)
        
        if page_type in ["product", "customization"]:
            self.product_urls.add(url)
        
        if page_type == "customization":
            self.configurator_urls.add(url)
    
    def link_configurator_to_product(self, config_url: str, product_url: str):
        """Link a configurator URL to its parent product."""
        self.url_to_product_map[config_url] = product_url
    
    def is_duplicate_product(self, url: str) -> bool:
        """Check if this product URL is a duplicate."""
        # Already scraped as product
        if url in self.product_urls:
            return True
        
        # This is a configurator that belongs to an already-scraped product
        if url in self.configurator_urls:
            return True
        
        return False
    
    def get_parent_product(self, config_url: str) -> Optional[str]:
        """Get the parent product URL for a configurator URL."""
        return self.url_to_product_map.get(config_url)
    
    def should_scrape(self, url: str, page_classification) -> tuple[bool, str]:
        """
        Determine if URL should be scraped for product details.
        
        Returns:
            (should_scrape, reason)
        """
        # Skip if already scraped
        if self.is_duplicate_product(url):
            parent = self.get_parent_product(url)
            if parent:
                return False, f"Configurator for already-scraped product: {parent}"
            return False, "Already scraped"
        
        # Scrape product pages
        if page_classification.page_type == "product":
            return True, "Product page"
        
        # Scrape standalone customization pages
        if page_classification.page_type == "customization":
            # Check if this is linked to a product we already have
            if url in self.url_to_product_map:
                return False, "Already scraped as part of product"
            return True, "Standalone customization page"
        
        # Skip others
        return False, f"Not a product page (type: {page_classification.page_type})"
    
    def print_stats(self):
        """Print deduplication statistics."""
        print(f"\n{'='*80}")
        print("DEDUPLICATION STATISTICS")
        print(f"{'='*80}")
        print(f"Total URLs visited: {len(self.visited_urls)}")
        print(f"Product pages: {len(self.product_urls)}")
        print(f"Configurator pages: {len(self.configurator_urls)}")
        print(f"Linked configurators: {len(self.url_to_product_map)}")
        
        if self.url_to_product_map:
            print(f"\nConfigurator→Product Links:")
            for config_url, product_url in list(self.url_to_product_map.items())[:5]:
                print(f"  {config_url}")
                print(f"    → {product_url}")
            if len(self.url_to_product_map) > 5:
                print(f"  ... and {len(self.url_to_product_map) - 5} more")
        
        print(f"{'='*80}\n")