"""Intelligent URL routing based on learned patterns."""

from typing import Tuple, Optional
from urllib.parse import urlparse
from .pattern_learner import SiteProfile


class URLRouter:
    """Route URLs to appropriate handlers based on patterns."""
    
    def __init__(self, site_profile: SiteProfile):
        """
        Initialize router with learned patterns.
        
        Args:
            site_profile: Learned site patterns
        """
        self.profile = site_profile
        
        # Sort patterns by confidence (highest first)
        self.product_patterns = sorted(
            site_profile.product_patterns,
            key=lambda p: p.confidence,
            reverse=True
        )
        self.category_patterns = sorted(
            site_profile.category_patterns,
            key=lambda p: p.confidence,
            reverse=True
        )
        self.customization_patterns = sorted(
            site_profile.customization_patterns,
            key=lambda p: p.confidence,
            reverse=True
        )
        self.ignore_patterns = sorted(
            site_profile.ignore_patterns,
            key=lambda p: p.confidence,
            reverse=True
        )
        
        # Statistics
        self.routes_taken = {
            "IGNORE": 0,
            "CUSTOMIZATION": 0,
            "PRODUCT": 0,
            "CATEGORY": 0,
            "UNKNOWN": 0
        }
    
    def route(self, url: str) -> Tuple[str, float]:
        """
        Route URL to appropriate type.
        
        Priority order:
        1. IGNORE (highest priority - save resources)
        2. CUSTOMIZATION (high value pages)
        3. PRODUCT (core content)
        4. CATEGORY (navigation)
        5. UNKNOWN (needs classification)
        
        Args:
            url: The URL to route
            
        Returns:
            Tuple of (route_type, confidence)
            route_type: "IGNORE", "CUSTOMIZATION", "PRODUCT", "CATEGORY", "UNKNOWN"
            confidence: 0.0 to 1.0
        """
        # Check IGNORE patterns first (highest priority)
        route, conf = self._check_patterns(url, self.ignore_patterns, "IGNORE")
        if route:
            self.routes_taken["IGNORE"] += 1
            return route, conf
        
        # Check CUSTOMIZATION patterns (high value)
        route, conf = self._check_patterns(url, self.customization_patterns, "CUSTOMIZATION")
        if route:
            self.routes_taken["CUSTOMIZATION"] += 1
            return route, conf
        
        # Check PRODUCT patterns
        route, conf = self._check_patterns(url, self.product_patterns, "PRODUCT")
        if route:
            self.routes_taken["PRODUCT"] += 1
            return route, conf
        
        # Check CATEGORY patterns
        route, conf = self._check_patterns(url, self.category_patterns, "CATEGORY")
        if route:
            self.routes_taken["CATEGORY"] += 1
            return route, conf
        
        # Unknown - needs classification
        self.routes_taken["UNKNOWN"] += 1
        return "UNKNOWN", 0.0
    
    def _check_patterns(self, url: str, patterns, route_type: str) -> Tuple[Optional[str], float]:
        """
        Check URL against a list of patterns.
        
        Args:
            url: URL to check
            patterns: List of URLPattern objects
            route_type: Type to return if matched
            
        Returns:
            (route_type, confidence) if matched, (None, 0.0) otherwise
        """
        path = urlparse(url).path.lower()
        
        for pattern in patterns:
            if pattern.regex.search(path):
                return route_type, pattern.confidence
        
        return None, 0.0
    
    def should_crawl(self, url: str) -> bool:
        """
        Determine if URL should be crawled.
        
        Args:
            url: The URL to check
            
        Returns:
            True if should crawl, False if should skip
        """
        route, confidence = self.route(url)
        
        # Never crawl ignored URLs
        if route == "IGNORE":
            return False
        
        # Always crawl high-value pages
        if route in ["CUSTOMIZATION", "PRODUCT"] and confidence > 0.5:
            return True
        
        # Crawl categories for link discovery
        if route == "CATEGORY":
            return True
        
        # Crawl unknowns (need to classify)
        if route == "UNKNOWN":
            return True
        
        return True
    
    def should_classify(self, url: str) -> bool:
        """
        Determine if URL needs AI/rule-based classification.
        
        This is key to reducing AI costs!
        
        Args:
            url: The URL to check
            
        Returns:
            True if needs classification, False if confident from URL alone
        """
        route, confidence = self.route(url)
        
        # High confidence routes don't need classification
        if confidence >= 0.7:
            return False
        
        # Unknown always needs classification
        if route == "UNKNOWN":
            return True
        
        # Medium confidence - classify to confirm
        if 0.3 <= confidence < 0.7:
            return True
        
        # Low confidence - classify
        return True
    
    def get_priority(self, url: str) -> int:
        """
        Get crawl priority for URL.
        
        Higher priority = crawl sooner
        
        Args:
            url: The URL
            
        Returns:
            Priority score (0-100)
        """
        route, confidence = self.route(url)
        
        priority_map = {
            "CUSTOMIZATION": 90,
            "PRODUCT": 80,
            "CATEGORY": 50,
            "UNKNOWN": 30,
            "IGNORE": 0
        }
        
        base_priority = priority_map.get(route, 30)
        
        # Adjust by confidence
        confidence_boost = int(confidence * 20)
        
        return min(base_priority + confidence_boost, 100)
    
    def print_statistics(self):
        """Print routing statistics."""
        total = sum(self.routes_taken.values())
        if total == 0:
            print("No routes taken yet")
            return
        
        print("\n" + "="*60)
        print("URL ROUTING STATISTICS")
        print("="*60)
        
        for route_type, count in sorted(
            self.routes_taken.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            percentage = (count / total) * 100
            print(f"{route_type:15} {count:5} ({percentage:5.1f}%)")
        
        print(f"{'TOTAL':15} {total:5}")
        print("="*60)
        
        # Calculate efficiency
        skip_rate = (self.routes_taken["IGNORE"] / total) * 100 if total > 0 else 0
        classify_needed = self.routes_taken["UNKNOWN"]
        
        print(f"\nEfficiency Metrics:")
        print(f"  URLs skipped automatically: {skip_rate:.1f}%")
        print(f"  URLs needing classification: {classify_needed} ({classify_needed/total*100:.1f}%)")
        print(f"  Pattern hit rate: {(total - classify_needed)/total*100:.1f}%")
        print()
    
    def find_customization_links(self, url: str, markdown: str) -> list:
        """
        Scan product page for customization links.
        
        Args:
            url: Product page URL
            markdown: Page content
            
        Returns:
            List of potential customization URLs
        """
        import re
        from urllib.parse import urljoin
        
        customization_links = []
        
        # Extract all links
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        links = re.findall(link_pattern, markdown)
        
        # Keywords that suggest customization
        customize_keywords = [
            'customize', 'personalize', 'design', 'configure', 'build',
            'create your own', 'start designing', 'inquiry', 'quote',
            'get started', 'begin', 'build your'
        ]
        
        for link_text, link_url in links:
            text_lower = link_text.lower()
            url_lower = link_url.lower()
            
            # Check text for keywords
            text_score = sum(1 for kw in customize_keywords if kw in text_lower)
            
            # Check URL for patterns
            url_score = sum(1 for kw in customize_keywords if kw in url_lower)
            
            # If likely a customization link
            if text_score + url_score >= 2:
                absolute_url = urljoin(url, link_url)
                customization_links.append({
                    'url': absolute_url,
                    'text': link_text,
                    'score': text_score + url_score
                })
        
        # Sort by score
        customization_links.sort(key=lambda x: x['score'], reverse=True)
        
        return [link['url'] for link in customization_links]