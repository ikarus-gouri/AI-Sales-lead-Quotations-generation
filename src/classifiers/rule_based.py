"""Rule-based page classifier with multi-class detection.

This classifier uses URL patterns and content analysis to classify pages.
"""

import re
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from .base_classifier import BaseClassifier


@dataclass
class ClassificationSignals:
    """Detailed signals detected during classification."""
    
    # Price signals
    price_count: int = 0
    price_patterns: List[str] = field(default_factory=list)
    has_base_price: bool = False
    has_price_modifiers: bool = False
    
    # Structure signals
    heading_count: int = 0
    option_categories: int = 0
    list_items: int = 0
    images_with_descriptions: int = 0
    
    # Content signals
    customization_keywords: int = 0
    product_keywords: int = 0
    blog_indicators: int = 0
    
    # Form signals
    has_checkboxes: bool = False
    has_radio_buttons: bool = False
    has_dropdowns: bool = False
    
    # CTA signals
    has_purchase_cta: bool = False
    has_customization_cta: bool = False
    
    # Metadata
    content_length: int = 0
    unique_words: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            'price_count': self.price_count,
            'has_base_price': self.has_base_price,
            'has_price_modifiers': self.has_price_modifiers,
            'option_categories': self.option_categories,
            'customization_keywords': self.customization_keywords,
            'product_keywords': self.product_keywords,
            'blog_indicators': self.blog_indicators,
            'has_checkboxes': self.has_checkboxes,
            'has_purchase_cta': self.has_purchase_cta,
            'content_length': self.content_length
        }


@dataclass
class PageClassification:
    """Complete page classification result."""
    
    page_type: str  # "product", "list", "blog", "other"
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    signals: Dict = field(default_factory=dict)
    reasoning: List[str] = field(default_factory=list)
    
    def add_reason(self, reason: str):
        """Add reasoning step."""
        self.reasoning.append(reason)


