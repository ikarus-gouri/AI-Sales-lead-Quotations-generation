"""Dynamic classifier for Model-D hybrid routing.

This classifier determines whether each page should use:
    - Model-S: Static extraction (fast, pattern-based)
    - Model-D: Browser-based extraction (slow, handles JavaScript)

Decision Process:
    1. Run static classification (BalancedClassifier)
    2. If product page, analyze for dynamic configurator:
        - Check for JavaScript frameworks
        - Detect SPA patterns
        - Look for dynamic pricing signals
        - **Critical**: Price present + NO static options
    3. Calculate confidence score:
        - >= 50%: Route to Model-D (browser)
        - < 50%: Route to Model-S (static)

Key Signal Weights:
    - JS framework detected: +25%
    - SPA patterns: +20%
    - Dynamic pricing: +25%
    - Price without static options: +50% (strong signal)
    - Known platform: +15%

Example:
    >>> classifier = DynamicClassifier(strictness="balanced")
    >>> result = classifier.classify_page(url, markdown)
    >>> print(f"Model: {result['model']}")  # 'S' or 'D'
    >>> print(f"Confidence: {result['confidence']:.2%}")
"""

from typing import Dict
from .balanced_classifier import BalancedClassifier, StrictnessLevel
from ..dynamic.dynamic_detector import DynamicConfiguratorDetector


class DynamicClassifier:
    """Hybrid classifier for automatic Model-S/Model-D routing.
    
    This classifier wraps BalancedClassifier and DynamicConfiguratorDetector
    to intelligently route each product page to the appropriate extraction method.
    
    Decision flow:
        1. Run static classification (BalancedClassifier)
        2. If product page, check if dynamic configurator (DynamicConfiguratorDetector)
        3. If confidence >= 50%: Route to Model-D (browser-based)
        4. Otherwise: Route to Model-S (static extraction)
    
    Attributes:
        static_classifier: BalancedClassifier for initial page classification
        dynamic_detector: DynamicConfiguratorDetector for JS configurator detection
        strictness: StrictnessLevel enum exposed for compatibility
    
    Example:
        >>> classifier = DynamicClassifier(strictness="balanced")
        >>> classification = classifier.classify_page(url, markdown)
        >>> if classification['model'] == 'D':
        ...     # Use browser-based extraction
        ...     pass
        >>> else:
        ...     # Use static extraction
        ...     pass
    """
    
    def __init__(self, strictness: str = "balanced"):
        """
        Initialize dynamic classifier.
        
        Args:
            strictness: Strictness level for static classification
                       ('lenient', 'balanced', 'strict')
        """
        # Convert string to enum for BalancedClassifier
        strictness_map = {
            "lenient": StrictnessLevel.LENIENT,
            "balanced": StrictnessLevel.BALANCED,
            "strict": StrictnessLevel.STRICT
        }
        strictness_level = strictness_map.get(strictness.lower(), StrictnessLevel.BALANCED)
        
        self.static_classifier = BalancedClassifier(strictness=strictness_level)
        self.dynamic_detector = DynamicConfiguratorDetector()
        # Expose the strictness enum from static_classifier for compatibility
        self.strictness = self.static_classifier.strictness
        
        print(f"\033[32m[✓]\033[0m Dynamic Classifier initialized (strictness={strictness})")
    
    def classify_page(
        self,
        url: str,
        markdown: str,
        html_snippet: str = ""
    ) -> Dict:
        """
        Classify page and determine extraction model.
        
        Returns:
        {
            'page_type': 'product' | 'category' | 'blog' | 'other',
            'is_product': bool,
            'model': 'S' | 'D',
            'confidence': float,
            'extraction_strategy': 'static' | 'dynamic_browser',
            'static_classification': {...},
            'dynamic_detection': {...}
        }
        """
        # Step 1: Static classification
        # Use classify() method which returns Classification object
        static_classification = self.static_classifier.classify(url, markdown)
        
        # Convert Classification object to dict, handling enums properly
        page_type = static_classification.page_type
        if hasattr(page_type, 'value'):
            # It's an enum - extract string value
            page_type = page_type.value
        
        static_result = {
            'page_type': page_type,
            'is_product': static_classification.is_product,
            'confidence': static_classification.confidence,
            'signals': static_classification.signals if hasattr(static_classification, 'signals') else {},
            'reasons': static_classification.reasons if hasattr(static_classification, 'reasons') else []
        }
        
        result = {
            'page_type': page_type,
            'is_product': static_result['is_product'],
            'model': 'S',  # Default to static
            'confidence': static_result['confidence'],
            'extraction_strategy': 'static',
            'static_classification': static_result,
            'dynamic_detection': None
        }
        
        # If not a product page, no need to check for dynamic
        if not static_result['is_product']:
            return result
        
        # Step 2: Check if dynamic configurator
        dynamic_detection = self.dynamic_detector.is_dynamic_configurator(
            url, markdown, html_snippet
        )
        
        result['dynamic_detection'] = dynamic_detection
        
        # Step 3: Route decision
        if dynamic_detection['is_dynamic']:
            result['model'] = 'D'
            result['extraction_strategy'] = 'dynamic_browser'
            result['confidence'] = dynamic_detection['confidence']
            
            print(f"  \033[36m[D]\033[0m Model-D selected (dynamic configurator)")
            print(f"     Confidence: {dynamic_detection['confidence']:.2%}")
            print(f"     Reasons: {', '.join(dynamic_detection['reasons'])}")
        else:
            result['model'] = 'S'
            result['extraction_strategy'] = 'static'
            
            print(f"  \033[34m[S]\033[0m Model-S selected (static scraping)")
        
        return result
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Simplified method matching BalancedClassifier interface.
        
        Returns:
            True if product page (regardless of model)
        """
        result = self.classify_page(url, markdown)
        return result['is_product']
    
    def should_use_browser(self, url: str, markdown: str, html_snippet: str = "") -> bool:
        """
        Determine if browser execution is needed.
        
        Returns:
            True if Model-D should be used
        """
        result = self.classify_page(url, markdown, html_snippet)
        return result['model'] == 'D'
    
    def get_extraction_strategy(self, url: str, markdown: str) -> str:
        """
        Get extraction strategy for this page.
        
        Returns:
            'static' or 'dynamic_browser'
        """
        result = self.classify_page(url, markdown)
        return result['extraction_strategy']