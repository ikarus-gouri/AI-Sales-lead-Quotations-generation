"""
Unified Crawler
---------------
Two-phase crawling approach:
1. Discovery Phase: Crawl website and collect ALL URLs (no classification)
2. Filter Phase: Use Gemini to identify relevant pages based on user intent

File: src/crawlers/crawler.py
"""

import re
import time
from typing import Set, Dict, List, Tuple
from urllib.parse import urlparse, urlunparse
from dataclasses import dataclass

import google.generativeai as genai

from src.utils.http_client import HTTPClient
from src.extractors.link_extractor import LinkExtractor


# ------------------------------------------------------------------
# Data Models
# ------------------------------------------------------------------

@dataclass
class URLInfo:
    """Information about a discovered URL."""
    url: str
    title: str
    snippet: str  # First 500 chars of content
    depth: int


@dataclass
class FilteredURL:
    """URL that passed the filter phase."""
    url: str
    category: str  # PRODUCT | SERVICE | PROJECT | BLOG | OTHER
    confidence: float
    name: str


# ------------------------------------------------------------------
# Unified Crawler
# ------------------------------------------------------------------

class Crawler:
    """
    Two-phase crawler:
    1. Discovery: Crawl site and extract all URLs
    2. Filter: Use Gemini to identify relevant pages
    """

    def __init__(
        self,
        base_url: str,
        http_client: HTTPClient,
        link_extractor: LinkExtractor,
        gemini_api_key: str = None,
        crawl_delay: float = 0.5
    ):
        """
        Initialize crawler.
        
        Args:
            base_url: Starting URL
            http_client: HTTP client for fetching pages
            link_extractor: Link extractor for finding URLs
            gemini_api_key: Gemini API key for filtering phase
            crawl_delay: Delay between requests (seconds)
        """
        self.base_url = base_url
        self.http_client = http_client
        self.link_extractor = link_extractor
        self.crawl_delay = crawl_delay

        # Initialize Gemini
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self.model = None

        # State tracking
        self.discovered_urls: Dict[str, URLInfo] = {}
        self.visited_urls: Set[str] = set()
        self.skipped_urls: Dict[str, str] = {}  # URL -> reason
        self.failed_urls: Dict[str, str] = {}   # URL -> error

        # Statistics
        self.stats = {
            'total_discovered': 0,
            'total_crawled': 0,
            'total_skipped': 0,
            'total_failed': 0,
            'skip_reasons': {}
        }

    # ------------------------------------------------------------------
    # Phase 1: Discovery (No Classification)
    # ------------------------------------------------------------------

    def discover(
        self,
        max_pages: int = 50,
        max_depth: int = 3
    ) -> Dict[str, URLInfo]:
        """
        Phase 1: Crawl website and discover all accessible URLs.
        No classification - just collect URLs with basic info.
        
        Args:
            max_pages: Maximum pages to crawl
            max_depth: Maximum crawl depth
            
        Returns:
            Dictionary of URL -> URLInfo
        """
        print("\n" + "="*80)
        print("PHASE 1: DISCOVERING URLS (No Classification)")
        print("="*80 + "\n")

        to_visit = [(self.base_url, 0)]  # (url, depth)
        normalized_seen = set()

        while to_visit and len(self.visited_urls) < max_pages:
            current_url, depth = to_visit.pop(0)

            # Normalize URL
            normalized_url = self._normalize_url(current_url)

            # Skip if already visited
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
            progress = f"[{len(self.visited_urls)+1}/{max_pages}]"
            print(f"{progress} Crawling (depth {depth}): {current_url}")

            # Fetch the page
            try:
                markdown = self.http_client.scrape_with_jina(current_url)
                if not markdown:
                    raise ValueError("Empty content returned")

                # Extract basic info
                title = self._extract_title(markdown)
                snippet = markdown[:500].strip()

                # Store URL info
                self.discovered_urls[normalized_url] = URLInfo(
                    url=current_url,
                    title=title,
                    snippet=snippet,
                    depth=depth
                )

                self.visited_urls.add(normalized_url)
                self.stats['total_crawled'] += 1
                print(f"  ✓ Fetched: {title[:60]}")

            except Exception as e:
                self.failed_urls[current_url] = str(e)
                self.stats['total_failed'] += 1
                print(f"  ✗ Failed: {e}")
                continue

            # Extract links
            try:
                links = self.link_extractor.extract_from_markdown(markdown, current_url)
                links = list(set(links))  # De-duplicate

                # Add new links to queue
                new_links = 0
                for link in links:
                    normalized_link = self._normalize_url(link)

                    if normalized_link in normalized_seen:
                        continue

                    should_skip_link, _ = self._should_skip_url(link)
                    if should_skip_link:
                        continue

                    if link not in [url for url, _ in to_visit]:
                        to_visit.append((link, depth + 1))
                        new_links += 1
                        self.stats['total_discovered'] += 1

                if new_links > 0:
                    print(f"  → Discovered {new_links} new links")

            except Exception as e:
                self.failed_urls[current_url] = f"link_extraction_error: {e}"
                print(f"  ✗ Link extraction failed: {e}")

            # Rate limiting
            time.sleep(self.crawl_delay)

        self._print_discovery_summary()
        return self.discovered_urls

    # ------------------------------------------------------------------
    # Phase 2: AI Filtering with Gemini
    # ------------------------------------------------------------------

    def filter_by_intent(
        self,
        user_intent: str,
        url_info_dict: Dict[str, URLInfo] = None
    ) -> List[FilteredURL]:
        """
        Phase 2: Use Gemini to filter URLs based on user intent.
        
        Args:
            user_intent: User's intent/prompt
            url_info_dict: Dictionary of URLs to filter (uses discovered_urls if None)
            
        Returns:
            List of filtered URLs with categories
        """
        if url_info_dict is None:
            url_info_dict = self.discovered_urls

        if not url_info_dict:
            print("  ✗ No URLs to filter")
            return []

        if not self.model:
            print("  ✗ Gemini API not configured")
            return []

        print("\n" + "="*80)
        print("PHASE 2: FILTERING URLS WITH GEMINI")
        print("="*80 + "\n")

        url_list = list(url_info_dict.values())
        
        # Process in batches to avoid token limits
        batch_size = 30
        all_filtered: List[FilteredURL] = []

        for i in range(0, len(url_list), batch_size):
            batch = url_list[i:i+batch_size]
            print(f"Processing batch {i//batch_size + 1} ({len(batch)} URLs)...")
            
            filtered = self._filter_batch(batch, user_intent)
            
            # Fallback: If no results and this is the first batch, try lenient mode
            if not filtered and i == 0:
                print(f"  ℹ️  No matches found - retrying with ultra-lenient mode...")
                filtered = self._filter_batch_lenient(batch)
            
            all_filtered.extend(filtered)
            
            time.sleep(1)  # Rate limiting between batches

        # Ultimate fallback: If still no results, include all non-excluded pages
        if not all_filtered and len(url_list) > 0:
            print(f"\n  ⚠️  Zero matches from AI - using fallback mode")
            print(f"     Including all pages except obvious exclusions...\n")
            
            for url_info in url_list:
                # Simple heuristic: exclude only obvious non-content pages
                url_lower = url_info.url.lower()
                should_exclude = any(pattern in url_lower for pattern in [
                    'contact', 'about', 'privacy', 'terms', 'login', 
                    'cart', 'checkout', 'account', 'policy'
                ])
                
                if not should_exclude:
                    all_filtered.append(FilteredURL(
                        url=url_info.url,
                        category="UNKNOWN",
                        confidence=0.5,
                        name=url_info.title or "Unknown Page"
                    ))
            
            print(f"  ℹ️  Fallback mode included {len(all_filtered)} pages")

        self._print_filter_summary(all_filtered)
        return all_filtered

    def _filter_batch(
        self,
        url_batch: List[URLInfo],
        user_intent: str
    ) -> List[FilteredURL]:
        """Filter a batch of URLs using Gemini."""
        
        # Build URL list for prompt
        url_list = ""
        for i, info in enumerate(url_batch, 1):
            url_list += f"{i}. URL: {info.url}\n"
            url_list += f"   Title: {info.title}\n"
            url_list += f"   Preview: {info.snippet[:150]}...\n\n"

        prompt = f"""
You are analyzing web pages to extract valuable business content.

USER'S EXTRACTION GOAL:
{user_intent}

PAGES TO ANALYZE:
{url_list}

CRITICAL: Be EXTREMELY LENIENT. When in doubt, INCLUDE the page.

ALWAYS INCLUDE these page types:
✅ Products/Services: Any page describing what the business sells or does
✅ Projects/Work: Portfolio, gallery, case studies, "our work", examples
✅ Details: Specifications, features, pricing, descriptions
✅ Offerings: What they make/build/provide/install
✅ Catalogs: Lists of items, categories, collections
✅ Configurators: Customization, options, variants, "build your own"

CLUES TO LOOK FOR (be generous with interpretation):
- Page titles mentioning products, services, projects, work
- URLs containing: product, service, project, portfolio, gallery, work, item, catalog
- Content previews mentioning: what we do, our services, products, options, prices
- Any page that ISN'T obviously: contact, about, privacy, terms, blog/article

⚠️ CONFIGURATOR DETECTION (look for these signals):
- Words: customize, configure, choose, select, options, variants, colors, sizes
- Any page with selection/customization UI
- Product builders or option pickers

MATCHING RULES:
1. Default to HIGH or MEDIUM relevance unless clearly irrelevant
2. If user intent mentions "products", include ANY page that might show products
3. If user intent mentions "projects", include galleries, portfolios, case studies
4. If user intent mentions "services", include service description pages
5. Be LENIENT with keyword matching - close is good enough
6. When uncertain, mark as MEDIUM relevance (not LOW)

ONLY mark as LOW relevance if the page is CLEARLY:
- About Us / Company history (unless user asks for this)
- Contact information only
- Privacy policy / Terms
- Pure blog/news articles
- FAQs without product info

OUTPUT JSON with ALL {len(url_batch)} URLs:

[
  {{
    "url_number": 1,
    "category": "PRODUCT|SERVICE|PROJECT|GALLERY|CONFIGURATOR|LISTING|INFO",
    "relevance": "HIGH|MEDIUM|LOW",
    "confidence": 0.85,
    "has_configurator": false,
    "reasoning": "why included/excluded",
    "signals": ["keyword1", "keyword2"],
    "name": "descriptive name"
  }}
]

REMEMBER: Better to include too many than miss important pages. Be LENIENT!
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,  # Slightly higher for more flexibility
                    "response_mime_type": "application/json"
                }
            )

            import json
            classifications = json.loads(response.text)

            filtered = []
            for item in classifications:
                url_num = item.get("url_number", 0) - 1

                if 0 <= url_num < len(url_batch):
                    relevance = item.get("relevance", "LOW")
                    has_configurator = item.get("has_configurator", False)
                    
                    # LENIENT: Include HIGH and MEDIUM relevance
                    # Also include LOW relevance if it has a configurator
                    if relevance in ["HIGH", "MEDIUM"] or (relevance == "LOW" and has_configurator):
                        category = item.get("category", "OTHER")
                        
                        # Add configurator flag to category if detected
                        if has_configurator:
                            category = f"{category}_CONFIGURATOR"
                        
                        filtered_url = FilteredURL(
                            url=url_batch[url_num].url,
                            category=category,
                            confidence=float(item.get("confidence", 0.0)),
                            name=item.get("name", "")
                        )
                        filtered.append(filtered_url)
                        
                        # Print configurator detection
                        if has_configurator:
                            print(f"  🎛️  CONFIGURATOR DETECTED: {url_batch[url_num].url}")
                            signals = item.get("signals", [])
                            if signals:
                                print(f"      Signals: {', '.join(signals[:3])}")

            return filtered

        except Exception as e:
            print(f"  ✗ Batch filtering failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _filter_batch_lenient(self, url_batch: List[URLInfo]) -> List[FilteredURL]:
        """Ultra-lenient filtering - include almost everything."""
        
        url_list = ""
        for i, info in enumerate(url_batch, 1):
            url_list += f"{i}. {info.url} - {info.title}\n"

        prompt = f"""
