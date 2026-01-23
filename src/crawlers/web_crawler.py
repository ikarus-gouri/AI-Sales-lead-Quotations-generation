"""Intelligent web crawler with URL pattern learning."""

import time
from typing import Set, Tuple, Optional
from ..utils.http_client import HTTPClient
from ..extractors.link_extractor import LinkExtractor
from ..classifiers.base_classifier import BaseClassifier
from ..url_intelligence.pattern_learner import URLPatternLearner, SiteProfile
from ..url_intelligence.url_router import URLRouter


class IntelligentWebCrawler:
    """
    Crawl website with URL intelligence to minimize unnecessary classification.
    
    This crawler:
    1. Learns URL patterns as it crawls
    2. Routes URLs intelligently 
    3. Only classifies when uncertain
    4. Dramatically reduces AI/classification calls
    """
    
    def __init__(
        self,
        base_url: str,
        http_client: HTTPClient,
        link_extractor: LinkExtractor,
        classifier: BaseClassifier,
        crawl_delay: float = 0.5,
        learning_phase_pages: int = 10  # Learn patterns from first N pages
    ):
        """
        Initialize intelligent web crawler.
        
        Args:
            base_url: The base URL to crawl
            http_client: HTTP client for making requests
            link_extractor: Link extractor for finding URLs
            classifier: Page classifier (used only when needed)
            crawl_delay: Delay between requests in seconds
            learning_phase_pages: Number of pages to crawl before pattern learning
        """
        self.base_url = base_url
        self.http_client = http_client
        self.link_extractor = link_extractor
        self.classifier = classifier
        self.crawl_delay = crawl_delay
        self.learning_phase_pages = learning_phase_pages
        
        # URL intelligence
        self.pattern_learner = URLPatternLearner()
        self.url_router: Optional[URLRouter] = None
        self.site_profile: Optional[SiteProfile] = None
        
        # State tracking
        self.visited_pages: Set[str] = set()
        self.product_pages: Set[str] = set()
        self.customization_pages: Set[str] = set()
        self.category_pages: Set[str] = set()
        self.skipped_urls: Set[str] = set()
        
        # Page cache (avoid re-fetching)
        self.page_cache: dict[str, str] = {}
        
        # Statistics
        self.stats = {
            'pages_fetched': 0,
            'classifications_performed': 0,
            'classifications_skipped': 0,
            'patterns_learned': 0
        }
    
    def crawl(self, max_pages: int = 50, max_depth: int = 3) -> Set[str]:
        """
        Crawl the website intelligently to discover product pages.
        
        Args:
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum crawl depth
            
        Returns:
            Set of product page URLs
        """
        print("\n" + "="*80)
        print("INTELLIGENT CRAWLING WITH URL PATTERN LEARNING")
        print("="*80 + "\n")
        
        to_visit = [(self.base_url, 0, 100)]  # (url, depth, priority)
        learning_phase = True
        
        while to_visit and len(self.visited_pages) < max_pages:
            # Sort by priority (highest first)
            to_visit.sort(key=lambda x: x[2], reverse=True)
            
            current_url, depth, priority = to_visit.pop(0)
            
            # Skip if already visited
            if current_url in self.visited_pages:
                continue
            
            # Skip if too deep
            if depth > max_depth:
                continue
            
            # Check if URL should be skipped (basic filters)
            should_skip, reason = self._should_skip_url(current_url)
            if should_skip:
                self.skipped_urls.add(current_url)
                print(f"⊘ Skipping ({reason}): {current_url}")
                continue
            
            # URL Intelligence: Route the URL
            if self.url_router:
                route, confidence = self.url_router.route(current_url)
                
                # Skip ignored URLs
                if route == "IGNORE":
                    self.skipped_urls.add(current_url)
                    print(f"⊘ Skipping (pattern: IGNORE, {confidence:.0%}): {current_url}")
                    continue
                
                # Log routing decision
                print(f"🧭 Routing [{len(self.visited_pages)+1}/{max_pages}] (depth {depth}, {route}, {confidence:.0%}): {current_url}")
            else:
                print(f"Crawling [{len(self.visited_pages)+1}/{max_pages}] (depth {depth}, LEARNING): {current_url}")
            
            # Fetch the page
            markdown = self.http_client.scrape_with_jina(current_url)
            self.stats['pages_fetched'] += 1
            
            if not markdown:
                self.visited_pages.add(current_url)
                continue
            
            # Cache the content
            self.page_cache[current_url] = markdown
            self.visited_pages.add(current_url)
            
            # Determine page type
            page_type = self._determine_page_type(current_url, markdown)
            
            # Record observation for learning
            self.pattern_learner.observe(current_url, page_type)
            
            # Categorize page
            if page_type == "product":
                self.product_pages.add(current_url)
                print(f"  ✓ PRODUCT PAGE")
                
                # Look for customization links
                if self.url_router:
                    custom_links = self.url_router.find_customization_links(current_url, markdown)
                    if custom_links:
                        print(f"  → Found {len(custom_links)} potential customization links")
                        for custom_url in custom_links[:3]:  # Add top 3
                            to_visit.append((custom_url, depth, 95))
            
            elif page_type == "customization":
                self.customization_pages.add(current_url)
                print(f"  ✓ CUSTOMIZATION PAGE")
            
            elif page_type == "category":
                self.category_pages.add(current_url)
                print(f"  → Category page")
            
            # Learning phase: Train patterns after initial pages
            if learning_phase and len(self.visited_pages) >= self.learning_phase_pages:
                print(f"\n{'='*80}")
                print(f"LEARNING PHASE COMPLETE - TRAINING URL PATTERNS")
                print(f"{'='*80}\n")
                
                self.site_profile = self.pattern_learner.learn_patterns(min_samples=2)
                self.url_router = URLRouter(self.site_profile)
                
                self._print_learned_patterns()
                
                learning_phase = False
                print(f"\n{'='*80}")
                print(f"INTELLIGENT ROUTING ENABLED")
                print(f"{'='*80}\n")
            
            # Extract links for further crawling
            links = self.link_extractor.extract_from_markdown(markdown, current_url)
            
            # Add new links to visit queue with priority
            new_links_count = 0
            for link in links:
                # Double-check the link is valid
                should_skip_link, _ = self._should_skip_url(link)
                if should_skip_link:
                    continue
                
                if link not in self.visited_pages and link not in [url for url, _, _ in to_visit]:
                    # Calculate priority
                    if self.url_router:
                        link_priority = self.url_router.get_priority(link)
                    else:
                        link_priority = 50  # Default priority during learning
                    
                    to_visit.append((link, depth + 1, link_priority))
                    new_links_count += 1
            
            if new_links_count > 0:
                print(f"  Found {new_links_count} new links to crawl")
            
            # Be nice to the server
            time.sleep(self.crawl_delay)
        
        # Print summary
        self._print_summary()
        
        # Return product pages (including customization pages)
        all_product_pages = self.product_pages | self.customization_pages
        return all_product_pages
    
    def _determine_page_type(self, url: str, markdown: str) -> str:
        """
        Determine page type using URL intelligence or classification.
        
        Returns: "product", "customization", "category", or "ignore"
        """
        # If we have a router, use it first
        if self.url_router:
            route, confidence = self.url_router.route(url)
            
            # High confidence - trust the pattern
            if confidence >= 0.7:
                self.stats['classifications_skipped'] += 1
                return route.lower()
            
            # Medium confidence - use as hint but verify
            if confidence >= 0.4:
                # Quick sanity check with classifier
                if self.classifier.is_product_page(url, markdown):
                    self.stats['classifications_performed'] += 1
                    # Trust classifier, but note pattern might be wrong
                    return "product"
                else:
                    self.stats['classifications_performed'] += 1
                    return "category"
        
        # Low/no confidence - full classification needed
        self.stats['classifications_performed'] += 1
        
        # Check if product page
        if self.classifier.is_product_page(url, markdown):
            # Is it a customization page?
            if self._is_customization_page(url, markdown):
                return "customization"
            return "product"
        
        return "category"
    
    def _is_customization_page(self, url: str, markdown: str) -> bool:
        """Quick check if page is customization-focused."""
        url_lower = url.lower()
        markdown_lower = markdown.lower()
        
        customize_keywords = ['customize', 'configurator', 'inquiry', 'build-your']
        
        url_match = any(kw in url_lower for kw in customize_keywords)
        content_match = sum(1 for kw in customize_keywords if kw in markdown_lower) >= 2
        
        return url_match or content_match
    
    def _should_skip_url(self, url: str) -> tuple[bool, str]:
        """
        Basic URL filtering (before pattern matching).
        
        Returns: (should_skip, reason)
        """
        url_lower = url.lower()
        
        # Check for file extensions
        skip_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico',
            '.pdf', '.mp4', '.zip', '.doc', '.docx'
        ]
        if any(url_lower.endswith(ext) for ext in skip_extensions):
            return (True, "media file")
        
        # Check for WordPress uploads
        if '/wp-content/uploads/' in url_lower:
            return (True, "WordPress upload")
        
        # Check for common non-page URLs
        skip_patterns = [
            '/feed/', '/rss/', '/wp-json/', '/xmlrpc.php',
            '/wp-login.php', '/wp-admin/', '/cart/', '/checkout/'
        ]
        for pattern in skip_patterns:
            if pattern in url_lower:
                return (True, f"pattern: {pattern}")
        
        return (False, "")
    
    def _print_learned_patterns(self):
        """Print the learned URL patterns."""
        if not self.site_profile:
            return
        
        print(f"Domain: {self.site_profile.domain}")
        print(f"Observations: {self.pattern_learner.observations.__len__()}")
        print(f"Pattern Hit Rate: {self.site_profile.pattern_hit_rate:.1%}\n")
        
        def print_pattern_list(patterns, title):
            if patterns:
                print(f"{title}:")
                for p in patterns[:5]:  # Show top 5
                    print(f"  • {p.pattern[:50]:50} (conf: {p.confidence:.1%}, samples: {p.sample_count})")
                if len(patterns) > 5:
                    print(f"  ... and {len(patterns)-5} more")
                print()
        
        print_pattern_list(self.site_profile.product_patterns, "Product Patterns")
        print_pattern_list(self.site_profile.customization_patterns, "Customization Patterns")
        print_pattern_list(self.site_profile.category_patterns, "Category Patterns")
    
    def _print_summary(self):
        """Print crawl summary with intelligence stats."""
        print(f"\n{'='*80}")
        print("INTELLIGENT CRAWL SUMMARY")
        print(f"{'='*80}")
        
        print(f"✓ Pages crawled: {len(self.visited_pages)}")
        print(f"✓ Product pages: {len(self.product_pages)}")
        print(f"✓ Customization pages: {len(self.customization_pages)}")
        print(f"✓ Category pages: {len(self.category_pages)}")
        print(f"⊘ URLs skipped: {len(self.skipped_urls)}")
        
        print(f"\nIntelligence Metrics:")
        print(f"  Pages fetched: {self.stats['pages_fetched']}")
        print(f"  Classifications performed: {self.stats['classifications_performed']}")
        print(f"  Classifications skipped: {self.stats['classifications_skipped']}")
        
        total_potential = self.stats['classifications_performed'] + self.stats['classifications_skipped']
        if total_potential > 0:
            skip_rate = (self.stats['classifications_skipped'] / total_potential) * 100
            print(f"  Classification reduction: {skip_rate:.1f}%")
        
        if self.url_router:
            print()
            self.url_router.print_statistics()
        
        print(f"{'='*80}\n")
    
    def get_cached_content(self, url: str) -> Optional[str]:
        """
        Get cached page content if available.
        
        Args:
            url: The URL
            
        Returns:
            Cached markdown content or None
        """
        return self.page_cache.get(url)