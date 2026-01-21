"""Base classifier interface."""

from abc import ABC, abstractmethod


class BaseClassifier(ABC):
    """Abstract base class for page classifiers."""
    
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