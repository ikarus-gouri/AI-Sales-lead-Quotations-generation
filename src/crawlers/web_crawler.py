"""Web crawler for discovering pages."""

import time
from typing import Set, Tuple
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..classifiers.base_classifier import BaseClassifier


class WebCrawler:
    """Crawl website to discover pages and identify product pages."""
    
    def __init__(
        self,
        base_url: str,
        http_client: HTTPClient,
        link_extractor: LinkExtractor,
        classifier: BaseClassifier,
        crawl_delay: float = 0.5
    ):
        """
        Initialize web crawler.
        
        Args:
            base_url: The base URL to crawl
            http_client: HTTP client for making requests
            link_extractor: Link extractor for finding URLs
            classifier: Page classifier
            crawl_delay: Delay between requests in seconds
        """
        self.base_url = base_url
        self.http_client = http_client
        self.link_extractor = link_extractor
        self.classifier = classifier
        self.crawl_delay = crawl_delay
        
        self.visited_pages: Set[str] = set()
        self.product_pages: Set[str] = set()
        self.skipped_urls: Set[str] = set()  # Track skipped URLs
    
    def _should_skip_url(self, url: str) -> tuple[bool, str]:
        """
        Determine if URL should be skipped with reason.
        
        Args:
            url: The URL to check
            
        Returns:
            (should_skip, reason)
        """
        url_lower = url.lower()
        
        # Check for image files
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp']
        if any(url_lower.endswith(ext) for ext in image_extensions):
            return (True, "image file")
        
        # Check for other media
        media_extensions = ['.pdf', '.mp4', '.avi', '.zip', '.doc', '.docx']
        if any(url_lower.endswith(ext) for ext in media_extensions):
            return (True, "media file")
        
        # Check for WordPress media uploads
        if '/wp-content/uploads/' in url_lower:
            return (True, "WordPress upload")
        
        # Check for other common non-page URLs
        skip_patterns = [
            '/feed/', '/rss/', '/wp-json/', '/xmlrpc.php',
            '/wp-login.php', '/wp-admin/', '/cart/', '/checkout/', '/location/'
        ]
        for pattern in skip_patterns:
            if pattern in url_lower:
                return (True, f"matches pattern: {pattern}")
        
        return (False, "")
    
    def crawl(self, max_pages: int = 50, max_depth: int = 3) -> Set[str]:
        """
        Crawl the website to discover product pages.
        
        Args:
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum crawl depth
            
        Returns:
            Set of product page URLs
        """
        print("\n" + "="*80)
        print("CRAWLING WEBSITE TO DISCOVER PRODUCT PAGES")
        print("="*80 + "\n")
        
        to_visit = [(self.base_url, 0)]  # (url, depth)
        
        while to_visit and len(self.visited_pages) < max_pages:
            current_url, depth = to_visit.pop(0)
            
            # Skip if already visited
            if current_url in self.visited_pages:
                continue
            
            # Skip if too deep
            if depth > max_depth:
                continue
            
            # Check if URL should be skipped
            should_skip, reason = self._should_skip_url(current_url)
            if should_skip:
                self.skipped_urls.add(current_url)
                print(f" Skipping ({reason}): {current_url}")
                continue
            
            print(f"Crawling [{len(self.visited_pages)+1}/{max_pages}] (depth {depth}): {current_url}")
            
            # Scrape the page
            markdown = self.http_client.scrape_with_jina(current_url)
            
            if not markdown:
                self.visited_pages.add(current_url)
                continue
            
            self.visited_pages.add(current_url)
            
            # Check if it's a product page
            if self.classifier.is_product_page(current_url, markdown):
                self.product_pages.add(current_url)
                print(f" PRODUCT PAGE DETECTED: {current_url}")
            
            # Extract links for further crawling
            links = self.link_extractor.extract_from_markdown(markdown, current_url)
            
            # Add new links to visit queue
            new_links_count = 0
            for link in links:
                # Double-check the link is valid
                should_skip_link, _ = self._should_skip_url(link)
                if should_skip_link:
                    continue
                    
                if link not in self.visited_pages and link not in [url for url, _ in to_visit]:
                    to_visit.append((link, depth + 1))
                    new_links_count += 1
            
            if new_links_count > 0:
                print(f"  Found {new_links_count} new links to crawl")
            
            # Be nice to the server
            time.sleep(self.crawl_delay)
        
        print(f"\n{'='*80}")
        print("CRAWL SUMMARY")
        print(f"{'='*80}")
        print(f"✓ Pages crawled: {len(self.visited_pages)}")
        print(f"✓ Product pages found: {len(self.product_pages)}")
        print(f" URLs skipped (images/media): {len(self.skipped_urls)}")
        print(f"{'='*80}\n")
        
        return self.product_pages