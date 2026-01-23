"""Unified page classification that distinguishes product vs customization pages.

MODIFIED: Added content validation to prevent blogs from being classified as products.
"""

from typing import Dict, Tuple
from dataclasses import dataclass
from .base_classifier import BaseClassifier


@dataclass
class PageClassification:
    """Complete page classification result."""
    page_type: str  # "product", "customization", "category", "content", "other"
    confidence: float
    has_customization: bool
    customization_location: str  # "same_page", "external_url", "embedded_url", "none"
    customization_url: str = None
    signals: dict = None
    
    def is_product_page(self) -> bool:
        """Check if this is any type of product page."""
        return self.page_type in ["product", "customization"]


class UnifiedPageClassifier(BaseClassifier):
    """
    Unified classifier that properly distinguishes:
    1. Product page with embedded customization (same page)
    2. Product page linking to separate customization page
    3. Standalone customization page
    4. Category/listing pages
    5. Content/blog pages (NEW - prevents false positives)
    
    This replaces the confusion between is_product_page() and configurator detection.
    """
    
    def __init__(self, configurator_detector):
        """
        Initialize with configurator detector.
        
        Args:
            configurator_detector: ConfiguratorDetector instance
        """
        self.configurator_detector = configurator_detector
        
        # NEW: Import content validator
        try:
            from .content_validator import PageTypeScorer
            self.content_validator = PageTypeScorer()
            self.use_content_validation = True
        except ImportError:
            print("⚠️  Content validator not found - running without content filtering")
            self.content_validator = None
            self.use_content_validation = False
        
        # Thresholds
        self.CUSTOMIZATION_PAGE_THRESHOLD = 0.6
        self.PRODUCT_PAGE_THRESHOLD = 0.4
    
    def classify(self, url: str, markdown: str) -> PageClassification:
        """
        Comprehensive page classification.
        
        Args:
            url: Page URL
            markdown: Page content
            
        Returns:
            Complete PageClassification with all details
        """
        # Use configurator detector to analyze page
        config_info = self.configurator_detector.has_configurator(url, markdown)
        
        # Determine primary page type
        page_type = self._determine_page_type(url, markdown, config_info)
        
        # Determine customization location
        customization_location, customization_url = self._determine_customization_location(
            url, config_info
        )
        
        return PageClassification(
            page_type=page_type,
            confidence=config_info['confidence'],
            has_customization=config_info['has_configurator'],
            customization_location=customization_location,
            customization_url=customization_url,
            signals=config_info['signals']
        )
    
    def _determine_page_type(
        self, 
        url: str, 
        markdown: str, 
        config_info: Dict
    ) -> str:
        """
        Determine if page is product, customization, content, or category.
        
        NEW: Added content validation gate to prevent blog false positives.
        
        Logic:
        1. GATE: Check if it's a blog/content page (BLOCKER)
        2. High customization signals + customization keywords in URL = CUSTOMIZATION page
        3. Has product info + customization options = PRODUCT page (with embedded custom)
        4. Has product info only = PRODUCT page
        5. Otherwise = CATEGORY page
        """
        url_lower = url.lower()
        markdown_lower = markdown.lower()
        
        # NEW: CONTENT VALIDATION GATE (prevents false positives)
        if self.use_content_validation:
            validated_type, validation_confidence, signals = self.content_validator.score(
                url=url,
                markdown=markdown
            )
            
            # BLOCKER: If content page detected, return immediately
            if validated_type == "content":
                return "content"
            
            # HIGH CONFIDENCE PRODUCT: Trust validation
            if validated_type == "product" and validation_confidence >= 0.6:
                # Still need to check if it's a customization-focused product page
                if self._is_customization_focused(url_lower, config_info):
                    return "customization"
                return "product"
        
        # Original logic continues below (with content pages already filtered out)
        
        # Check if URL strongly suggests customization page
        customization_url_keywords = [
            'customize', 'customization', 'configurator', 'configure',
            'inquiry', 'enquiry', 'quote', 'quotation', 'build-your', 'design-your'
        ]
        
        url_is_customization = any(kw in url_lower for kw in customization_url_keywords)
        
        # Strong customization signals in content
        strong_customization_signals = (
            config_info['confidence'] >= self.CUSTOMIZATION_PAGE_THRESHOLD and
            config_info['signals'].get('content_score', 0) >= 3
        )
        
        # Check for product indicators
        has_product_indicators = self._has_product_indicators(markdown_lower)
        
        # Decision tree
        if url_is_customization and strong_customization_signals:
            # Dedicated customization page
            return "customization"
        
        elif has_product_indicators:
            # Product page (may have embedded customization)
            return "product"
        
        elif strong_customization_signals:
            # Customization-focused but no clear product base
            return "customization"
        
        elif config_info['confidence'] >= self.PRODUCT_PAGE_THRESHOLD:
            # Likely a product page based on signals
            return "product"
        
        else:
            # Default to category
            return "category"
    
    def _is_customization_focused(self, url_lower: str, config_info: Dict) -> bool:
        """Check if page is customization-focused."""
        customization_keywords = [
            'customize', 'customization', 'configurator', 'configure',
            'inquiry', 'enquiry', 'quote', 'quotation', 'build-your', 'design-your'
        ]
        
        url_match = any(kw in url_lower for kw in customization_keywords)
        strong_signals = (
            config_info['confidence'] >= self.CUSTOMIZATION_PAGE_THRESHOLD and
            config_info['signals'].get('content_score', 0) >= 3
        )
        
        return url_match and strong_signals
    
    def _has_product_indicators(self, markdown_lower: str) -> bool:
        """Check if page has core product information."""
        product_indicators = [
            'base price',
            'starting at',
            'price:',
            'dimensions:',
            'specifications:',
            'capacity:',
            'material:',
            'add to cart',
            'buy now',
            'contact for price'
        ]
        
        indicator_count = sum(1 for ind in product_indicators if ind in markdown_lower)
        return indicator_count >= 2
    
    def _determine_customization_location(
        self, 
        current_url: str, 
        config_info: Dict
    ) -> Tuple[str, str]:
        """
        Determine where customization happens.
        
        Returns:
            (location_type, url)
            location_type: "same_page", "external_url", "embedded_url", "none"
        """
        if not config_info['has_configurator']:
            return "none", None
        
        config_url = config_info.get('configurator_url')
        
        if not config_url:
            # Has customization but no separate URL = same page
            return "same_page", None
        
        # Normalize URLs for comparison
        from urllib.parse import urlparse
        current_domain = urlparse(current_url).netloc
        config_domain = urlparse(config_url).netloc
        
        if current_domain != config_domain:
            # Different domain = external
            return "external_url", config_url
        else:
            # Same domain = embedded
            return "embedded_url", config_url
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Legacy compatibility method.
        Returns True for any page that has product content.
        """
        classification = self.classify(url, markdown)
        return classification.is_product_page()


class FastPageRouter:
    """
    Fast router that combines URL patterns with minimal content checks.
    
    Used during crawling to quickly decide:
    1. Should we crawl this URL?
    2. Is this likely a product/customization page?
    3. Should we scrape it in detail?
    """
    
    def __init__(self, url_router, configurator_detector):
        """
        Initialize fast router.
        
        Args:
            url_router: URLRouter with learned patterns
            configurator_detector: ConfiguratorDetector for quick checks
        """
        self.url_router = url_router
        self.configurator_detector = configurator_detector
    
    def quick_classify(self, url: str, markdown: str = None) -> Dict:
        """
        Quick classification using URL patterns first, content second.
        
        Args:
            url: URL to classify
            markdown: Optional content (if already fetched)
            
        Returns:
            {
                'route': str,  # URL router result
                'confidence': float,
                'should_scrape': bool,
                'priority': int
            }
        """
        # First: URL pattern matching (fastest)
        route, url_confidence = self.url_router.route(url)
        
        # High confidence from URL alone
        if url_confidence >= 0.7:
            return {
                'route': route,
                'confidence': url_confidence,
                'should_scrape': route in ['PRODUCT', 'CUSTOMIZATION'],
                'priority': self.url_router.get_priority(url),
                'source': 'url_pattern'
            }
        
        # If we have content, do quick content check
        if markdown:
            # Quick signal check (much faster than full classification)
            quick_signals = self._quick_content_check(url, markdown)
            
            combined_confidence = max(url_confidence, quick_signals['confidence'])
            
            return {
                'route': quick_signals['likely_type'],
                'confidence': combined_confidence,
                'should_scrape': quick_signals['likely_type'] in ['PRODUCT', 'CUSTOMIZATION'],
                'priority': int(combined_confidence * 100),
                'source': 'url_pattern+content'
            }
        
        # Medium confidence - needs full classification
        return {
            'route': route,
            'confidence': url_confidence,
            'should_scrape': route in ['PRODUCT', 'CUSTOMIZATION', 'UNKNOWN'],
            'priority': self.url_router.get_priority(url),
            'source': 'url_pattern_only'
        }
    
    def _quick_content_check(self, url: str, markdown: str) -> Dict:
        """
        Quick content check using limited signals.
        
        Much faster than full configurator detection.
        """
        markdown_lower = markdown.lower()
        
        # Quick keyword counts
        customization_keywords = ['customize', 'choose', 'select', 'options']
        product_keywords = ['price', 'buy', 'specifications', 'dimensions']
        
        custom_score = sum(1 for kw in customization_keywords if kw in markdown_lower)
        product_score = sum(1 for kw in product_keywords if kw in markdown_lower)
        
        # Quick decision
        if custom_score >= 3:
            return {
                'likely_type': 'CUSTOMIZATION',
                'confidence': min(0.6 + (custom_score * 0.05), 0.85)
            }
        elif product_score >= 2:
            return {
                'likely_type': 'PRODUCT',
                'confidence': min(0.5 + (product_score * 0.05), 0.75)
            }
        else:
            return {
                'likely_type': 'CATEGORY',
                'confidence': 0.3
            }
    
    def should_deep_scrape(self, url: str, quick_result: Dict) -> bool:
        """
        Decide if page needs detailed scraping.
        
        Args:
            url: Page URL
            quick_result: Result from quick_classify()
            
        Returns:
            True if should perform detailed product extraction
        """
        # Always scrape high-confidence product/customization pages
        if quick_result['route'] in ['PRODUCT', 'CUSTOMIZATION']:
            if quick_result['confidence'] >= 0.5:
                return True
        
        # Scrape unknowns that might be products
        if quick_result['route'] == 'UNKNOWN':
            return True
        
        return False