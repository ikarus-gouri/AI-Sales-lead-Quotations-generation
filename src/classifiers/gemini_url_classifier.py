"""Gemini-powered URL batch classifier for intelligent product page detection."""

import google.generativeai as genai
from typing import List, Dict, Tuple
import json
import re


class GeminiURLClassifier:
    """
    Uses Gemini to intelligently classify URLs in batch.
    
    This is more efficient and accurate than individual page classification
    because Gemini can:
    1. See URL patterns across the entire site
    2. Distinguish product vs category vs content pages
    3. Identify hybrid pages (category + product showcase)
    """
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize Gemini URL classifier.
        
        Args:
            api_key: Gemini API key
            model_name: Gemini model to use
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        print("✓ Gemini URL Classifier enabled")
    
    def classify_urls_batch(
        self, 
        urls: List[str], 
        base_url: str,
        site_context: str = None
    ) -> Dict[str, Dict]:
        """
        Classify a batch of URLs using Gemini.
        
        Args:
            urls: List of URLs to classify
            base_url: Base domain URL for context
            site_context: Optional description of the website
            
        Returns:
            Dictionary mapping URL to classification:
            {
                "url": {
                    "type": "product" | "category" | "content" | "other",
                    "confidence": 0.0-1.0,
                    "reason": "explanation",
                    "priority": 1-10  # scraping priority
                }
            }
        """
        if not urls:
            return {}
        
        print(f"\n🤖 Gemini: Classifying {len(urls)} URLs...")
        
        # Build prompt
        prompt = self._build_classification_prompt(urls, base_url, site_context)
        
        try:
            # Get Gemini classification
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            classifications = self._parse_gemini_response(response_text, urls)
            
            # Print summary
            self._print_classification_summary(classifications)
            
            return classifications
            
        except Exception as e:
            print(f"  ⚠️ Gemini classification failed: {e}")
            print(f"  → Falling back to URL pattern matching")
            return self._fallback_classification(urls)
    
    def _build_classification_prompt(
        self, 
        urls: List[str], 
        base_url: str,
        site_context: str = None
    ) -> str:
        """Build the classification prompt for Gemini."""
        
        # Format URLs for better readability
        url_list = "\n".join(f"{i+1}. {url}" for i, url in enumerate(urls))
        
        context = f"\n\nSite description: {site_context}" if site_context else ""
        
        prompt = f"""You are analyzing URLs from an e-commerce website to classify them accurately.

Website: {base_url}{context}

Your task: Classify each URL into one of these categories:

**PRODUCT**: Individual product pages where users can view/customize/buy ONE specific product
  - Examples: /model-3/, /outdoor-barrel-sauna/, /4-person-sauna/
  - Has: Product name in URL, specific model/variant identifier

**CATEGORY**: Collection/listing pages showing MULTIPLE products
  - Examples: /for-home/, /saunas/, /outdoor-saunas/, /shop/
  - Has: Plural nouns, category names, collection indicators

**CONTENT**: Blog posts, articles, guides, resources
  - Examples: /blog/sauna-benefits/, /resources/, /why-sauna-is-good/
  - Has: Article titles, dates, resource indicators

**HYBRID**: Pages that both showcase a specific product AND list related products
  - Examples: /bespoke-saunas/ (main product + customization options)
  - Has: Can be both a product showcase and category

**OTHER**: About pages, contact, careers, etc.

URLs to classify:
{url_list}

Respond with ONLY valid JSON in this exact format:
{{
  "classifications": [
    {{
      "url": "full_url_here",
      "type": "product|category|content|hybrid|other",
      "confidence": 0.95,
      "reason": "Brief explanation",
      "priority": 8
    }}
  ]
}}

Rules:
- confidence: 0.0 to 1.0 (how certain you are)
- priority: 1-10 (10=definitely scrape, 1=skip)
- reason: One sentence explaining the classification
- Look for patterns across ALL URLs to identify the site's structure
- Product pages typically have specific model names/numbers
- Category pages typically have generic/plural terms

Respond with JSON only, no markdown formatting."""
        
        return prompt
    
    def _parse_gemini_response(
        self, 
        response_text: str, 
        original_urls: List[str]
    ) -> Dict[str, Dict]:
        """Parse Gemini's JSON response into classification dict."""
        
        # Try to extract JSON from response
        try:
            # Remove markdown code blocks if present
            json_text = re.sub(r'```json\s*|\s*```', '', response_text)
            json_text = json_text.strip()
            
            # Parse JSON
            data = json.loads(json_text)
            
            # Convert to dict keyed by URL
            classifications = {}
            for item in data.get('classifications', []):
                url = item['url']
                classifications[url] = {
                    'type': item['type'],
                    'confidence': float(item['confidence']),
                    'reason': item['reason'],
                    'priority': int(item.get('priority', 5))
                }
            
            # Ensure all original URLs are in result
            for url in original_urls:
                if url not in classifications:
                    print(f"  ⚠️ Missing classification for: {url}")
                    classifications[url] = self._fallback_single(url)
            
            return classifications
            
        except json.JSONDecodeError as e:
            print(f"  ⚠️ Failed to parse Gemini JSON response: {e}")
            print(f"  Response preview: {response_text[:200]}...")
            return self._fallback_classification(original_urls)
    
    def _fallback_classification(self, urls: List[str]) -> Dict[str, Dict]:
        """Fallback to simple pattern matching if Gemini fails."""
        classifications = {}
        for url in urls:
            classifications[url] = self._fallback_single(url)
        return classifications
    
    def _fallback_single(self, url: str) -> Dict:
        """Simple pattern-based classification for a single URL."""
        url_lower = url.lower()
        
        # Product indicators
        product_patterns = [
            r'/model-\d+',
            r'/\d+-person',
            r'/barrel-sauna',
            r'/-sauna/',
            r'/outdoor-\w+-sauna',
        ]
        
        # Category indicators
        category_patterns = [
            r'/for-home/?$',
            r'/for-business/?$',
            r'/shop/?$',
            r'/products/?$',
            r'/saunas/?$',
        ]
        
        # Content indicators
        content_patterns = [
            r'/blog/',
            r'/resources/',
            r'/\d{4}/\d{2}/',  # Date pattern
            r'/(why|how|what)-',
            r'/article/',
        ]
        
        # Check patterns
        for pattern in product_patterns:
            if re.search(pattern, url_lower):
                return {
                    'type': 'product',
                    'confidence': 0.6,
                    'reason': 'URL pattern suggests product',
                    'priority': 7
                }
        
        for pattern in category_patterns:
            if re.search(pattern, url_lower):
                return {
                    'type': 'category',
                    'confidence': 0.5,
                    'reason': 'URL pattern suggests category',
                    'priority': 5
                }
        
        for pattern in content_patterns:
            if re.search(pattern, url_lower):
                return {
                    'type': 'content',
                    'confidence': 0.7,
                    'reason': 'URL pattern suggests blog/article',
                    'priority': 1
                }
        
        # Default: unknown
        return {
            'type': 'other',
            'confidence': 0.3,
            'reason': 'No clear pattern detected',
            'priority': 3
        }
    
    def _print_classification_summary(self, classifications: Dict[str, Dict]):
        """Print a summary of classifications."""
        
        # Group by type
        by_type = {}
        for url, data in classifications.items():
            page_type = data['type']
            if page_type not in by_type:
                by_type[page_type] = []
            by_type[page_type].append((url, data))
        
        print(f"\n📊 Classification Summary:")
        print(f"   Total URLs: {len(classifications)}")
        
        for page_type in ['product', 'category', 'hybrid', 'content', 'other']:
            if page_type in by_type:
                count = len(by_type[page_type])
                avg_conf = sum(d['confidence'] for _, d in by_type[page_type]) / count
                print(f"   {page_type.upper()}: {count} (avg confidence: {avg_conf:.1%})")
        
        # Show product pages by priority
        products = [
            (url, data) for url, data in classifications.items()
            if data['type'] in ['product', 'hybrid']
        ]
        
        if products:
            products_sorted = sorted(products, key=lambda x: x[1]['priority'], reverse=True)
            print(f"\n🎯 Product Pages by Priority ({len(products)}):")
            for url, data in products_sorted[:5]:  # Show top 5
                short_url = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                print(f"   [{data['priority']}/10] /{short_url}/")
                print(f"            → {data['reason']}")
            
            if len(products) > 5:
                print(f"   ... and {len(products) - 5} more product pages")
        
        # Show what's being filtered out
        filtered = [
            (url, data) for url, data in classifications.items()
            if data['type'] in ['content', 'other'] or data['priority'] < 5
        ]
        
        if filtered:
            print(f"\n🚫 Filtered Out ({len(filtered)} pages):")
            for url, data in filtered[:3]:
                short_url = url.split('/')[-2] if url.endswith('/') else url.split('/')[-1]
                print(f"   /{short_url}/ - {data['type']} ({data['reason']})")
            if len(filtered) > 3:
                print(f"   ... and {len(filtered) - 3} more filtered pages")
    
    def get_product_urls(
        self, 
        classifications: Dict[str, Dict],
        min_priority: int = 5
    ) -> List[str]:
        """
        Extract product URLs from classifications.
        
        Args:
            classifications: Result from classify_urls_batch()
            min_priority: Minimum priority score (1-10)
            
        Returns:
            List of product URLs sorted by priority
        """
        products = [
            (url, data['priority'])
            for url, data in classifications.items()
            if data['type'] in ['product', 'hybrid'] 
            and data['priority'] >= min_priority
        ]
        
        # Sort by priority (highest first)
        products.sort(key=lambda x: x[1], reverse=True)
        
        return [url for url, _ in products]
    
    def should_scrape_detailed(self, url: str, classification: Dict) -> bool:
        """
        Determine if URL should get detailed product scraping.
        
        Args:
            url: The URL
            classification: Classification data from classify_urls_batch()
            
        Returns:
            True if should scrape in detail
        """
        page_type = classification['type']
        confidence = classification['confidence']
        priority = classification['priority']
        
        # Always scrape high-priority products
        if page_type == 'product' and priority >= 7:
            return True
        
        # Scrape hybrid pages (they might have product details)
        if page_type == 'hybrid' and confidence >= 0.5:
            return True
        
        # Don't scrape content or low-priority pages
        if page_type in ['content', 'other']:
            return False
        
        # For uncertain cases, use priority
        return priority >= 6


# Integration example
def integrate_with_scraper(scraper_instance):
    """
    Example of how to integrate GeminiURLClassifier with your scraper.
    
    Call this BEFORE Phase 2 (content validation & extraction).
    """
    # Initialize classifier
    gemini_classifier = GeminiURLClassifier(
        api_key=scraper_instance.config.gemini_api_key,
        model_name="gemini-2.0-flash-exp"
    )
    
    # Get all discovered URLs from crawler
    discovered_urls = list(scraper_instance.crawler.visited_pages)
    
    # Classify URLs in batch
    classifications = gemini_classifier.classify_urls_batch(
        urls=discovered_urls,
        base_url=scraper_instance.config.base_url,
        site_context="Cedar & Stone Sauna - Custom outdoor sauna manufacturer"
    )
    
    # Filter to product URLs only
    product_urls = gemini_classifier.get_product_urls(
        classifications=classifications,
        min_priority=6  # Only scrape priority 6+
    )
    
    print(f"\n✓ Filtered to {len(product_urls)} product pages for detailed scraping")
    
    return product_urls, classifications