"""Base classifier interface.

This module defines the abstract interface that all page classifiers must implement.
Classifiers are responsible for determining whether a page is a product page,
category page, blog post, or other content type.

Implementations:
    - BalancedClassifier: Static classification using content analysis
    - DynamicClassifier: Hybrid routing between static and dynamic extraction
"""

from abc import ABC, abstractmethod


class BaseClassifier(ABC):
    """Abstract base class for page classifiers.
    
    All classifiers must implement the is_product_page() method to determine
    if a given page contains product information with customization options.
    """
    
    @abstractmethod
    def is_product_page(self, url: str, markdown: str) -> bool:
        """
        Determine if a page is a product customization page.
        
        Args:
            url: The page URL
            markdown: The page content in markdown
            
        Returns:
            True if product page, False otherwise
        """
        pass