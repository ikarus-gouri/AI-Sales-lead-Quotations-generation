"""Content validation - hard gate before PRODUCT classification.

This is the discipline layer that prevents blogs/articles from being 
misclassified as products based on URL shape alone.

File location: src/classifiers/content_validator.py
"""

import re
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class ContentSignals:
    """Signals detected in page content."""
    has_price: bool = False
    has_customization: bool = False
    has_product_cta: bool = False
    has_option_lists: bool = False
    has_blog_indicators: bool = False
    has_article_structure: bool = False
    signal_count: int = 0
    
    def is_product(self) -> bool:
        """Product requires ≥2 product signals AND no strong blog signals."""
        return self.signal_count >= 2 and not self.has_blog_indicators


class ContentValidator:
    """
    Hard gate that validates page content before allowing PRODUCT classification.
    
    Purpose: Prevent blogs/articles from being treated as products.
    
    Decision rule:
    - ≥2 product signals + no blog signals = PRODUCT ✓
    - Blog signals detected = CONTENT ✗
    - <2 product signals = UNKNOWN (needs full classification)
    """
    
    def __init__(self):
        # Product signals
        self.price_patterns = [
            r'base price[:\s]+\$[\d,]+',
            r'starting at[:\s]+\$[\d,]+',
            r'price[:\s]+\$[\d,]+',
            r'from\s+\$[\d,]+'
        ]
        
        self.customization_keywords = [
            'customize', 'customization', 'choose your',
            'select your', 'options:', 'add-ons',
            'upgrades', 'configuration', 'personalize'
        ]
        
        self.product_ctas = [
            'request a quote', 'get a quote', 'contact for price',
            'add to cart', 'buy now', 'request inquiry',
            'start designing', 'build your', 'configure now'
        ]
        
        self.option_list_indicators = [
            r'-\s*\[.\]\s+',  # Checkbox lists
            r'(?:color|size|material|finish|wood type):\s*\n(?:\s*[-*•])',
            r'available (?:colors|finishes|options|sizes):'
        ]
        
        # Blog/content signals (BLOCKERS)
        self.blog_indicators = [
            r'published:?\s+\d{4}',
            r'posted on',
            r'by\s+[A-Z][a-z]+\s+[A-Z][a-z]+',  # Author name
            r'read more',
            r'continue reading',
            r'share this (?:post|article)',
            r'comments?\s*\(\d+\)',
            r'tags?:',
            r'categories?:'
        ]
        
        self.article_structure_indicators = [
            r'introduction\n',
            r'conclusion\n',
            r'table of contents',
            r'references\n',
            r'further reading'
        ]
    
    def validate_product_page(self, markdown: str) -> ContentSignals:
        """
        Validate if page content supports PRODUCT classification.
        
        Args:
            markdown: Page content
            
        Returns:
            ContentSignals with validation results
        """
        markdown_lower = markdown.lower()
        signals = ContentSignals()
        
        # Check BLOCKERS first (blog/article indicators)
        signals.has_blog_indicators = self._detect_blog_indicators(markdown_lower)
        signals.has_article_structure = self._detect_article_structure(markdown_lower)
        
        # If blog detected, skip product signal checks
        if signals.has_blog_indicators or signals.has_article_structure:
            return signals
        
        # Check product signals
        signals.has_price = self._detect_price(markdown_lower)
        signals.has_customization = self._detect_customization(markdown_lower)
        signals.has_product_cta = self._detect_product_cta(markdown_lower)
        signals.has_option_lists = self._detect_option_lists(markdown)
        
        # Count signals
        signals.signal_count = sum([
            signals.has_price,
            signals.has_customization,
            signals.has_product_cta,
            signals.has_option_lists
        ])
        
        return signals
    
    def _detect_price(self, markdown_lower: str) -> bool:
        """Detect price mentions."""
        for pattern in self.price_patterns:
            if re.search(pattern, markdown_lower):
                return True
        return False
    
    def _detect_customization(self, markdown_lower: str) -> bool:
        """Detect customization keywords."""
        count = sum(1 for kw in self.customization_keywords if kw in markdown_lower)
        return count >= 2  # Require multiple mentions
    
    def _detect_product_cta(self, markdown_lower: str) -> bool:
        """Detect product call-to-action."""
        return any(cta in markdown_lower for cta in self.product_ctas)
    
    def _detect_option_lists(self, markdown: str) -> bool:
        """Detect structured option lists (checkboxes, categorized options)."""
        for pattern in self.option_list_indicators:
            if re.search(pattern, markdown, re.IGNORECASE):
                return True
        return False
    
    def _detect_blog_indicators(self, markdown_lower: str) -> bool:
        """Detect blog/article indicators (BLOCKERS)."""
        for pattern in self.blog_indicators:
            if re.search(pattern, markdown_lower):
                return True
        return False
    
    def _detect_article_structure(self, markdown_lower: str) -> bool:
        """Detect article structure indicators."""
        count = sum(
            1 for pattern in self.article_structure_indicators
            if re.search(pattern, markdown_lower)
        )
        return count >= 2  # Multiple structural indicators
    
    def get_page_type_from_signals(self, signals: ContentSignals) -> str:
        """
        Determine page type from content signals.
        
        Returns:
            "product", "content", or "unknown"
        """
        if signals.has_blog_indicators or signals.has_article_structure:
            return "content"
        
        if signals.signal_count >= 2:
            return "product"
        
        return "unknown"
    
    def explain_decision(self, signals: ContentSignals) -> str:
        """Generate human-readable explanation of classification."""
        if signals.has_blog_indicators:
            return "CONTENT - blog/article indicators detected"
        
        if signals.has_article_structure:
            return "CONTENT - article structure detected"
        
        if signals.signal_count >= 2:
            active_signals = []
            if signals.has_price:
                active_signals.append("price")
            if signals.has_customization:
                active_signals.append("customization")
            if signals.has_product_cta:
                active_signals.append("CTA")
            if signals.has_option_lists:
                active_signals.append("option_lists")
            
            return f"PRODUCT - {signals.signal_count} signals: {', '.join(active_signals)}"
        
        return f"UNKNOWN - only {signals.signal_count} product signals"


