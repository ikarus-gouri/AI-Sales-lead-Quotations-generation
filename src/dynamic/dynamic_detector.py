"""Dynamic configurator detection for Model-D routing.

This module detects JavaScript-based configurators that require browser
execution for proper extraction. It analyzes multiple signals to determine
if a page needs Model-D (browser automation) vs Model-S (static extraction).

Detection Signals:
    1. **JavaScript Frameworks**: React, Vue, Angular, Svelte, Next.js, etc.
    2. **SPA Indicators**: Single-page app patterns (div#root, __NEXT_DATA__, etc.)
    3. **Dynamic Pricing**: Price calculators, update functions, API calls
    4. **Critical Signal**: Price element present + NO static options (50% confidence)
    5. **Known Platforms**: Shopify apps, WooCommerce plugins, ThreeKit, etc.

Confidence Calculation:
    - JS framework: +25%
    - SPA patterns: +20%
    - Dynamic pricing: +25%
    - Price without static options: +50% (strong signal)
    - Known platform: +15%
    - Threshold: >= 50% triggers Model-D

Usage:
    >>> detector = DynamicConfiguratorDetector()
    >>> result = detector.is_dynamic_configurator(url, markdown)
    >>> if result['is_dynamic'] and result['confidence'] >= 0.50:
    ...     # Use Model-D (browser automation)
    ...     pass
    >>> else:
    ...     # Use Model-S (static extraction)
    ...     pass
\"\"\"
"""
import re
from typing import Dict, List
from urllib.parse import urlparse


