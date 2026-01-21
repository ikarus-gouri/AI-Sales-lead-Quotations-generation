"""Rule-based page classifier."""

import re
from .base_classifier import BaseClassifier


class RuleBasedClassifier(BaseClassifier):
    """Classify pages using rule-based logic."""
    
    def __init__(self):
        self.url_indicators = [
            'inquiry', 'enquiry', 'customize', 'builder', 'configurator',
            'quote', 'quotation', 'build-your', 'design-your'
        ]
        
        self.content_indicators = [
            'base price',
            'customization',
            'choose your',
            'select your',
            'interior paneling',
            'exterior',
            'heater',
            'accessories',
            'add-ons',
            'options',
            'upgrade',
            'included',
            'dimensions:',
            'capacity:',
            'electrical requirements'
        ]
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Check if page is a product/customization page using rules.
        
        Args:
            url: The page URL
            markdown: The page content
            
        Returns:
            True if product page, False otherwise
        """
        url_lower = url.lower()
        markdown_lower = markdown.lower()
        
        # Check URL indicators
        if any(indicator in url_lower for indicator in self.url_indicators):
            return True
        
        # Check content indicators
        indicator_count = sum(
            1 for indicator in self.content_indicators 
            if indicator in markdown_lower
        )
        
        # If page has multiple customization indicators
        if indicator_count >= 3:
            return True
        
        # Check for form-like structures (multiple images with prices)
        price_pattern_count = len(re.findall(r'\(\+?\$[\d,]+\)', markdown))
        if price_pattern_count >= 5:
            return True
        
        return False