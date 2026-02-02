"""AI-based page classifier using Gemini."""

import google.generativeai as genai
from .base_classifier import BaseClassifier
from .rule_based import RuleBasedClassifier


class AIClassifier(BaseClassifier):
    """Classify pages using AI (Gemini)."""
    
    def __init__(self, api_key: str, model_name: str = "models/gemini-2.0-flash-exp"):
        """
        Initialize AI classifier.
        
        Args:
            api_key: Gemini API key
            model_name: Gemini model to use
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.fallback_classifier = RuleBasedClassifier()
        print("✓ Gemini AI enabled for page classification")
    
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Use AI to determine if page is a product page.
        
        Args:
            url: The page URL
            markdown: The page content
            
        Returns:
            True if product page, False otherwise
        """
        # Truncate content for speed
        content_sample = markdown[:3000]
        
        prompt = f"""
Analyze this webpage and determine if it's a PRODUCT CUSTOMIZATION PAGE.

A product customization page typically has:
- Base product information (price, dimensions, specs)
- Multiple customization categories (wood types, colors, accessories)
- Options with prices (e.g., "+$500", "Included")
- Images of different options
- Form-like structure for selecting options

URL: {url}

Content sample:
"""
{content_sample}
"""

Respond with ONLY "YES" or "NO".
"""
        
        try:
            response = self.model.generate_content(prompt)
            answer = response.text.strip().upper()
            return answer == "YES"
        except Exception as e:
            print(f"  ⚠ AI classification failed, using rules: {e}")
            return self.fallback_classifier.is_product_page(url, markdown)