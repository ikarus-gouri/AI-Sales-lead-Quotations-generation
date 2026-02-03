"""Balanced page classifier - combines lenient and strict approaches.

This classifier offers configurable strictness levels:
- LENIENT: Prefer recall (catch all products, some false positives)
- BALANCED: Good precision and recall (recommended)
- STRICT: Prefer precision (clean results, may miss some products)
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum


class StrictnessLevel(Enum):
    """Classification strictness levels."""
    LENIENT = "lenient"
    BALANCED = "balanced"
    STRICT = "strict"


@dataclass
class ClassificationResult:
    """Complete classification result with reasoning."""
    is_product: bool
    confidence: float
    page_type: str  # "product", "category", "blog", "other"
    strictness_used: str
    scores: Dict[str, float] = field(default_factory=dict)
    signals: Dict[str, any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)


class BalancedClassifier:
    """
    Balanced classifier with configurable strictness.
    
    Combines:
    1. Simple keyword scoring (lenient approach)
    2. Content validation (strict approach)
    3. URL pattern analysis
    4. Configurable thresholds
    
    Usage:
        # Lenient mode
        classifier = BalancedClassifier(strictness=StrictnessLevel.LENIENT)
        
        # Balanced mode (recommended)
        classifier = BalancedClassifier(strictness=StrictnessLevel.BALANCED)
        
        # Strict mode
        classifier = BalancedClassifier(strictness=StrictnessLevel.STRICT)
    """
    
    def __init__(self, strictness: StrictnessLevel = StrictnessLevel.BALANCED):
        """
        Initialize balanced classifier.
        
        Args:
            strictness: Classification strictness level
        """
        self.strictness = strictness
        self._setup_patterns()
        self._setup_thresholds()
    
    def _setup_patterns(self):
        """Setup all detection patterns."""
        
        # Product keywords (from lenient approach)
        self.product_keywords = [
            'price', 'dimensions', 'materials', 'features',
            'specifications', 'size', 'capacity', 'finish',
            'color', 'style', 'model', 'product', 'sku',
            'shipping', 'delivery', 'warranty', 'customize',
            'weight', 'height', 'width', 'depth', 'length'
        ]
        
        # Customization indicators
        self.customization_keywords = [
            'customize', 'customization', 'choose your',
            'select your', 'options:', 'add-ons', 'upgrades',
            'configuration', 'personalize', 'build your',
            'design your', 'pick your', 'select', 'choose'
        ]
        
        # Price patterns (from strict approach)
        self.price_patterns = [
            r'base\s+price[:\s]*\$[\d,]+',
            r'starting\s+at[:\s]*\$[\d,]+',
            r'price[:\s]*\$[\d,]+',
            r'from\s+\$[\d,]+',
            r'\$[\d,]+(?:\.\d{2})?'
        ]
        
        # Blog/article indicators (from strict approach)
        self.blog_keywords = [
            'published', 'posted on', 'author:', 'written by',
            'tags:', 'categories:', 'read more', 'share this',
            'continue reading', 'related posts', 'comments',
            'blog post', 'article by'
        ]
        
        # Article structure indicators
        self.article_structure = [
            r'introduction\n',
            r'conclusion\n',
            r'table of contents',
            r'references\n',
            r'further reading'
        ]
        
        # Product CTAs
        self.product_ctas = [
            'add to cart', 'buy now', 'get a quote',
            'request quote', 'contact for price',
            'purchase', 'order now', 'shop now',
            'inquire now', 'request inquiry'
        ]
        
        # URL patterns
        self.product_url_patterns = [
            r'/product[s]?/',
            r'/shop/',
            r'/item[s]?/',
            r'/p/',
            r'/buy/',
        ]
        
        self.blog_url_patterns = [
            r'/blog/',
            r'/news/',
            r'/article[s]?/',
            r'/post[s]?/',
        ]
        
        self.category_url_patterns = [
            r'/categor(?:y|ies)/',
            r'/collection[s]?/',
            r'/all-products',
            r'/shop/?$',
        ]
    
    def _setup_thresholds(self):
        """Setup thresholds based on strictness level."""
        
        if self.strictness == StrictnessLevel.LENIENT:
            self.PRODUCT_THRESHOLD = 3.0
            self.BLOG_PENALTY_THRESHOLD = 3
            self.CONTENT_SIGNAL_REQUIREMENT = 1
            self.KEYWORD_WEIGHT = 1.0
            self.PRICE_WEIGHT = 2.0
            self.STRUCTURE_WEIGHT = 2.0
            
        elif self.strictness == StrictnessLevel.BALANCED:
            self.PRODUCT_THRESHOLD = 5.0
            self.BLOG_PENALTY_THRESHOLD = 2
            self.CONTENT_SIGNAL_REQUIREMENT = 2
            self.KEYWORD_WEIGHT = 0.8
            self.PRICE_WEIGHT = 2.5
            self.STRUCTURE_WEIGHT = 2.0
            
        else:  # STRICT
            self.PRODUCT_THRESHOLD = 7.0
            self.BLOG_PENALTY_THRESHOLD = 1
            self.CONTENT_SIGNAL_REQUIREMENT = 3
            self.KEYWORD_WEIGHT = 0.5
            self.PRICE_WEIGHT = 3.0
            self.STRUCTURE_WEIGHT = 2.5
    
    def classify(self, url: str, markdown: str) -> ClassificationResult:
        """
        Classify page with detailed reasoning.
        
        Args:
            url: Page URL
            markdown: Page content
            
        Returns:
            Complete ClassificationResult
        """
        result = ClassificationResult(
            is_product=False,
            confidence=0.0,
            page_type="other",
            strictness_used=self.strictness.value
        )
        
        url_lower = url.lower()
        markdown_lower = markdown.lower()
        
        # Phase 1: Quick rejection filters
        if len(markdown) < 200:
            result.reasons.append("Content too short")
            return result
        
        # Phase 2: Check for obvious non-products (strict blocking)
        if self._is_obvious_non_product(url_lower, markdown_lower, result):
            return result
        
        # Phase 3: Scoring system (combines lenient + strict)
        score = 0.0
        
        # URL analysis
        url_score, url_signals = self._score_url(url_lower)
        score += url_score
        result.signals.update(url_signals)
        
        # Keyword analysis (lenient approach)
        keyword_score, keyword_signals = self._score_keywords(markdown_lower)
        score += keyword_score
        result.signals.update(keyword_signals)
        
        # Price analysis (strict approach)
        price_score, price_signals = self._score_prices(markdown)
        score += price_score
        result.signals.update(price_signals)
        
        # Structure analysis (strict approach)
        structure_score, structure_signals = self._score_structure(markdown, markdown_lower)
        score += structure_score
        result.signals.update(structure_signals)
        
        # CTA analysis
        cta_score, cta_signals = self._score_ctas(markdown_lower)
        score += cta_score
        result.signals.update(cta_signals)
        
        # Blog penalty (strict blocking)
        blog_penalty, blog_signals = self._check_blog_indicators(markdown_lower)
        score -= blog_penalty
        result.signals.update(blog_signals)
        
        # Phase 4: Make decision
        result.scores['total'] = score
        result.confidence = min(max(score / 15.0, 0.0), 1.0)
        
        # Determine page type
        if score >= self.PRODUCT_THRESHOLD:
            result.is_product = True
            result.page_type = "product"
        elif blog_penalty >= self.BLOG_PENALTY_THRESHOLD:
            result.page_type = "blog"
        elif url_signals.get('is_category_url', False):
            result.page_type = "category"
        else:
            result.page_type = "other"
        
        # Build reasoning
        self._build_reasoning(result)
        
        return result
    
    def _is_obvious_non_product(
        self, 
        url_lower: str, 
        markdown_lower: str,
        result: ClassificationResult
    ) -> bool:
        """Check for obvious non-product pages."""
        
        # Check URL patterns
        non_product_patterns = [
            r'/about', r'/contact', r'/cart', r'/checkout',
            r'/account', r'/login', r'/register', r'/privacy',
            r'/terms', r'/faq', r'/help', r'/support'
        ]
        
        for pattern in non_product_patterns:
            if re.search(pattern, url_lower):
                result.reasons.append(f"Non-product URL pattern: {pattern}")
                result.page_type = "other"
                return True
        
        return False
    
    def _score_url(self, url_lower: str) -> Tuple[float, Dict]:
        """Score URL patterns."""
        score = 0.0
        signals = {}
        
        # Product URL patterns
        for pattern in self.product_url_patterns:
            if re.search(pattern, url_lower):
                score += 3.0
                signals['product_url'] = True
                break
        
        # Category URL patterns
        for pattern in self.category_url_patterns:
            if re.search(pattern, url_lower):
                signals['is_category_url'] = True
                break
        
        # Blog URL patterns (negative signal)
        for pattern in self.blog_url_patterns:
            if re.search(pattern, url_lower):
                score -= 5.0
                signals['blog_url'] = True
                break
        
        signals['url_score'] = score
        return score, signals
    
    def _score_keywords(self, markdown_lower: str) -> Tuple[float, Dict]:
        """Score product keywords (lenient approach)."""
        
        # Count product keywords
        keyword_count = sum(1 for kw in self.product_keywords if kw in markdown_lower)
        
        # Count customization keywords
        custom_count = sum(1 for kw in self.customization_keywords if kw in markdown_lower)
        
        score = (keyword_count * self.KEYWORD_WEIGHT) + (custom_count * 0.5)
        
        signals = {
            'product_keyword_count': keyword_count,
            'customization_keyword_count': custom_count,
            'keyword_score': score
        }
        
        return score, signals
    
    def _score_prices(self, markdown: str) -> Tuple[float, Dict]:
        """Score price mentions (strict approach)."""
        score = 0.0
        signals = {}
        
        # Find all prices
        all_prices = []
        for pattern in self.price_patterns:
            matches = re.findall(pattern, markdown, re.IGNORECASE)
            all_prices.extend(matches)
        
        price_count = len(all_prices)
        signals['price_count'] = price_count
        
        # Base price detection
        if re.search(r'base\s+price', markdown, re.IGNORECASE):
            score += self.PRICE_WEIGHT
            signals['has_base_price'] = True
        
        # Multiple prices suggest customization
        if price_count >= 5:
            score += self.PRICE_WEIGHT
            signals['has_price_variants'] = True
        elif price_count >= 3:
            score += self.PRICE_WEIGHT * 0.7
        elif price_count >= 1:
            score += self.PRICE_WEIGHT * 0.4
        
        signals['price_score'] = score
        return score, signals
    
    def _score_structure(self, markdown: str, markdown_lower: str) -> Tuple[float, Dict]:
        """Score product structure (strict approach)."""
        score = 0.0
        signals = {}
        
        # Check for option categories (e.g., "Wood Type:", "Colors:")
        category_pattern = re.compile(r'^([A-Z][^:\n]{2,40}):\s*$', re.MULTILINE)
        categories = category_pattern.findall(markdown)
        
        category_count = len(categories)
        signals['option_categories'] = category_count
        
        if category_count >= 4:
            score += self.STRUCTURE_WEIGHT * 1.5
        elif category_count >= 3:
            score += self.STRUCTURE_WEIGHT
        elif category_count >= 2:
            score += self.STRUCTURE_WEIGHT * 0.7
        
        # Check for checkboxes/options
        checkbox_count = len(re.findall(r'-\s*\[[x ]\]', markdown))
        signals['checkbox_count'] = checkbox_count
        
        if checkbox_count >= 5:
            score += 1.5
            signals['has_option_lists'] = True
        elif checkbox_count >= 3:
            score += 1.0
        
        # Check for product-like sections
        product_sections = ['features:', 'specifications:', 'details:', 'materials:']
        section_count = sum(1 for section in product_sections if section in markdown_lower)
        signals['product_section_count'] = section_count
        
        if section_count >= 2:
            score += 1.5
        
        signals['structure_score'] = score
        return score, signals
    
    def _score_ctas(self, markdown_lower: str) -> Tuple[float, Dict]:
        """Score call-to-action elements."""
        score = 0.0
        signals = {}
        
        cta_count = sum(1 for cta in self.product_ctas if cta in markdown_lower)
        signals['cta_count'] = cta_count
        
        if cta_count >= 2:
            score += 2.0
            signals['has_strong_cta'] = True
        elif cta_count >= 1:
            score += 1.0
            signals['has_cta'] = True
        
        signals['cta_score'] = score
        return score, signals
    
    def _check_blog_indicators(self, markdown_lower: str) -> Tuple[float, Dict]:
        """Check for blog/article indicators."""
        penalty = 0.0
        signals = {}
        
        # Count blog keywords
        blog_count = sum(1 for kw in self.blog_keywords if kw in markdown_lower)
        signals['blog_indicator_count'] = blog_count
        
        # Strong blog indicators
        if blog_count >= 3:
            penalty = 10.0
            signals['strong_blog_indicators'] = True
        elif blog_count >= 2:
            penalty = 5.0
            signals['moderate_blog_indicators'] = True
        elif blog_count >= 1:
            penalty = 2.0
        
        # Check article structure
        article_count = sum(
            1 for pattern in self.article_structure 
            if re.search(pattern, markdown_lower)
        )
        signals['article_structure_count'] = article_count
        
        if article_count >= 2:
            penalty += 5.0
            signals['has_article_structure'] = True
        
        signals['blog_penalty'] = penalty
        return penalty, signals
    
    def _build_reasoning(self, result: ClassificationResult):
        """Build human-readable reasoning."""
        
        # URL signals
        if result.signals.get('product_url'):
            result.reasons.append("Product URL pattern detected")
        if result.signals.get('blog_url'):
            result.reasons.append("Blog URL pattern detected")
        
        # Keyword signals
        kw_count = result.signals.get('product_keyword_count', 0)
        if kw_count > 0:
            result.reasons.append(f"Found {kw_count} product keywords")
        
        # Price signals
        if result.signals.get('has_base_price'):
            result.reasons.append("Base price found")
        if result.signals.get('has_price_variants'):
            result.reasons.append(f"Multiple prices found ({result.signals['price_count']})")
        
        # Structure signals
        cat_count = result.signals.get('option_categories', 0)
        if cat_count >= 2:
            result.reasons.append(f"Found {cat_count} option categories")
        
        # Blog signals
        if result.signals.get('strong_blog_indicators'):
            result.reasons.append("Strong blog indicators detected")
        
        # Final decision
        if result.is_product:
            result.reasons.append(f"PRODUCT (score: {result.scores['total']:.1f}, threshold: {self.PRODUCT_THRESHOLD})")
        else:
            result.reasons.append(f"NOT PRODUCT (score: {result.scores['total']:.1f}, threshold: {self.PRODUCT_THRESHOLD})")
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Simple interface for compatibility.
        
        Args:
            url: Page URL
            markdown: Page content
            
        Returns:
            True if product page
        """
        result = self.classify(url, markdown)
        return result.is_product
    
    def set_strictness(self, strictness: StrictnessLevel):
        """
        Change strictness level.
        
        Args:
            strictness: New strictness level
        """
        self.strictness = strictness
        self._setup_thresholds()


# Convenience functions for quick usage
def create_lenient_classifier():
    """Create a lenient classifier (high recall)."""
    return BalancedClassifier(strictness=StrictnessLevel.LENIENT)


def create_balanced_classifier():
    """Create a balanced classifier (recommended)."""
    return BalancedClassifier(strictness=StrictnessLevel.BALANCED)


def create_strict_classifier():
    """Create a strict classifier (high precision)."""
    return BalancedClassifier(strictness=StrictnessLevel.STRICT)