class RuleBasedClassifier(BaseClassifier):
    """
    Rule-based classifier using URL patterns and content analysis.
    
    Strategy:
    1. Check URL patterns first (high confidence)
    2. Validate with content patterns
    3. Use content analysis for ambiguous cases
    """
    
    def __init__(self, enable_logging: bool = True):
        """Initialize classifier."""
        self.enable_logging = enable_logging
        self.classification_log: List[Dict] = []
        self._compile_patterns()
        
        # Thresholds
        self.PRODUCT_THRESHOLD = 0.55
    
    def _compile_patterns(self):
        """Compile all regex patterns."""
        
        # URL patterns
        self.url_patterns = {
            'product_strong': [
                r'/products?/[^/]+/?$',
                r'/items?/[^/]+/?$',
                r'/p/[^/]+/?$',
            ],
            'list_strong': [
                r'/collections?/?$',
                r'/collections?/[^/]+/?$',
                r'/categor(?:y|ies)/?',
                r'/shop/?$',
                r'/products?/?$',
            ],
            'blog_strong': [
                r'/blog/',
                r'/article/',
                r'/post/',
                r'/news/',
            ]
        }
        
        # Price patterns
        self.price_patterns = {
            'base_price': re.compile(
                r'(?:base\s+)?price[:\s]*\$?[\d,]+(?:\.\d{2})?',
                re.IGNORECASE
            ),
            'price_modifier': re.compile(
                r'\+\s*\$[\d,]+(?:\.\d{2})?|\(\+\$[\d,]+(?:\.\d{2})?\)'
            ),
            'price_mention': re.compile(
                r'\$[\d,]+(?:\.\d{2})?'
            ),
        }
        
        # Structure patterns
        self.structure_patterns = {
            'checkbox': re.compile(r'-\s*\[[x ]\]\s+(.+)'),
            'image_with_alt': re.compile(r'!\[([^\]]+)\]\(([^\)]+)\)'),
        }
        
        # Category pattern
        self.category_pattern = re.compile(
            r'^(?:#{2,4}\s+)?([A-Z][^:\n]{2,40}):\s*$',
            re.MULTILINE
        )
        
        # CTA patterns
        self.cta_patterns = {
            'purchase': re.compile(
                r'(?:add\s+to\s+cart|buy\s+now|purchase|get\s+quote|request\s+quote)',
                re.IGNORECASE
            ),
            'customization': re.compile(
                r'(?:customiz|personalis|configure|build\s+your|design\s+your)',
                re.IGNORECASE
            )
        }
        
        # Blog patterns
        self.blog_patterns = {
            'date': re.compile(
                r'(?:published|posted|written)\s+(?:on\s+)?',
                re.IGNORECASE
            ),
            'author': re.compile(r'by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'),
            'tags': re.compile(r'(?:tags?|categories?):\s*', re.IGNORECASE),
        }
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """Determine if page is a product page."""
        result = self.classify(url, markdown)
        
        if self.enable_logging:
            self.classification_log.append({
                'url': url,
                'result': {
                    'page_type': result.page_type,
                    'confidence': result.confidence,
                    'reasoning': result.reasoning
                }
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
            }
        )
        
        # Check content length
        if len(markdown) < 200:
            result.add_reason("Content too short")
            return result
        
        # Phase 1: URL Pattern Analysis
        url_classification = self._classify_by_url(url)
        
        if url_classification['confidence'] >= 0.8:
            result.page_type = url_classification['type']
            result.confidence = url_classification['confidence']
            result.add_reason(f"Strong URL pattern: {url_classification['type']}")
            return result
        
        # Phase 2: Content Analysis
        # Check for blog indicators first (blocker)
        blog_score = self._detect_blog_indicators(markdown)
        if blog_score >= 0.6:
            result.page_type = 'blog'
            result.confidence = blog_score
            result.add_reason("Blog indicators detected")
            return result
        
        # Detect product page
        product_score, product_signals = self._detect_product_page(url, markdown)
        result.scores['product'] = product_score
        result.signals['product'] = product_signals
        
        # Detect list page
        list_score, list_signals = self._detect_list_page(markdown)
        result.scores['list'] = list_score
        result.signals['list'] = list_signals
        
        # Determine final classification
        if product_score >= self.PRODUCT_THRESHOLD and product_score > list_score:
            result.page_type = 'product'
            result.confidence = product_score
            result.add_reason(f"Product page detected (score: {product_score:.2f})")
        elif list_score >= 0.5:
            result.page_type = 'list'
            result.confidence = list_score
            result.add_reason(f"List page detected (score: {list_score:.2f})")
        else:
            result.page_type = 'other'
            result.confidence = 0.3
            result.add_reason("No clear classification")
        
        return result
    
    def _classify_by_url(self, url: str) -> Dict:
        """Classify based on URL patterns."""
        url_lower = url.lower()
        
        # Check strong patterns
        for pattern in self.url_patterns['product_strong']:
            if re.search(pattern, url_lower):
                return {'type': 'product', 'confidence': 0.9}
        
        for pattern in self.url_patterns['list_strong']:
            if re.search(pattern, url_lower):
                return {'type': 'list', 'confidence': 0.9}
        
        for pattern in self.url_patterns['blog_strong']:
            if re.search(pattern, url_lower):
                return {'type': 'blog', 'confidence': 0.9}
        
        return {'type': 'unknown', 'confidence': 0.0}
    
    def _detect_blog_indicators(self, markdown: str) -> float:
        """Detect blog indicators."""
        score = 0.0
        
        if self.blog_patterns['date'].search(markdown):
            score += 0.40
        
        if self.blog_patterns['author'].search(markdown):
            score += 0.30
        
        if self.blog_patterns['tags'].search(markdown):
            score += 0.20
        
        blog_keywords = ['share this', 'comments', 'reading time']
        blog_count = sum(1 for kw in blog_keywords if kw in markdown.lower())
        score += blog_count * 0.10
        
        return min(score, 1.0)
    
    def _detect_list_page(self, markdown: str) -> Tuple[float, Dict]:
        """Detect list/collection pages."""
        score = 0.0
        signals = {}
        
        # Count product-like links
        markdown_lower = markdown.lower()
        product_link_indicators = ['view details', 'shop now', 'learn more']
        link_count = sum(markdown_lower.count(ind) for ind in product_link_indicators)
        signals['product_links'] = link_count
        
        # Only high counts indicate list pages
        if link_count >= 15:
            score += 0.60
        elif link_count >= 8:
            score += 0.40
        elif link_count >= 5:
            score += 0.20
        
        # Check for pagination
        pagination_keywords = ['page', 'next', 'previous', 'showing']
        if any(kw in markdown_lower for kw in pagination_keywords):
            score += 0.25
            signals['pagination'] = True
        
        return min(score, 1.0), signals
    
    def _detect_product_page(self, url: str, markdown: str) -> Tuple[float, Dict]:
        """Detect individual product pages."""
        score = 0.0
        signals = ClassificationSignals()
        
        markdown_lower = markdown.lower()
        
        # Base price
        if self.price_patterns['base_price'].search(markdown):
            score += 0.30
            signals.has_base_price = True
        
        # Price modifiers (customization options)
        modifiers = self.price_patterns['price_modifier'].findall(markdown)
        if len(modifiers) >= 3:
            score += 0.25
            signals.has_price_modifiers = True
        
        # Option categories
        categories = self._count_option_categories(markdown)
        signals.option_categories = categories
        if categories >= 3:
            score += 0.30
        elif categories >= 2:
            score += 0.20
        
        # Customization keywords
        custom_keywords = ['customize', 'choose', 'select', 'options', 'configure']
        custom_count = sum(1 for kw in custom_keywords if kw in markdown_lower)
        signals.customization_keywords = custom_count
        if custom_count >= 3:
            score += 0.15
        
        # Product keywords
        product_keywords = ['specifications', 'dimensions', 'features', 'description']
        product_count = sum(1 for kw in product_keywords if kw in markdown_lower)
        signals.product_keywords = product_count
        if product_count >= 2:
            score += 0.10
        
        # CTAs
        if self.cta_patterns['purchase'].search(markdown):
            score += 0.10
            signals.has_purchase_cta = True
        
        if self.cta_patterns['customization'].search(markdown):
            score += 0.10
            signals.has_customization_cta = True
        
        # Form elements
        checkboxes = len(self.structure_patterns['checkbox'].findall(markdown))
        if checkboxes >= 3:
            score += 0.15
            signals.has_checkboxes = True
        
        return min(score, 1.0), signals.to_dict()
    
    def _count_option_categories(self, markdown: str) -> int:
        """Count structured option categories."""
        lines = markdown.split('\n')
        categories = 0
        
        for i, line in enumerate(lines):
            match = self.category_pattern.match(line.strip())
            if match:
                # Check if next few lines have items
                items_found = 0
                for j in range(i + 1, min(i + 15, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if next_line.startswith('-') or next_line.startswith('*'):
                        items_found += 1
                    elif self.category_pattern.match(next_line):
                        break
                
                if items_found >= 2:
                    categories += 1
        
        return categories
    
    def get_classification_log(self) -> List[Dict]:
        """Get all classification decisions."""
        return self.classification_log
    
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
        
        print(f"\n{'='*80}")
        print("CLASSIFICATION STATISTICS")
        print(f"{'='*80}")
        print(f"Total pages classified: {total}")
        print(f"\nPage Type Distribution:")
        for ptype in ['product', 'list', 'blog', 'other']:
            if ptype in type_counts:
                count = type_counts[ptype]
                pct = count / total * 100
                print(f"  {ptype.upper()}: {count} ({pct:.1f}%)")
        print(f"{'='*80}\n")