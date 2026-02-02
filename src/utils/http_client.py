"""HTTP client for making requests."""

import requests
from typing import Optional, Dict


class HTTPClient:
    """Wrapper for HTTP requests with Jina AI integration."""
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.jina_base_url = "https://r.jina.ai/"
    
    def scrape_with_jina(self, url: str) -> Optional[str]:
        """
        Scrape a URL using Jina AI Reader.
        
        Args:
            url: The URL to scrape
            
        Returns: 
            Markdown content or None if failed
        """
        try:
            headers = {
                "X-Return-Format": "markdown",
                "X-Remove-Selector": "nav, footer, header, .navigation, .menu, script, style, .cookie"
            }
            
            response = requests.get(
                f"{self.jina_base_url}{url}",
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.text
            
        except requests.exceptions.Timeout:
            print(f"  ✗ Timeout scraping {url}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Failed to scrape {url}: {e}")
            return None
    
    def get(self, url: str, headers: Optional[Dict] = None) -> Optional[requests.Response]:
        """
        Make a GET request.
        
        Args:
            url: The URL to request
            headers: Optional headers
            
        Returns:
            Response object or None if failed
        """
        try:
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request failed for {url}: {e}")
            return None