"""Automatic URL pattern learning and detection."""

import re
from typing import List, Dict, Set
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class URLPattern:
    """Represents a learned URL pattern."""
    pattern: str
    regex: re.Pattern
    confidence: float
    sample_count: int
    page_type: str  # "product", "category", "customization", "ignore"


@dataclass
class SiteProfile:
    """Learned patterns for a specific site."""
    domain: str
    
    # Learned patterns
    product_patterns: List[URLPattern] = field(default_factory=list)
    category_patterns: List[URLPattern] = field(default_factory=list)
    customization_patterns: List[URLPattern] = field(default_factory=list)
    ignore_patterns: List[URLPattern] = field(default_factory=list)
    
    # Statistics
    total_pages_seen: int = 0
    pattern_hit_rate: float = 0.0


class URLPatternLearner:
    """Learn URL patterns from observed pages."""
    
    def __init__(self):
        # Seed patterns (common e-commerce patterns)
        self.seed_patterns = {
            "product": [
                r"/product/[^/]+$",
                r"/products/[^/]+$",
                r"/p/\d+",
                r"/item/[^/]+$",
                r"/shop/[^/]+/[^/]+$",
            ],
            "category": [
                r"/category/[^/]+$",
                r"/categories/[^/]+$",
                r"/collection/[^/]+$",
                r"/collections/[^/]+$",
                r"/shop/[^/]+$",
            ],
            "customization": [
                r"customize",
                r"configurator",
                r"inquiry",
                r"enquiry",
                r"build-your",
                r"design-your",
                r"quote",
                r"quotation",
            ],
            "ignore": [
                r"/cart",
                r"/checkout",
                r"/account",
                r"/login",
                r"/register",
                r"/wp-admin",
                r"/wp-content/uploads",
            ]
        }
        
        # Observed URL → page type mapping
        self.observations: Dict[str, str] = {}
        
        # Path segment frequency
        self.segment_counter: Counter = Counter()
    
    def observe(self, url: str, page_type: str):
        """
        Record an observation of URL → page type.
        
        Args:
            url: The URL
            page_type: One of "product", "category", "customization", "ignore"
        """
        self.observations[url] = page_type
        
        # Extract and count path segments
        path_parts = self._extract_path_segments(url)
        for part in path_parts:
            self.segment_counter[part] += 1
    
    def learn_patterns(self, min_samples: int = 3) -> SiteProfile:
        """
        Learn patterns from observations.
        
        Args:
            min_samples: Minimum samples needed to promote a pattern
            
        Returns:
            SiteProfile with learned patterns
        """
        if not self.observations:
            return self._create_seed_profile()
        
        # Group URLs by page type
        grouped = self._group_by_type()
        
        profile = SiteProfile(domain=self._extract_domain())
        
        # Learn patterns for each type
        for page_type, urls in grouped.items():
            if len(urls) < min_samples:
                continue
            
            patterns = self._extract_common_patterns(urls, page_type, min_samples)
            
            if page_type == "product":
                profile.product_patterns.extend(patterns)
            elif page_type == "category":
                profile.category_patterns.extend(patterns)
            elif page_type == "customization":
                profile.customization_patterns.extend(patterns)
            elif page_type == "ignore":
                profile.ignore_patterns.extend(patterns)
        
        # Add seed patterns with lower confidence
        profile = self._merge_with_seeds(profile)
        
        # Calculate statistics
        profile.total_pages_seen = len(self.observations)
        profile.pattern_hit_rate = self._calculate_hit_rate(profile)
        
        return profile
    
    def _extract_path_segments(self, url: str) -> List[str]:
        """Extract path segments from URL."""
        from urllib.parse import urlparse
        path = urlparse(url).path
        segments = [s for s in path.split('/') if s]
        return segments
    
    def _extract_domain(self) -> str:
        """Extract domain from first observation."""
        if not self.observations:
            return "unknown"
        
        from urllib.parse import urlparse
        first_url = next(iter(self.observations.keys()))
        return urlparse(first_url).netloc
    
    def _group_by_type(self) -> Dict[str, List[str]]:
        """Group URLs by their page type."""
        grouped = {}
        for url, page_type in self.observations.items():
            if page_type not in grouped:
                grouped[page_type] = []
            grouped[page_type].append(url)
        return grouped
    
    def _extract_common_patterns(
        self, 
        urls: List[str], 
        page_type: str,
        min_samples: int
    ) -> List[URLPattern]:
        """
        Extract common patterns from URLs of the same type.
        
        Strategy:
        1. Find common path prefixes
        2. Find common path segments
        3. Find common patterns in path structure
        """
        patterns = []
        
        # Method 1: Common path prefixes
        common_prefix = self._find_common_prefix(urls)
        if common_prefix and len(common_prefix) > 5:
            pattern_str = re.escape(common_prefix) + r".*"
            patterns.append(URLPattern(
                pattern=pattern_str,
                regex=re.compile(pattern_str),
                confidence=0.9,
                sample_count=len(urls),
                page_type=page_type
            ))
        
        # Method 2: Common segments
        all_segments = []
        for url in urls:
            all_segments.extend(self._extract_path_segments(url))
        
        segment_freq = Counter(all_segments)
        
        # Find segments that appear in most URLs
        for segment, count in segment_freq.most_common(5):
            if count >= min_samples and len(segment) > 2:
                # Ignore very generic segments
                if segment.lower() in ['en', 'us', 'www', 'index', 'home']:
                    continue
                
                pattern_str = f"/{re.escape(segment)}/"
                patterns.append(URLPattern(
                    pattern=pattern_str,
                    regex=re.compile(pattern_str),
                    confidence=min(0.7, count / len(urls)),
                    sample_count=count,
                    page_type=page_type
                ))
        
        # Method 3: Detect numeric/slug patterns
        numeric_pattern = self._detect_numeric_pattern(urls)
        if numeric_pattern:
            patterns.append(numeric_pattern)
        
        slug_pattern = self._detect_slug_pattern(urls)
        if slug_pattern:
            patterns.append(slug_pattern)
        
        return patterns
    
    def _find_common_prefix(self, urls: List[str]) -> str:
        """Find common prefix among URLs."""
        if not urls:
            return ""
        
        from urllib.parse import urlparse
        paths = [urlparse(url).path for url in urls]
        
        if not paths:
            return ""
        
        prefix = paths[0]
        for path in paths[1:]:
            while not path.startswith(prefix):
                prefix = prefix[:-1]
                if not prefix:
                    return ""
        
        return prefix
    
    def _detect_numeric_pattern(self, urls: List[str]) -> URLPattern:
        """Detect if URLs follow a numeric ID pattern."""
        from urllib.parse import urlparse
        
        numeric_count = 0
        for url in urls:
            path = urlparse(url).path
            if re.search(r'/\d+/?$', path):
                numeric_count += 1
        
        if numeric_count >= len(urls) * 0.7:  # 70% have numeric IDs
            return URLPattern(
                pattern=r"/\d+/?$",
                regex=re.compile(r"/\d+/?$"),
                confidence=0.85,
                sample_count=numeric_count,
                page_type="product"
            )
        
        return None
    
    def _detect_slug_pattern(self, urls: List[str]) -> URLPattern:
        """Detect if URLs follow a slug pattern."""
        from urllib.parse import urlparse
        
        slug_count = 0
        for url in urls:
            path = urlparse(url).path
            # Slug pattern: lowercase-with-hyphens
            if re.search(r'/[a-z0-9]+(?:-[a-z0-9]+)+/?$', path):
                slug_count += 1
        
        if slug_count >= len(urls) * 0.7:  # 70% have slugs
            return URLPattern(
                pattern=r"/[a-z0-9]+(?:-[a-z0-9]+)+/?$",
                regex=re.compile(r"/[a-z0-9]+(?:-[a-z0-9]+)+/?$"),
                confidence=0.75,
                sample_count=slug_count,
                page_type="product"
            )
        
        return None
    
    def _merge_with_seeds(self, profile: SiteProfile) -> SiteProfile:
        """Merge learned patterns with seed patterns."""
        # Add seed patterns with lower confidence
        for pattern_str in self.seed_patterns.get("product", []):
            if not any(p.pattern == pattern_str for p in profile.product_patterns):
                profile.product_patterns.append(URLPattern(
                    pattern=pattern_str,
                    regex=re.compile(pattern_str),
                    confidence=0.5,  # Lower confidence for seeds
                    sample_count=0,
                    page_type="product"
                ))
        
        for pattern_str in self.seed_patterns.get("customization", []):
            if not any(p.pattern == pattern_str for p in profile.customization_patterns):
                profile.customization_patterns.append(URLPattern(
                    pattern=pattern_str,
                    regex=re.compile(pattern_str),
                    confidence=0.6,
                    sample_count=0,
                    page_type="customization"
                ))
        
        for pattern_str in self.seed_patterns.get("ignore", []):
            if not any(p.pattern == pattern_str for p in profile.ignore_patterns):
                profile.ignore_patterns.append(URLPattern(
                    pattern=pattern_str,
                    regex=re.compile(pattern_str),
                    confidence=0.8,
                    sample_count=0,
                    page_type="ignore"
                ))
        
        return profile
    
    def _create_seed_profile(self) -> SiteProfile:
        """Create profile from seed patterns only."""
        profile = SiteProfile(domain="unknown")
        
        for pattern_str in self.seed_patterns.get("product", []):
            profile.product_patterns.append(URLPattern(
                pattern=pattern_str,
                regex=re.compile(pattern_str),
                confidence=0.5,
                sample_count=0,
                page_type="product"
            ))
        
        for pattern_str in self.seed_patterns.get("customization", []):
            profile.customization_patterns.append(URLPattern(
                pattern=pattern_str,
                regex=re.compile(pattern_str),
                confidence=0.6,
                sample_count=0,
                page_type="customization"
            ))
        
        for pattern_str in self.seed_patterns.get("ignore", []):
            profile.ignore_patterns.append(URLPattern(
                pattern=pattern_str,
                regex=re.compile(pattern_str),
                confidence=0.8,
                sample_count=0,
                page_type="ignore"
            ))
        
        return profile
    
    def _calculate_hit_rate(self, profile: SiteProfile) -> float:
        """Calculate how often patterns would have matched observations."""
        if not self.observations:
            return 0.0
        
        from .url_router import URLRouter
        router = URLRouter(profile)
        
        hits = 0
        for url, actual_type in self.observations.items():
            predicted_type, confidence = router.route(url)
            if predicted_type == actual_type and confidence > 0.5:
                hits += 1
        
        return hits / len(self.observations)