Analyze these web pages. Include ANY page that might have business content.

{url_list}

ONLY EXCLUDE if the page is clearly one of these:
- Contact form / Contact us
- About company / Team bios
- Privacy Policy / Terms
- Login / Account pages
- Cart / Checkout pages

For EVERY OTHER page, include it as MEDIUM relevance.

Return JSON array with {len(url_batch)} items:
[
  {{"url_number": 1, "relevance": "MEDIUM|LOW", "category": "BUSINESS_CONTENT", "name": "page name"}}
]
"""

        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )

            import json
            classifications = json.loads(response.text)

            filtered = []
            for item in classifications:
                url_num = item.get("url_number", 0) - 1
                if 0 <= url_num < len(url_batch):
                    if item.get("relevance") == "MEDIUM":
                        filtered.append(FilteredURL(
                            url=url_batch[url_num].url,
                            category="BUSINESS_CONTENT",
                            confidence=0.7,
                            name=item.get("name", url_batch[url_num].title)
                        ))
            
            return filtered

        except Exception as e:
            print(f"  ✗ Lenient filtering failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Combined API (Discovery + Filter in one call)
    # ------------------------------------------------------------------

    def crawl(
        self,
        user_intent: str = None,
        max_pages: int = 50,
        max_depth: int = 3
    ) -> Dict[str, any]:
        """
        Combined crawl method: discover + filter.
        
        Returns:
            Dictionary with:
            - all_urls: All discovered URLs
            - filtered_urls: URLs matching intent (if intent provided)
            - stats: Statistics
        """
        # Phase 1: Discovery
        all_urls = self.discover(max_pages=max_pages, max_depth=max_depth)

        # Phase 2: Filtering (if intent provided)
        filtered = []
        if user_intent and self.model:
            filtered = self.filter_by_intent(user_intent, all_urls)

        return {
            'all_urls': all_urls,
            'filtered_urls': filtered,
            'stats': {
                'total_discovered': len(all_urls),
                'total_filtered': len(filtered),
                'categories': self._count_categories(filtered)
            }
        }

    # ------------------------------------------------------------------
    # URL Filtering & Normalization
    # ------------------------------------------------------------------

    def _should_skip_url(self, url: str) -> Tuple[bool, str]:
        """
        Determine if URL should be skipped.
        
        Returns:
            (should_skip, reason)
        """
        url_lower = url.lower()

        # Image files
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp']
        for ext in image_extensions:
            if url_lower.endswith(ext):
                return (True, f"image_file")

        # Other media
        media_extensions = ['.pdf', '.mp4', '.zip', '.doc', '.mp3', '.wav']
        for ext in media_extensions:
            if url_lower.endswith(ext):
                return (True, f"media_file")

        # WordPress media
        if '/wp-content/uploads/' in url_lower:
            return (True, "wordpress_upload")

        # Skip patterns (including contact/social media to avoid infinite crawl)
        skip_patterns = {
            '/feed/': 'rss_feed',
            '/rss/': 'rss_feed',
            '/wp-json/': 'api_endpoint',
            '/wp-login.php': 'login_page',
            '/wp-admin/': 'admin_page',
            '/login': 'login_page',
            '/signin': 'login_page',
            '/cart/': 'cart_page',
            '/checkout/': 'checkout_page',
            '/my-account/': 'account_page',
            '/contact': 'contact_page',  # Avoid contact pages (social media links)
            '/contact-us': 'contact_page',
            'contact.html': 'contact_page',
            '/privacy': 'policy_page',
            '/terms': 'policy_page',
            '/returns': 'policy_page',
            '/shipping': 'policy_page',
            'facebook.com': 'social_media',
            'twitter.com': 'social_media',
            'instagram.com': 'social_media',
            'linkedin.com': 'social_media',
            'youtube.com': 'social_media',
            'pinterest.com': 'social_media',
            'tiktok.com': 'social_media',
        }

        for pattern, reason in skip_patterns.items():
            if pattern in url_lower:
                return (True, reason)

        # Check if URL points to external domain (social media, etc.)
        if not self._same_domain(self.base_url, url):
            return (True, "external_domain")

        return (False, "")

    def _normalize_url(self, url: str) -> str:
        """
        Normalize URL to prevent duplicates.
        
        Removes:
        - Trailing slashes
        - Query parameters
        - URL fragments
        """
        parsed = urlparse(url)

        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip('/')

        normalized = urlunparse((
            parsed.scheme,
            netloc,
            path,
            '',  # No params
            '',  # No query
            ''   # No fragment
        ))

        return normalized

    def _same_domain(self, url1: str, url2: str) -> bool:
        """Check if two URLs are on the same domain."""
        domain1 = urlparse(url1).netloc.lower()
        domain2 = urlparse(url2).netloc.lower()
        
        # Remove www. for comparison
        domain1 = domain1.replace('www.', '')
        domain2 = domain2.replace('www.', '')
        
        return domain1 == domain2

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _extract_title(self, markdown: str) -> str:
        """Extract page title from markdown."""
        for line in markdown.split('\n')[:20]:
            line = line.strip()
            if line.startswith('# '):
                return line.lstrip('#').strip()
        return "Untitled Page"

    def _count_categories(self, filtered: List[FilteredURL]) -> Dict[str, int]:
        """Count URLs by category."""
        counts = {}
        for item in filtered:
            counts[item.category] = counts.get(item.category, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Summary Reports
    # ------------------------------------------------------------------

    def _print_discovery_summary(self):
        """Print discovery phase summary."""
        print(f"\n{'='*80}")
        print("DISCOVERY PHASE COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Statistics:")
        print(f"   URLs discovered: {self.stats['total_discovered']}")
        print(f"   Pages crawled: {self.stats['total_crawled']}")
        print(f"   URLs skipped: {self.stats['total_skipped']}")
        print(f"   Failed fetches: {self.stats['total_failed']}")

        if self.stats['skip_reasons']:
            print(f"\n📋 Skip Reasons:")
            sorted_reasons = sorted(
                self.stats['skip_reasons'].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for reason, count in sorted_reasons[:10]:
                print(f"   {reason}: {count}")

        print(f"{'='*80}\n")

    def _print_filter_summary(self, filtered: List[FilteredURL]):
        """Print filter phase summary."""
        print(f"\n{'='*80}")
        print("FILTER PHASE COMPLETE")
        print(f"{'='*80}")
        print(f"✅ Matched URLs: {len(filtered)}")

        if filtered:
            # Count configurators
            configurators = [item for item in filtered if "CONFIGURATOR" in item.category]
            if configurators:
                print(f"🎛️  Configurators Detected: {len(configurators)}")
            
            # Count by category
            categories = self._count_categories(filtered)
            print(f"\n📂 By Category:")
            for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                # Add emoji indicators
                emoji = "🎛️" if "CONFIGURATOR" in category else "📄"
                print(f"   {emoji} {category}: {count}")

            # Show sample results
            print(f"\n🔍 Sample Results:")
            
            # Show configurators first
            shown = 0
            if configurators and shown < 5:
                print(f"\n   🎛️  CONFIGURATOR PAGES:")
                for i, item in enumerate(configurators[:2], 1):
                    print(f"   {i}. {item.name}")
                    print(f"      {item.url}")
                    print(f"      Confidence: {item.confidence:.0%}")
                    shown += 1
            
            # Show other items
            other_items = [item for item in filtered if "CONFIGURATOR" not in item.category]
            if other_items and shown < 5:
                remaining = 5 - shown
                if configurators:
                    print(f"\n   📄 OTHER PAGES:")
                for i, item in enumerate(other_items[:remaining], shown + 1):
                    print(f"   {i}. [{item.category}] {item.name}")
                    print(f"      {item.url}")
                    print(f"      Confidence: {item.confidence:.0%}")
                    shown += 1

            if len(filtered) > 5:
                print(f"\n   ... and {len(filtered) - 5} more")
        else:
            print("\n⚠️  No relevant URLs found. Try:")
            print("   • Using a more general intent")
            print("   • Increasing max_pages to discover more URLs")
            print("   • Checking if the website has the content you're looking for")

        print(f"{'='*80}\n")

    def save_results(self, filepath: str, filtered: List[FilteredURL] = None):
        """Save crawl results to JSON."""
        import json

        results = {
            'base_url': self.base_url,
            'statistics': self.stats,
            'all_urls': [
                {
                    'url': info.url,
                    'title': info.title,
                    'depth': info.depth
                }
                for info in self.discovered_urls.values()
            ],
            'filtered_urls': [
                {
                    'url': item.url,
                    'category': item.category,
                    'confidence': item.confidence,
                    'name': item.name
                }
                for item in (filtered or [])
            ],
            'skipped_urls': self.skipped_urls,
            'failed_urls': self.failed_urls
        }

        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"✓ Results saved: {filepath}")
