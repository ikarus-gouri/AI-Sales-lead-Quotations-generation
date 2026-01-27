"""Unified page classification that distinguishes product vs customization pages."""

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
    5. Content/blog pages
    """
    
    def __init__(self, configurator_detector):
        """
        Initialize with configurator detector.
        
        Args:
            configurator_detector: ConfiguratorDetector instance
        """
        self.configurator_detector = configurator_detector
        
        # Try to import content validator
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
        
        Logic:
        1. Check if it's a blog/content page (BLOCKER)
        2. High customization signals = CUSTOMIZATION page
        3. Has product info + customization = PRODUCT page
        4. Has product info only = PRODUCT page
        5. Otherwise = CATEGORY page
        """
        url_lower = url.lower()
        markdown_lower = markdown.lower()
        
        # Content validation gate
        if self.use_content_validation:
            validated_type, validation_confidence, signals = self.content_validator.score(
                url=url,
                markdown=markdown
            )
            
            # If content page detected, return immediately
            if validated_type == "content":
                return "content"
            
            # High confidence product
            if validated_type == "product" and validation_confidence >= 0.6:
                if self._is_customization_focused(url_lower, config_info):
                    return "customization"
                return "product"
        
        # Check URL for customization keywords
        customization_url_keywords = [
            'customize', 'customization', 'configurator', 'configure',
            'inquiry', 'enquiry', 'quote', 'build-your', 'design-your'
        ]
        
        url_is_customization = any(kw in url_lower for kw in customization_url_keywords)
        
        # Strong customization signals
        strong_customization_signals = (
            config_info['confidence'] >= self.CUSTOMIZATION_PAGE_THRESHOLD and
            config_info['signals'].get('content_score', 0) >= 3
        )
        
        # Check for product indicators
        has_product_indicators = self._has_product_indicators(markdown_lower)
        
        # Decision tree
        if url_is_customization and strong_customization_signals:
            return "customization"
        elif has_product_indicators:
            return "product"
        elif strong_customization_signals:
            return "customization"
        elif config_info['confidence'] >= self.PRODUCT_PAGE_THRESHOLD:
            return "product"
        else:
            return "category"
    
    def _is_customization_focused(self, url_lower: str, config_info: Dict) -> bool:
        """Check if page is customization-focused."""
        customization_keywords = [
            'customize', 'customization', 'configurator', 'configure',
            'inquiry', 'quote', 'build-your', 'design-your'
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
            'base price', 'starting at', 'price:', 'dimensions:',
            'specifications:', 'capacity:', 'material:',
            'add to cart', 'buy now', 'contact for price'
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
            return "same_page", None
        
        # Normalize URLs for comparison
        from urllib.parse import urlparse
        current_domain = urlparse(current_url).netloc
        config_domain = urlparse(config_url).netloc
        
        if current_domain != config_domain:
            return "external_url", config_url
        else:
            return "embedded_url", config_url
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Legacy compatibility method.
        Returns True for any page that has product content.
        """
        classification = self.classify(url, markdown)
        return classification.is_product_page()