class PageTypeScorer:
    """
    Scoring-based page type classifier.
    
    Combines:
    1. URL pattern confidence (boost, not decision)
    2. Content signals (primary decision maker)
    3. Explicit thresholds
    
    Usage:
        scorer = PageTypeScorer()
        page_type, confidence = scorer.score(url, markdown, url_pattern_type)
    """
    
    def __init__(self):
        self.validator = ContentValidator()
        
        # Thresholds
        self.PRODUCT_THRESHOLD = 0.6
        self.CONTENT_THRESHOLD = 0.7
    
    def score(
        self,
        url: str,
        markdown: str,
        url_pattern_type: str = None,
        url_pattern_confidence: float = 0.0
    ) -> tuple[str, float, ContentSignals]:
        """
        Score page and determine type.
        
        Args:
            url: Page URL
            markdown: Page content
            url_pattern_type: Predicted type from URL patterns (optional)
            url_pattern_confidence: Confidence from URL patterns (optional)
            
        Returns:
            (page_type, confidence, signals)
        """
        # Get content signals
        signals = self.validator.validate_product_page(markdown)
        
        # Start with content-based score
        content_score = 0.0
        
        # Blog/content indicators are BLOCKING
        if signals.has_blog_indicators:
            return ("content", 0.9, signals)
        
        if signals.has_article_structure:
            return ("content", 0.85, signals)
        
        # Product signal scoring
        signal_weights = {
            'price': 0.3,
            'customization': 0.25,
            'cta': 0.25,
            'options': 0.2
        }
        
        if signals.has_price:
            content_score += signal_weights['price']
        if signals.has_customization:
            content_score += signal_weights['customization']
        if signals.has_product_cta:
            content_score += signal_weights['cta']
        if signals.has_option_lists:
            content_score += signal_weights['options']
        
        # URL pattern adds boost (max +0.2)
        url_boost = 0.0
        if url_pattern_type == "PRODUCT":
            url_boost = min(url_pattern_confidence * 0.2, 0.2)
        
        # Combined score
        total_score = content_score + url_boost
        
        # Decide type
        if total_score >= self.PRODUCT_THRESHOLD:
            return ("product", total_score, signals)
        elif total_score >= 0.3:
            return ("unknown", total_score, signals)
        else:
            return ("category", total_score, signals)
    
    def should_extract_product(
        self,
        page_type: str,
        confidence: float,
        signals: ContentSignals
    ) -> tuple[bool, str]:
        """
        Decide if we should run product extraction.
        
        Returns:
            (should_extract, reason)
        """
        if page_type == "content":
            return (False, "Content page - no extraction")
        
        if page_type == "product" and confidence >= self.PRODUCT_THRESHOLD:
            return (True, f"Product page ({confidence:.0%} confidence)")
        
        if page_type == "unknown" and signals.signal_count >= 1:
            return (True, "Unknown but has product signals - try extraction")
        
        return (False, f"Low confidence ({confidence:.0%})")


# Quick integration example
def integrate_with_existing_classifier(
    url: str,
    markdown: str,
    old_page_type: str,
    old_confidence: float
) -> tuple[str, float]:
    """
    Drop-in integration with existing UnifiedPageClassifier.
    
    Call this AFTER URL routing but BEFORE accepting PRODUCT classification.
    
    Args:
        url: Page URL
        markdown: Page content
        old_page_type: Type from URL patterns
        old_confidence: Confidence from URL patterns
        
    Returns:
        (corrected_page_type, corrected_confidence)
    """
    scorer = PageTypeScorer()
    
    new_type, new_confidence, signals = scorer.score(
        url=url,
        markdown=markdown,
        url_pattern_type=old_page_type.upper(),
        url_pattern_confidence=old_confidence
    )
    
    # Log if we're correcting
    if old_page_type != new_type and old_page_type == "product":
        print(f"  🔄 Corrected: {old_page_type} ({old_confidence:.0%}) → {new_type} ({new_confidence:.0%})")
        print(f"     Reason: {scorer.validator.explain_decision(signals)}")
    
    return (new_type, new_confidence)