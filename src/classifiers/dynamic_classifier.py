"""Smart classifier that uses URL patterns FIRST, then content.

This fixes the issue where product pages with "related products" sections
get misclassified as list pages.

REPLACE: src/classifiers/dynamic_classifier.py
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from .base_classifier import BaseClassifier


@dataclass
class PageClassification:
    """Complete page classification result."""
    
    page_type: str
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    signals: Dict[str, any] = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)
    
    def add_reason(self, reason: str):
        """Add reasoning step."""
        self.reasoning.append(reason)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            'page_type': self.page_type,
            'confidence': self.confidence,
            'scores': self.scores,
            'signals': self.signals,
            'reasoning': self.reasoning
        }


class DynamicPageClassifier(BaseClassifier):
    """
    Smart multi-class page classifier.
    
    Strategy:
    1. Check URL patterns FIRST (high confidence)
    2. Then validate with content patterns
    3. Only rely on content if URL is ambiguous
    
    This prevents product pages with "related products" from being
    misclassified as list pages.
    """
    
    def __init__(self, enable_logging: bool = True):
        """Initialize classifier."""
        self.enable_logging = enable_logging
        self.classification_log: List[Dict] = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile all detection patterns."""
        
        # URL patterns (PRIMARY SIGNALS)
        self.url_patterns = {
            'product_strong': [
                r'/products?/[^/]+/?$',  # /products/item-name
                r'/items?/[^/]+/?$',      # /items/item-name
                r'/p/[^/]+/?$',           # /p/item-name
            ],
            'list_strong': [
                r'/collections?/?$',       # /collections or /collection
                r'/collections?/[^/]+/?$', # /collections/category-name
                r'/categor(?:y|ies)/?',    # /category or /categories
                r'/shop/?$',               # /shop
                r'/all-products?/?',       # /all-products
                r'/products?/?$',          # /products (no specific item)
            ],
            'blog_strong': [
                r'/blog/',
                r'/article/',
                r'/post/',
                r'/news/',
            ]
        }
        
        # Content patterns (SECONDARY SIGNALS)
        self.content_patterns = {
            'product_link': re.compile(
                r'\[([^\]]+)\]\((https?://[^)]*(?:/product|/item|/p/)[^)]*)\)',
                re.IGNORECASE
            ),
            'price': re.compile(r'[\$€£¥₹][\d,]+(?:\.\d{2})?'),
            'price_modifier': re.compile(r'\+\s*[\$€£¥₹][\d,]+(?:\.\d{2})?'),
            'base_price': re.compile(
                r'(?:base\s+)?price[:\s]*[\$€£¥₹]?[\d,]+(?:\.\d{2})?',
                re.IGNORECASE
            ),
            'option_category': re.compile(
                r'^(?:#{2,4}\s+)?([A-Z][^:\n]{2,40}):\s*$',
                re.MULTILINE
            ),
            'pagination': re.compile(
                r'(?:page\s+\d+|next|previous|showing\s+\d+)',
                re.IGNORECASE
            ),
            'view_details': re.compile(
                r'(?:view\s+details?|see\s+more|learn\s+more|shop\s+now)',
                re.IGNORECASE
            ),
            'date_published': re.compile(
                r'(?:published|posted|written)\s+(?:on\s+)?',
                re.IGNORECASE
            ),
        }
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """Legacy method for backward compatibility."""
        result = self.classify(url, markdown)
        
        if self.enable_logging:
            self.classification_log.append({
                'url': url,
                'result': result.to_dict()
            })
        
        return result.page_type == 'product'
    
    def classify(self, url: str, markdown: str) -> PageClassification:
        """
        Classify page with URL-first strategy.
        
        Args:
            url: Page URL
            markdown: Page content
            
        Returns:
            PageClassification
        """
        result = PageClassification(
            page_type='other',
            confidence=0.0,
            scores={
                'product': 0.0,
                'list': 0.0,
                'blog': 0.0,
                'other': 0.0
            },
            signals={}
        )
        
        # ================================================================
        # PHASE 1: URL PATTERN ANALYSIS (PRIMARY)
        # ================================================================
        url_classification = self._classify_by_url(url)
        
        if url_classification['confidence'] >= 0.8:
            # High confidence from URL alone - trust it!
            result.page_type = url_classification['type']
            result.confidence = url_classification['confidence']
            result.add_reason(f"Strong URL pattern: {url_classification['pattern']}")
            result.signals['url_match'] = url_classification['pattern']
            
            # Still do quick content validation for sanity check
            content_validation = self._quick_content_check(markdown, url_classification['type'])
            if content_validation['confirms']:
                result.add_reason(f"Content confirms URL classification")
            else:
                result.add_reason(f"Warning: Content doesn't strongly confirm URL")
            
            return result
        
        # ================================================================
        # PHASE 2: MEDIUM CONFIDENCE URL + CONTENT ANALYSIS
        # ================================================================
        if url_classification['confidence'] >= 0.5:
            # Medium confidence from URL - validate with content
            result.add_reason(f"Medium URL pattern: {url_classification['pattern']}")
            
            # Get detailed content analysis
            if url_classification['type'] == 'product':
                score, signals = self._detect_product_page(url, markdown)
                result.scores['product'] = score
                result.signals['product'] = signals
                
                if score >= 0.3:
                    result.page_type = 'product'
                    result.confidence = min(url_classification['confidence'] + score, 1.0)
                    result.add_reason(f"URL + content confirm product page")
                    return result
            
            elif url_classification['type'] == 'list':
                score, signals = self._detect_list_page(url, markdown)
                result.scores['list'] = score
                result.signals['list'] = signals
                
                if score >= 0.3:
                    result.page_type = 'list'
                    result.confidence = min(url_classification['confidence'] + score, 1.0)
                    result.add_reason(f"URL + content confirm list page")
                    return result
        
        # ================================================================
        # PHASE 3: LOW CONFIDENCE URL - RELY ON CONTENT
        # ================================================================
        result.add_reason(f"No strong URL pattern, analyzing content...")
        
        # Full content analysis
        blog_score, blog_signals = self._detect_blog_page(url, markdown)
        list_score, list_signals = self._detect_list_page(url, markdown)
        product_score, product_signals = self._detect_product_page(url, markdown)
        
        result.scores['blog'] = blog_score
        result.scores['list'] = list_score
        result.scores['product'] = product_score
        result.signals['blog'] = blog_signals
        result.signals['list'] = list_signals
        result.signals['product'] = product_signals
        
        # Determine winner
        max_score = max(result.scores.values())
        
        if max_score < 0.3:
            result.page_type = 'other'
            result.confidence = 0.2
            result.add_reason("No strong signals detected")
        elif blog_score == max_score:
            result.page_type = 'blog'
            result.confidence = blog_score
            result.add_reason(f"Blog signals detected")
        elif list_score == max_score:
            result.page_type = 'list'
            result.confidence = list_score
            result.add_reason(f"List signals detected")
        elif product_score == max_score:
            result.page_type = 'product'
            result.confidence = product_score
            result.add_reason(f"Product signals detected")
        
        return result
    
    def _classify_by_url(self, url: str) -> Dict:
        """
        Classify based on URL pattern alone.
        
        Returns:
            {
                'type': 'product'|'list'|'blog'|'unknown',
                'confidence': 0.0-1.0,
                'pattern': 'matched_pattern'
            }
        """
        url_lower = url.lower()
        
        # Check strong product patterns
        for pattern in self.url_patterns['product_strong']:
            if re.search(pattern, url_lower):
                return {
                    'type': 'product',
                    'confidence': 0.9,
                    'pattern': pattern
                }
        
        # Check strong list patterns
        for pattern in self.url_patterns['list_strong']:
            if re.search(pattern, url_lower):
                return {
                    'type': 'list',
                    'confidence': 0.9,
                    'pattern': pattern
                }
        
        # Check strong blog patterns
        for pattern in self.url_patterns['blog_strong']:
            if re.search(pattern, url_lower):
                return {
                    'type': 'blog',
                    'confidence': 0.9,
                    'pattern': pattern
                }
        
        # No strong pattern
        return {
            'type': 'unknown',
            'confidence': 0.0,
            'pattern': 'none'
        }
    
    def _quick_content_check(self, markdown: str, expected_type: str) -> Dict:
        """Quick sanity check that content matches expected type."""
        
        if expected_type == 'product':
            # Check for product indicators
            has_price = bool(self.content_patterns['price'].search(markdown))
            has_options = bool(self.content_patterns['option_category'].search(markdown))
            
            return {
                'confirms': has_price or has_options,
                'signals': {'has_price': has_price, 'has_options': has_options}
            }
        
        elif expected_type == 'list':
            # Check for list indicators
            product_links = len(self.content_patterns['product_link'].findall(markdown))
            has_pagination = bool(self.content_patterns['pagination'].search(markdown))
            
            return {
                'confirms': product_links >= 5 or has_pagination,
                'signals': {'product_links': product_links, 'has_pagination': has_pagination}
            }
        
        return {'confirms': True, 'signals': {}}
    
    def _detect_blog_page(self, url: str, markdown: str) -> Tuple[float, Dict]:
        """Detect blog pages."""
        score = 0.0
        signals = {}
        
        if self.content_patterns['date_published'].search(markdown):
            score += 0.40
            signals['date_published'] = True
        
        blog_keywords = ['author:', 'share this', 'comments', 'tags:']
        blog_count = sum(1 for kw in blog_keywords if kw in markdown.lower())
        if blog_count >= 2:
            score += 0.30
            signals['blog_keywords'] = blog_count
        
        return min(score, 1.0), signals
    
    def _detect_list_page(self, url: str, markdown: str) -> Tuple[float, Dict]:
        """Detect list/collection pages."""
        score = 0.0
        signals = {}
        
        # Count product links (but be smarter about it)
        product_links = self.content_patterns['product_link'].findall(markdown)
        product_link_count = len(product_links)
        signals['product_links'] = product_link_count
        
        # CRITICAL: Only high counts indicate list pages
        # Product pages might have 5-10 "related products"
        # List pages have 20+
        if product_link_count >= 20:
            score += 0.60
            signals['many_product_links'] = True
        elif product_link_count >= 10:
            score += 0.40
            signals['multiple_product_links'] = True
        elif product_link_count >= 5:
            score += 0.15  # Might just be related products
        
        # Pagination is strong signal
        if self.content_patterns['pagination'].search(markdown):
            score += 0.25
            signals['pagination'] = True
        
        # Multiple "View Details" buttons
        view_details_count = len(self.content_patterns['view_details'].findall(markdown))
        if view_details_count >= 10:
            score += 0.20
        elif view_details_count >= 5:
            score += 0.10
        
        return min(score, 1.0), signals
    
    def _detect_product_page(self, url: str, markdown: str) -> Tuple[float, Dict]:
        """Detect individual product pages."""
        score = 0.0
        signals = {}
        
        # Base price
        if self.content_patterns['base_price'].search(markdown):
            score += 0.30
            signals['base_price'] = True
        
        # Price modifiers (customization)
        price_modifiers = self.content_patterns['price_modifier'].findall(markdown)
        if len(price_modifiers) >= 3:
            score += 0.25
            signals['price_modifiers'] = len(price_modifiers)
        
        # Option categories
        option_categories = self.content_patterns['option_category'].findall(markdown)
        if len(option_categories) >= 2:
            score += 0.30
            signals['option_categories'] = len(option_categories)
        
        # Product keywords
        product_keywords = ['specifications', 'dimensions', 'features', 'description']
        product_count = sum(1 for kw in product_keywords if kw in markdown.lower())
        if product_count >= 2:
            score += 0.15
            signals['product_keywords'] = product_count
        
        return min(score, 1.0), signals
    
    def get_classification_log(self) -> List[Dict]:
        """Get all classification decisions."""
        return self.classification_log
    
    def save_classification_log(self, filepath: str):
        """Save classification log to JSON file."""
        import json
        
        with open(filepath, 'w') as f:
            json.dump(self.classification_log, f, indent=2)
        
        print(f"✓ Classification log saved: {filepath}")
    
    def print_statistics(self):
        """Print classification statistics."""
        if not self.classification_log:
            print("No classifications logged yet.")
            return
        
        total = len(self.classification_log)
        
        type_counts = {}
        for log in self.classification_log:
            ptype = log['result']['page_type']
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
        
        type_confidences = {}
        for ptype in type_counts:
            confidences = [
                log['result']['confidence']
                for log in self.classification_log
                if log['result']['page_type'] == ptype
            ]
            type_confidences[ptype] = sum(confidences) / len(confidences)
        
        print(f"\n{'='*80}")
        print("CLASSIFICATION STATISTICS")
        print(f"{'='*80}")
        print(f"Total pages classified: {total}")
        print(f"\nPage Type Distribution:")
        for ptype in ['product', 'list', 'blog', 'other']:
            if ptype in type_counts:
                count = type_counts[ptype]
                pct = count / total * 100
                avg_conf = type_confidences[ptype]
                print(f"  {ptype.upper()}: {count} ({pct:.1f}%) - avg confidence: {avg_conf:.0%}")
        print(f"{'='*80}\n")


# Backward compatibility
class RuleBasedClassifier(DynamicPageClassifier):
    """Backward-compatible wrapper."""
    
    def __init__(self):
        """Initialize with default settings."""
        super().__init__(enable_logging=True)