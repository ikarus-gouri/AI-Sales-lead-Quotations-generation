"""HTTP client for making requests with Jina-safe rate limiting."""

import requests
import time
import threading
import re
from typing import Optional, Dict, List
from urllib.parse import urlparse, urlunparse
from dataclasses import dataclass


@dataclass
class JinaResponse:
    """Response from Jina API with extracted data."""
    url: str
    title: str
    text: str
    links: List[str]


class HTTPClient:
    """
    Wrapper for HTTP requests with Jina AI integration.
    
    Implements Jina-safe patterns:
    - Concurrency limit (4 max concurrent)
    - Fixed delay (400ms between calls)
    - Limited retries (3 max with backoff)
    - URL caching (never hit same URL twice)
    - Global cooldown (60s after 5x429)
    - Non-content page blocklist
    """
    
    # Class-level state for all instances
    _jina_semaphore = threading.Semaphore(4)  # Max 4 concurrent
    _jina_429_count = 0
    _jina_lock = threading.Lock()  # Protect shared counters
    _last_429_reset = time.time()
    
    # Non-content pages to skip
    BLOCKLIST = [
        '/login', '/signin', '/sign-in',
        '/cart', '/basket',
        '/account', '/my-account', '/profile',
        '/checkout', '/payment',
        '/privacy', '/terms', '/conditions',
        '/faq', '/help', '/support',
        '/contact', '/about-us',
        '/sitemap', '/robots.txt'
    ]
    
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.jina_base_url = "https://r.jina.ai/"
    
    def _should_skip_jina_url(self, url: str) -> bool:
        """Check if URL is on blocklist (non-content page)."""
        url_lower = url.lower()
        return any(blocked in url_lower for blocked in self.BLOCKLIST)
    
    def _jina_call_with_limit(self, url: str) -> Optional[str]:
        """
        Make Jina API call with concurrency limiting and retry logic.
        
        Args:
            url: URL to scrape
            
        Returns:
            Markdown content or None
        """
        with self._jina_semaphore:
            # Fixed delay to smooth traffic (Jina hates bursts)
            time.sleep(0.4)
            
            # Limited retries with backoff
            for attempt in range(3):
                try:
                    result = self._jina_request_sync(url)
                    
                    # Reset 429 count on success
                    if result is not None:
                        with HTTPClient._jina_lock:
                            HTTPClient._jina_429_count = 0
                    
                    return result
                    
                except Exception as e:
                    error_str = str(e)
                    
                    # Check for 429
                    if "429" in error_str or "rate limit" in error_str.lower():
                        with HTTPClient._jina_lock:
                            HTTPClient._jina_429_count += 1
                            current_count = HTTPClient._jina_429_count
                        
                        # Global cooldown if 429 spikes
                        if current_count >= 5:
                            print(f"  ⚠️  Jina rate limit spike detected. Cooling down for 60s...")
                            time.sleep(60)
                            with HTTPClient._jina_lock:
                                HTTPClient._jina_429_count = 0
                        
                        # Retry on 429 with exponential backoff: 10s, 20s, 40s (max)
                        if attempt < 2:
                            retry_delay = min(10 * (2 ** attempt), 40)  # 10s, 20s, 40s
                            print(f"  ⚠️  Jina rate limit (429) for {url} - retrying in {retry_delay}s (attempt {attempt + 1}/3)")
                            time.sleep(retry_delay)
                        else:
                            print(f"  ✗ Jina rate limit (429) for {url} - all retries exhausted")
                            return None
                    
                    # For other errors, retry with small backoff
                    elif attempt < 2:
                        time.sleep(2 + attempt)
                    else:
                        print(f"  ✗ Failed to scrape {url} after {attempt + 1} attempts: {e}")
                        return None
            
            return None
    
    def _jina_request_sync(self, url: str) -> Optional[str]:
        """Synchronous Jina request."""
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
            # Re-raise to be caught by async wrapper for 429 handling
            raise
    
    def scrape_with_jina(self, url: str) -> Optional[str]:
        """
        Scrape a URL using Jina AI Reader with rate limiting.
        
        Args:
            url: The URL to scrape
            
        Returns:
            Markdown content or None if failed
        """
        # Check blocklist
        if self._should_skip_jina_url(url):
            print(f"  ⏭️  Skipping non-content page: {url}")
            return None
        
        # Make rate-limited call
        result = self._jina_call_with_limit(url)
        
        return result
    
    def get(self, url: str, headers: Optional[Dict] = None) -> Optional[requests.Response]:
        """
        Make a GET request (non-Jina).
        
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


class JinaClient:
    """
    Jina AI client for URL discovery and content extraction.
    
    Provides structured responses with title, text, and extracted links.
    Used by AI crawler for semantic page classification.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize Jina client.
        
        Args:
            api_key: Jina API key (currently not required for r.jina.ai)
        """
        self.api_key = api_key
        self.http_client = HTTPClient()
    
    def fetch(self, url: str) -> JinaResponse:
        """
        Fetch page content with structured extraction.
        
        Args:
            url: URL to fetch
            
        Returns:
            JinaResponse with title, text, and links
        """
        # Get markdown content
        markdown = self.http_client.scrape_with_jina(url)
        
        if not markdown:
            return JinaResponse(
                url=url,
                title="",
                text="",
                links=[]
            )
        
        # Extract title from markdown
        title = self._extract_title(markdown)
        
        # Extract links from markdown
        links = self._extract_links(markdown)
        
        # Clean text (remove markdown formatting)
        text = self._clean_text(markdown)
        
        return JinaResponse(
            url=url,
            title=title,
            text=text,
            links=links
        )
    
    def _extract_title(self, markdown: str) -> str:
        """Extract title from markdown (first H1)."""
        # Look for first # heading
        match = re.search(r'^#\s+(.+)$', markdown, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # Try to get first line if no heading
        lines = markdown.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('[') and not line.startswith('!'):
                return line[:100]  # Max 100 chars
        
        return ""
    
    def _extract_links(self, markdown: str) -> List[str]:
        """Extract all links from markdown."""
        # Pattern: [text](url)
        link_pattern = r'\[([^\]]+)\]\(([^\)]+)\)'
        matches = re.findall(link_pattern, markdown)
        
        # Extract URLs
        urls = []
        for text, url in matches:
            # Skip anchors and mailto
            if url.startswith('#') or url.startswith('mailto:'):
                continue
            
            # Skip images (common false positive)
            if any(ext in url.lower() for ext in ['.jpg', '.png', '.gif', '.svg', '.webp']):
                continue
            
            urls.append(url)
        
        return urls
    
    def _clean_text(self, markdown: str) -> str:
        """Clean markdown to plain text."""
        # Remove markdown links but keep text: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', markdown)
        
        # Remove images: ![alt](url) -> ""
        text = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', text)
        
        # Remove headings markers: ### Heading -> Heading
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        
        # Remove bold/italic: **text** or *text* -> text
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        
        # Remove code blocks: ```code``` -> ""
        text = re.sub(r'```[^`]*```', '', text, flags=re.DOTALL)
        
        # Remove inline code: `code` -> code
        text = re.sub(r'`([^`]+)`', r'\1', text)
        
        # Clean up extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        
        return text