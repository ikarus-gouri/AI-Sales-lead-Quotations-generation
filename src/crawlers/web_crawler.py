"""Enhanced web crawler with robust URL detection and logging.

File: src/crawlers/web_crawler.py (UPDATED)
"""

import time
from typing import Set, Tuple, Dict, List
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..classifiers.base_classifier import BaseClassifier


class WebCrawler:
    """
    Enhanced web crawler with:
    - Better URL detection and filtering
    - Detailed logging of skipped URLs with reasons
    - Smart duplicate detection
    - Progress tracking
    """
    
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
        
        # State tracking
        self.visited_pages: Set[str] = set()
        self.product_pages: Set[str] = set()
        self.skipped_urls: Dict[str, str] = {}  # URL -> reason
        self.failed_urls: Dict[str, str] = {}   # URL -> error
        self.page_cache: Dict[str, str] = {}    # URL -> markdown (for reuse)
        
        # Statistics
        self.stats = {
            'total_discovered': 0,
            'total_crawled': 0,
            'total_skipped': 0,
            'total_failed': 0,
            'products_found': 0,
            'skip_reasons': {}
        }
    
    def _should_skip_url(self, url: str) -> Tuple[bool, str]:
        """
        Determine if URL should be skipped with detailed reason.
        
        Args:
            url: The URL to check
            
        Returns:
            (should_skip, reason)
        """
        url_lower = url.lower()
        
        # Check for image files
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp']
        for ext in image_extensions:
            if url_lower.endswith(ext):
                return (True, f"image_file_{ext}")
        
        # Check for other media
        media_extensions = ['.pdf', '.mp4', '.avi', '.zip', '.doc', '.docx', '.mp3', '.wav']
        for ext in media_extensions:
            if url_lower.endswith(ext):
                return (True, f"media_file_{ext}")
        
        # Check for WordPress media uploads
        if '/wp-content/uploads/' in url_lower:
            return (True, "wordpress_upload")
        
        # Check for common non-page URLs
        skip_patterns = {
            '/feed/': 'rss_feed',
            '/rss/': 'rss_feed',
            '/wp-json/': 'api_endpoint',
            '/xmlrpc.php': 'xml_rpc',
            '/wp-login.php': 'login_page',
            '/wp-admin/': 'admin_page',
            '/cart/': 'cart_page',
            '/checkout/': 'checkout_page',
            '/my-account/': 'account_page',
            '/customer-service/': 'service_page',
            '/privacy-policy': 'policy_page',
            '/terms-of-service': 'policy_page',
            '/returns': 'policy_page',
            '/shipping': 'policy_page'
        }
        
        for pattern, reason in skip_patterns.items():
            if pattern in url_lower:
                return (True, reason)
        
        # Check for pagination (usually not product pages)
        if re.search(r'/page/\d+', url_lower) or '?page=' in url_lower:
            return (True, "pagination")
        
        # Check for tag/category archives (usually listings, not products)
        archive_patterns = ['/tag/', '/category/', '/author/']
        for pattern in archive_patterns:
            if pattern in url_lower:
                return (True, "archive_page")
        
        return (False, "")
    
    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL to prevent duplicate crawling.
        
        Removes:
        - Trailing slashes (standardize)
        - Query parameters (usually not needed)
        - URL fragments (#section)
        """
        from urllib.parse import urlparse, urlunparse
        
        parsed = urlparse(url)
        
        # Remove trailing slash from path
        path = parsed.path.rstrip('/')
        
        # Reconstruct without query/fragment
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            path,
            '',  # No params
            '',  # No query (comment this out if you need query params)
            ''   # No fragment
        ))
        
        return normalized
    
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
        print("ENHANCED WEB CRAWLER - DISCOVERING PAGES")
        print("="*80 + "\n")
        
        to_visit = [(self.base_url, 0)]  # (url, depth)
        normalized_seen = set()  # Track normalized URLs
        
        while to_visit and len(self.visited_pages) < max_pages:
            current_url, depth = to_visit.pop(0)
            
            # Normalize URL
            normalized_url = self._normalize_url(current_url)
            
            # Skip if already visited (by normalized version)
            if normalized_url in normalized_seen:
                continue
            
            normalized_seen.add(normalized_url)
            
            # Skip if too deep
            if depth > max_depth:
                self.skipped_urls[current_url] = "max_depth_exceeded"
                continue
            
            # Check if URL should be skipped
            should_skip, reason = self._should_skip_url(current_url)
            if should_skip:
                self.skipped_urls[current_url] = reason
                self.stats['total_skipped'] += 1
                self.stats['skip_reasons'][reason] = self.stats['skip_reasons'].get(reason, 0) + 1
                print(f"  ⏭️  Skipping ({reason}): {current_url}")
                continue
            
            # Progress indicator
            progress = f"[{len(self.visited_pages)+1}/{max_pages}]"
            print(f"\n{progress} Crawling (depth {depth}): {current_url}")
            
            # Scrape the page with error handling
            try:
                markdown = self.http_client.scrape_with_jina(current_url)
                if not markdown:
                    raise ValueError("Empty content returned from HTTP client")
            except Exception as e:
                self.failed_urls[current_url] = str(e)
                self.stats['total_failed'] += 1
                print(f"  ✗ Failed to fetch content: {e}")
                self.visited_pages.add(current_url)
                continue

            # Cache the content for later reuse
            self.page_cache[current_url] = markdown
            self.visited_pages.add(current_url)
            self.stats['total_crawled'] += 1

            # Classify the page with error handling
            try:
                if hasattr(self.classifier, 'classify'):
                    classification = self.classifier.classify(current_url, markdown)
                    page_type = classification.page_type
                    confidence = classification.confidence

                    if page_type == 'product':
                        self.product_pages.add(current_url)
                        self.stats['products_found'] += 1
                        print(f"  ✓ PRODUCT PAGE DETECTED")
                        print(f"    Confidence: {confidence:.0%}")
                        if classification.signals.get('product'):
                            print(f"    Signals: {classification.signals['product']}")
                    elif page_type == 'list':
                        print(f"  📋 LIST PAGE (collection/category)")
                        print(f"    Confidence: {confidence:.0%}")
                        if classification.signals.get('list', {}).get('product_links'):
                            link_count = classification.signals['list']['product_links']
                            print(f"    Contains {link_count} product links")
                    elif page_type == 'blog':
                        print(f"  📝 BLOG PAGE (article/post)")
                        print(f"    Confidence: {confidence:.0%}")
                    else:
                        print(f"    Other page type")
                else:
                    # Legacy classifier
                    is_product = self.classifier.is_product_page(current_url, markdown)
                    if is_product:
                        self.product_pages.add(current_url)
                        self.stats['products_found'] += 1
                        print(f"  ✓ PRODUCT PAGE DETECTED")
                    else:
                        print(f"  ○ Not a product page")
            except Exception as e:
                self.failed_urls[current_url] = f"classifier_error: {e}"
                self.stats['total_failed'] += 1
                print(f"  ✗ Classification failed: {e}")

            # Extract links with error handling
            try:
                links = self.link_extractor.extract_from_markdown(markdown, current_url)
            except Exception as e:
                links = []
                self.failed_urls[current_url] = f"link_extraction_error: {e}"
                self.stats['total_failed'] += 1
                print(f"  ✗ Link extraction failed: {e}")
            
            # Add new links to visit queue
            new_links_added = 0
            for link in links:
                normalized_link = self._normalize_url(link)
                
                # Skip if already seen
                if normalized_link in normalized_seen:
                    continue
                
                # Double-check the link is valid
                should_skip_link, _ = self._should_skip_url(link)
                if should_skip_link:
                    continue
                
                # Check if already in queue
                if link not in [url for url, _ in to_visit]:
                    to_visit.append((link, depth + 1))
                    new_links_added += 1
                    self.stats['total_discovered'] += 1
            
            if new_links_added > 0:
                print(f"  → Discovered {new_links_added} new links")
            
            # Be nice to the server
            time.sleep(self.crawl_delay)
        
        # Print comprehensive summary
        self._print_crawl_summary()
        
        return self.product_pages
    
    def _print_crawl_summary(self):
        """Print detailed crawl summary."""
        print(f"\n{'='*80}")
        print("CRAWL SUMMARY")
        print(f"{'='*80}")
        print(f"📊 Statistics:")
        print(f"   Total URLs discovered: {self.stats['total_discovered']}")
        print(f"   Total pages crawled: {self.stats['total_crawled']}")
        print(f"   Product pages found: {self.stats['products_found']}")
        print(f"   URLs skipped: {self.stats['total_skipped']}")
        print(f"   Failed fetches: {self.stats['total_failed']}")
        
        # Skip reasons breakdown
        if self.stats['skip_reasons']:
            print(f"\n📋 Skip Reasons:")
            sorted_reasons = sorted(
                self.stats['skip_reasons'].items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            for reason, count in sorted_reasons[:10]:
                print(f"   {reason}: {count}")
            if len(sorted_reasons) > 10:
                remaining = sum(count for _, count in sorted_reasons[10:])
                print(f"   ... and {remaining} more")
        
        # Show some product pages found
        if self.product_pages:
            print(f"\n✅ Product Pages Found ({len(self.product_pages)}):")
            for i, url in enumerate(list(self.product_pages)[:5], 1):
                print(f"   {i}. {url}")
            if len(self.product_pages) > 5:
                print(f"   ... and {len(self.product_pages) - 5} more")
        
        # Show some skipped URLs (for debugging)
        if self.skipped_urls:
            print(f"\n⏭️  Sample Skipped URLs:")
            skip_samples = list(self.skipped_urls.items())[:3]
            for url, reason in skip_samples:
                print(f"   {url}")
                print(f"     → Reason: {reason}")
        
        # Show failed URLs
        if self.failed_urls:
            print(f"\n❌ Failed URLs ({len(self.failed_urls)}):")
            for url, error in list(self.failed_urls.items())[:3]:
                print(f"   {url}")
                print(f"     → Error: {error}")
        
        print(f"{'='*80}\n")
    
    def save_crawl_report(self, filepath: str):
        """Save detailed crawl report to JSON."""
        import json
        
        report = {
            'statistics': self.stats,
            'product_pages': list(self.product_pages),
            'visited_pages': list(self.visited_pages),
            'skipped_urls': self.skipped_urls,
            'failed_urls': self.failed_urls,
            'total_discovered': self.stats['total_discovered'],
            'total_crawled': self.stats['total_crawled'],
            'efficiency': {
                'product_rate': (self.stats['products_found'] / max(self.stats['total_crawled'], 1)) * 100,
                'skip_rate': (self.stats['total_skipped'] / max(self.stats['total_discovered'], 1)) * 100,
                'failure_rate': (self.stats['total_failed'] / max(self.stats['total_crawled'], 1)) * 100
            }
        }
        
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✓ Crawl report saved: {filepath}")
    
    def get_page_content(self, url: str) -> str:
        """
        Get cached page content if available.
        
        This prevents re-fetching pages during the scraping phase.
        
        Args:
            url: Page URL
            
        Returns:
            Cached markdown content or empty string
        """
        normalized = self._normalize_url(url)
        return self.page_cache.get(normalized, self.page_cache.get(url, ""))


# ====================================================================
# Import fix for regex
# ====================================================================

import re