class DynamicConfiguratorDetector:
    # \"\"\"Detect JavaScript-driven configurators requiring browser execution.
    
    # This detector analyzes page content to determine if a product configurator
    # is JavaScript-based and requires browser automation (Model-D) rather than
    # static extraction (Model-S).
    
    # Detection Strategy:
    #     - Looks for JavaScript frameworks and SPA patterns
    #     - Detects dynamic pricing indicators
    #     - **Key heuristic**: Price present but NO static options = likely JS configurator
    #     - Identifies known e-commerce platforms
    """
    Attributes:
        js_frameworks: List of JavaScript framework names to detect
        spa_indicators: Regex patterns for single-page app detection
        dynamic_price_patterns: Patterns indicating dynamic price calculation
        known_platforms: E-commerce platforms with JS configurators
    
    Example:
        >>> detector = DynamicConfiguratorDetector()
        >>> result = detector.is_dynamic_configurator(
        ...     url=\"https://example.com/product\",
        ...     markdown=page_content
        ... )
        >>> print(f\"Dynamic: {result['is_dynamic']}\")
        >>> print(f\"Confidence: {result['confidence']:.2%}\")
        >>> print(f\"Reasons: {result['reasons']}\")
   """
    
    def __init__(self):
        # JavaScript framework indicators
        self.js_frameworks = [
            'react', 'vue', 'angular', 'svelte', 'next.js',
            'gatsby', 'nuxt', 'ember'
        ]
        
        # Common SPA patterns
        self.spa_indicators = [
            r'<div\s+id=["\']root["\']',
            r'<div\s+id=["\']app["\']',
            r'__NEXT_DATA__',
            r'__NUXT__',
            r'window\.__INITIAL_STATE__'
        ]
        
        # Dynamic pricing indicators
        self.dynamic_price_patterns = [
            r'data-price',
            r'price-calculator',
            r'dynamic-price',
            r'price-update',
            r'calculateTotal',
            r'updatePrice'
        ]
        
        # Known platforms that use dynamic configurators
        self.known_platforms = [
            'shopify', 'woocommerce', 'magento',
            'threekit', 'zakeke', 'customcat',
            'infinite-options', 'product-builder'
        ]
    
    def is_dynamic_configurator(
        self,
        url: str,
        markdown: str,
        html_snippet: str = ""
    ) -> Dict:
        """
        Determine if configurator is dynamic (requires browser execution).
        
        Args:
            url: Product page URL
            markdown: Page content in markdown (from Jina)
            html_snippet: Raw HTML snippet if available (optional)
            
        Returns:
            Detection result with confidence and signals
        """
        result = {
            'is_dynamic': False,
            'confidence': 0.0,
            'model': 'static',  # or 'dynamic'
            'signals': {},
            'reasons': []
        }
        
        markdown_lower = markdown.lower()
        html_lower = html_snippet.lower() if html_snippet else ""
        
        # Signal 1: JavaScript framework detected
        framework_score = self._detect_framework(markdown_lower, html_lower)
        result['signals']['framework'] = framework_score
        
        # Signal 2: SPA indicators
        spa_score = self._detect_spa_pattern(markdown_lower, html_lower)
        result['signals']['spa_pattern'] = spa_score
        
        # Signal 3: Dynamic pricing indicators
        dynamic_price_score = self._detect_dynamic_pricing(markdown_lower, html_lower)
        result['signals']['dynamic_pricing'] = dynamic_price_score
        
        # Signal 4: No customization options in markdown
        has_static_options = self._has_static_options(markdown)
        result['signals']['static_options_found'] = has_static_options
        
        # Signal 5: Price element exists
        has_price_element = self._has_price_element(markdown)
        result['signals']['price_element_found'] = has_price_element
        
        # Signal 6: Known platform
        platform_detected = self._detect_known_platform(url, markdown_lower)
        result['signals']['known_platform'] = platform_detected
        
        # Calculate overall confidence
        result = self._calculate_dynamic_confidence(result)
        
        return result
    
    def _detect_framework(self, markdown: str, html: str) -> int:
        """Detect JavaScript framework usage."""
        score = 0
        
        for framework in self.js_frameworks:
            if framework in markdown or framework in html:
                score += 1
        
        # React/Vue specific patterns
        if 'react' in html or 'reactdom' in html:
            score += 2
        if 'vue' in html or 'v-bind' in html or 'v-model' in html:
            score += 2
        
        return min(score, 5)
    
    def _detect_spa_pattern(self, markdown: str, html: str) -> int:
        """Detect single-page application patterns."""
        score = 0
        
        for pattern in self.spa_indicators:
            if re.search(pattern, html, re.IGNORECASE):
                score += 2
        
        # Check for minimal HTML content
        if html and len(html) < 1000 and '<div id=' in html:
            score += 1
        
        return min(score, 5)
    
    def _detect_dynamic_pricing(self, markdown: str, html: str) -> int:
        """Detect dynamic price calculation indicators."""
        score = 0
        
        for pattern in self.dynamic_price_patterns:
            if re.search(pattern, markdown + html, re.IGNORECASE):
                score += 1
        
        # API endpoint patterns
        api_patterns = [
            r'/api/price',
            r'/calculate',
            r'/quote',
            r'graphql'
        ]
        
        for pattern in api_patterns:
            if re.search(pattern, markdown + html, re.IGNORECASE):
                score += 2
        
        return min(score, 5)
    
    def _has_static_options(self, markdown: str) -> bool:
        """
        Check if customization options are present in markdown.
        Uses the same logic as ProductExtractor to avoid false positives.
        """
        # Look for valid customization patterns matching ProductExtractor logic
        
        # Pattern 1: Images with prices in alt text (e.g., ![Color (+$50)](url))
        image_with_price = re.findall(
            r'!\[(?:Image \d+:?\s*)?([^\]]+?)\s*\(\+?\$[\d,]+\)\]\([^\)]+\)',
            markdown
        )
        
        # Pattern 2: Checkboxes with prices (e.g., - [x] Option (+$50))
        checkbox_with_price = re.findall(
            r'^-\s*\[x?\]\s*(.+?)\s*\(\+?\$[\d,]+\)',
            markdown,
            re.MULTILINE
        )
        
        # Pattern 3: Customization category headers followed by options
        # (e.g., "Size:" followed by bullet points or images)
        category_pattern = r'^([A-Z][^:]+?):\s*\*?\s*$'
        has_categories = bool(re.search(category_pattern, markdown, re.MULTILINE))
        
        # Count valid options
        total_options = len(image_with_price) + len(checkbox_with_price)
        
        # Need at least 3 valid options OR at least 1 option with categories
        return total_options >= 3 or (has_categories and total_options >= 1)
    
    def _has_price_element(self, markdown: str) -> bool:
        """Check if price information is present."""
        price_patterns = [
            r'\$[\d,]+(?:\.\d{2})?',
            r'price:?\s*\$',
            r'total:?\s*\$',
            r'from\s+\$[\d,]+'
        ]
        
        for pattern in price_patterns:
            if re.search(pattern, markdown, re.IGNORECASE):
                return True
        
        return False
    
    def _detect_known_platform(self, url: str, markdown: str) -> bool:
        """Detect known e-commerce platforms."""
        url_lower = url.lower()
        
        for platform in self.known_platforms:
            if platform in url_lower or platform in markdown:
                return True
        
        return False
    
    def _calculate_dynamic_confidence(self, result: Dict) -> Dict:
        """Calculate final confidence score and make decision."""
        signals = result['signals']
        score = 0.0
        reasons = []
        
        # High-weight signals
        if signals.get('framework', 0) >= 1:
            score += 0.25
            reasons.append(f"js_framework({signals['framework']})")
        
        if signals.get('spa_pattern', 0) >= 2:
            score += 0.20
            reasons.append("spa_detected")
        
        if signals.get('dynamic_pricing', 0) >= 2:
            score += 0.25
            reasons.append(f"dynamic_pricing({signals['dynamic_pricing']})")
        
        # Critical combination: Has price but no static options
        # This is a STRONG signal that customizations are JavaScript-driven
        if signals.get('price_element_found') and not signals.get('static_options_found'):
            score += 0.50  # Increased from 0.30 - this is a critical signal
            reasons.append("price_without_static_options")
        
        # Platform detection
        if signals.get('known_platform'):
            score += 0.15
            reasons.append("known_platform")
        
        # Decision logic
        result['confidence'] = min(score, 1.0)
        result['reasons'] = reasons
        
        # Threshold for switching to Model-D
        if result['confidence'] >= 0.5:
            result['is_dynamic'] = True
            result['model'] = 'dynamic'
        else:
            result['model'] = 'static'
        
        return result
    
    def should_use_browser(self, detection_result: Dict) -> bool:
        """
            Determine if browser execution is needed.
        
        Args:
            detection_result: Result from is_dynamic_configurator()
            
        Returns:
            True if browser needed, False if static scraping sufficient
        """
        return detection_result['is_dynamic'] and detection_result['confidence'] >= 0.5