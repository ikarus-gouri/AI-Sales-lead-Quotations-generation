"""Model LAM: Enhanced scraper with Gemini-powered interactive extraction.

This scraper extends Model S (BalancedScraper) but replaces configurator extraction
with Gemini-guided interactive extraction when appropriate.

Workflow:
    1. Identify all product pages (crawl entire website)
    2. Send product list to Gemini to detect configurators
    3. For each configurator:
        a. Use Gemini + Playwright for interactive extraction
        b. Fall back to static extraction if needed
    4. Export results

Usage:
    scraper = LAMScraper(config, strictness="balanced")
    catalog = scraper.scrape_all_products()
"""

import os
import time
import asyncio
from typing import Dict, List, Optional
from .balanced_scraper import BalancedScraper
from .config import ScraperConfig


class GeminiConfiguatorConsultant:
    """Consults Gemini to determine if interactive extraction should be used."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini consultant."""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
            except Exception as e:
                print(f"  ⚠️ Gemini initialization failed: {e}")
                self.enabled = False
    
    def should_use_interactive_extraction(
        self, 
        url: str, 
        configurator_info: Dict,
        markdown: str
    ) -> Dict:
        """
        Consult Gemini to determine if interactive extraction should be used.
        
        Args:
            url: Product page URL
            configurator_info: Result from ConfiguratorDetector
            markdown: Page content
            
        Returns:
            Dictionary with decision and reasoning
        """
        if not self.enabled:
            return {
                'use_interactive': False,
                'reason': 'Gemini not available',
                'configurator_url': configurator_info.get('configurator_url'),
                'confidence': 0.0
            }
        
        # Only consult Gemini for high confidence configurators
        if configurator_info.get('confidence', 0) < 0.6:
            return {
                'use_interactive': False,
                'reason': 'Configurator confidence too low',
                'configurator_url': configurator_info.get('configurator_url'),
                'confidence': configurator_info.get('confidence', 0)
            }
        
        try:
            prompt = f"""
Analyze this product page to determine if interactive browser-based extraction is needed.

Product URL: {url}
Configurator Detected: {configurator_info.get('has_configurator')}
Configurator Type: {configurator_info.get('configurator_type')}
Configurator URL: {configurator_info.get('configurator_url')}
Confidence: {configurator_info.get('confidence')}
Indicators: {configurator_info.get('indicators')}

Page Content (first 3000 chars):
{markdown[:3000]}

TASK: Determine if this configurator requires interactive browser-based extraction.

Return JSON with:
{{
  "use_interactive": boolean,
  "reason": "string - why or why not",
  "recommended_url": "string - best URL to extract from",
  "complexity_score": number (0-10),
  "requires_clicks": boolean,
  "has_dynamic_content": boolean
}}

Use interactive extraction (Playwright + Gemini) IF:
- The configurator requires clicking through tabs/accordions/cards
- Content loads dynamically based on user interaction
- Options are revealed progressively
- Complex multi-step configuration process

Use static extraction IF:
- All options are visible in the HTML
- Simple form-based configuration
- Options are in a flat list/table

Only return valid JSON.
"""
            
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean JSON - more aggressive cleaning
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]
            
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Remove trailing commas before closing braces/brackets
            import re
            response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
            
            import json
            result = json.loads(response_text)
            result['confidence'] = configurator_info.get('confidence', 0)
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ Gemini consultation failed: {e}")
            return {
                'use_interactive': False,
                'reason': f'Gemini error: {str(e)}',
                'configurator_url': configurator_info.get('configurator_url'),
                'confidence': configurator_info.get('confidence', 0)
            }


class LAMScraper(BalancedScraper):
    """Model LAM: Balanced scraper with Gemini-powered interactive extraction.
    
    Extends BalancedScraper but replaces configurator extraction with
    Gemini-guided interactive extraction when appropriate.
    """
    
    def __init__(
        self,
        config: ScraperConfig,
        strictness: str = "balanced",
        enable_gemini: bool = True,
        gemini_api_key: Optional[str] = None
    ):
        """
        Initialize LAM scraper.
        
        Args:
            config: Scraper configuration
            strictness: Classification strictness
            enable_gemini: Enable Gemini interactive extraction
            gemini_api_key: Optional Gemini API key
        """
        # Initialize parent (BalancedScraper)
        super().__init__(config, strictness=strictness)
        
        # Initialize Gemini components
        self.enable_gemini = enable_gemini
        self.gemini_consultant = GeminiConfiguatorConsultant(gemini_api_key)
        self.gemini_extractor = None
        
        if enable_gemini and self.gemini_consultant.enabled:
            try:
                # Import from the correct location
                from ..extractors.gemini_interactive_extractor import GeminiInteractiveExtractor
                self.gemini_extractor = GeminiInteractiveExtractor(gemini_api_key)
                print(f"  ✓ Gemini interactive extraction enabled")
            except Exception as e:
                print(f"  ⚠️ Gemini interactive extractor not available: {e}")
                self.enable_gemini = False
        else:
            print(f"  ℹ️ Gemini not enabled or API key not available")
        
        # Statistics
        self.lam_stats = {
            'gemini_consultations': 0,
            'interactive_extractions': 0,
            'static_fallbacks': 0,
            'gemini_failures': 0
        }
    
    def scrape_product(self, url: str, markdown: str = None) -> Optional[Dict]:
        """
        Scrape a single product with LAM approach (for backward compatibility).
        
        Note: For best results, use scrape_all_products() which implements the
        full workflow: identify pages → detect configurators → extract
        
        Args:
            url: Product page URL
            markdown: Optional pre-fetched markdown
            
        Returns:
            Product data dictionary
        """
        print(f"\n{'-'*80}")
        print(f"[LAM] Scraping single product: {url}")
        print(f"{'-'*80}")
        
        # Create a configurator map for this single URL
        configurator_map = self.detect_configurators_with_gemini([url])
        config_info = configurator_map.get(url, {
            'has_configurator': False,
            'configurator_type': 'none',
            'confidence': 0.0
        })
        
        # Scrape the product
        return self._scrape_product_with_config_info(url, config_info)
    
    def _extract_static_fallback(
        self,
        url: str,
        markdown: str,
        product_name: str,
        configurator_info: Dict
    ) -> str:
        """Fall back to static extraction methods (same as BalancedScraper)."""
        customizations = {}
        source = "none"
        
        # Try external configurator
        if configurator_info.get('configurator_type') == 'external' and configurator_info.get('configurator_url'):
            time.sleep(self.config.crawl_delay)
            external_result = self.external_scraper.scrape_external_configurator(
                url=configurator_info['configurator_url'],
                product_name=product_name,
                delay=self.config.crawl_delay
            )
            
            if external_result['success']:
                customizations = external_result['customizations']
                source = "external_configurator"
                print(f"     ✓ Extracted from external configurator")
        
        # Try embedded configurator URL
        elif configurator_info.get('configurator_url') and configurator_info.get('configurator_type') == 'embedded':
            time.sleep(self.config.crawl_delay)
            config_markdown = self.http_client.scrape_with_jina(configurator_info['configurator_url'])
            
            if config_markdown:
                customizations = self.product_extractor.extract_customizations(config_markdown)
                source = "embedded_configurator_page"
                print(f"     ✓ Extracted from embedded configurator")
        
        # Extract from current page
        if not customizations:
            customizations = self.product_extractor.extract_customizations(markdown)
            source = "product_page"
            print(f"     ✓ Extracted from product page")
        
        self._current_customizations = customizations
        return source
    
    def _convert_gemini_options(self, gemini_options: List[Dict]) -> Dict:
        """
        Convert Gemini's option format to standard customizations format.
        
        Gemini format:
        [
            {"category": "Size", "component": "Large", "price": "+$100", "reference": "url"},
            ...
        ]
        
        Standard format:
        {
            "Size": [
                {"label": "Large", "price": "+$100", "image": "url"},
                ...
            ]
        }
        """
        customizations = {}
        
        for option in gemini_options:
            category = option.get('category', 'Options')
            
            if category not in customizations:
                customizations[category] = []
            
            customizations[category].append({
                'label': option.get('component', 'Unknown'),
                'price': option.get('price'),
                'image': option.get('reference')
            })
        
        return customizations
    
    def _get_extracted_customizations(self) -> Dict:
        """Get customizations from current extraction."""
        return getattr(self, '_current_customizations', {})
    
    def identify_all_product_pages(self) -> List[str]:
        """Step 1: Crawl website and identify all product pages."""
        print(f"\n{'='*80}")
        print(f"[LAM Step 1] Identifying All Product Pages")
        print(f"{'='*80}")
        
        # Use the crawler to discover all pages
        self.crawler.crawl(
            max_pages=self.config.max_pages,
            max_depth=self.config.max_depth
        )
        
        product_urls = list(self.crawler.product_pages)
        
        print(f"\n✓ Identified {len(product_urls)} product pages")
        for i, url in enumerate(product_urls[:10], 1):
            print(f"  {i}. {url}")
        
        if len(product_urls) > 10:
            print(f"  ... and {len(product_urls) - 10} more")
        
        return product_urls
    
    def detect_configurators_with_gemini(self, product_urls: List[str]) -> Dict[str, Dict]:
        """Step 2: Send product page list to Gemini to identify configurators."""
        print(f"\n{'='*80}")
        print(f"[LAM Step 2] Detecting Configurators with Gemini")
        print(f"{'='*80}")
        
        configurator_map = {}
        
        if not self.gemini_consultant.enabled:
            print("  ⚠️ Gemini not available, using static detection only")
            return self._detect_configurators_static(product_urls)
        
        # Ask Gemini to analyze the product list
        try:
            import json
            
            prompt = f"""
Analyze this list of product pages and identify which ones likely have interactive configurators.

Product URLs:
{json.dumps(product_urls, indent=2)}

TASK: For each URL, determine:
1. Does it likely have a product configurator/customizer?
2. What type of configurator (embedded, external, none)?
3. Is it worth interactive extraction with Playwright?

Return JSON with:
{{
  "configurators_detected": [
    {{
      "url": "string",
      "has_configurator": boolean,
      "confidence": number (0-1),
      "configurator_type": "embedded" | "external" | "none",
      "requires_interaction": boolean,
      "reason": "string"
    }}
  ],
  "recommendations": {{
    "interactive_extraction_count": number,
    "static_extraction_count": number
  }}
}}

Look for URL patterns indicating:
- /configure, /customize, /build, /design
- product pages that mention customization
- links to external configurator platforms

Only return valid JSON.
"""
            
            print("  🤖 Consulting Gemini about configurators...")
            response = self.gemini_consultant.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean JSON - more aggressive cleaning
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            elif response_text.startswith('```'):
                response_text = response_text[3:]
            
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Remove any trailing commas before closing braces/brackets (common JSON error)
            import re
            response_text = re.sub(r',(\s*[}\]])', r'\1', response_text)
            
            # Try to parse JSON
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as json_err:
                print(f"  ⚠️ JSON parsing error: {json_err}")
                print(f"  Response preview: {response_text[:500]}")
                raise
            
            # Convert to configurator map
            for item in result.get('configurators_detected', []):
                url = item['url']
                configurator_map[url] = {
                    'has_configurator': item.get('has_configurator', False),
                    'configurator_type': item.get('configurator_type', 'none'),
                    'confidence': item.get('confidence', 0.0),
                    'requires_interaction': item.get('requires_interaction', False),
                    'reason': item.get('reason', ''),
                    'detection_method': 'gemini'
                }
            
            # Print summary
            recs = result.get('recommendations', {})
            print(f"\n  ✓ Gemini Analysis Complete")
            print(f"    Interactive extraction recommended: {recs.get('interactive_extraction_count', 0)}")
            print(f"    Static extraction recommended: {recs.get('static_extraction_count', 0)}")
            
            return configurator_map
            
        except Exception as e:
            print(f"  ⚠️ Gemini detection failed: {e}")
            print(f"  → Falling back to static detection")
            return self._detect_configurators_static(product_urls)
    
    def _detect_configurators_static(self, product_urls: List[str]) -> Dict[str, Dict]:
        """Fallback: Use static configurator detection."""
        configurator_map = {}
        
        print("  📋 Using static configurator detection...")
        
        for url in product_urls:
            # Quick detection based on URL patterns
            url_lower = url.lower()
            has_config = any(keyword in url_lower for keyword in 
                           ['configure', 'customize', 'build', 'design', 'personalize'])
            
            configurator_map[url] = {
                'has_configurator': has_config,
                'configurator_type': 'embedded' if has_config else 'none',
                'confidence': 0.7 if has_config else 0.3,
                'requires_interaction': has_config,
                'reason': 'URL pattern match' if has_config else 'No configurator indicators',
                'detection_method': 'static'
            }
        
        config_count = sum(1 for c in configurator_map.values() if c['has_configurator'])
        print(f"  ✓ Static detection found {config_count} potential configurators")
        
        return configurator_map
    
    async def extract_with_gemini_playwright(self, url: str, configurator_info: Dict) -> Dict:
        """Step 3: Use Gemini + Playwright for interactive extraction."""
        print(f"\n  [Gemini+Playwright Extraction]")
        
        if not self.gemini_extractor:
            print("    ⚠️ Gemini extractor not available")
            return {'success': False, 'customizations': {}}
        
        try:
            # Use Gemini interactive extractor (async)
            options = await self.gemini_extractor.interactive_extraction(
                url,
                max_iterations=20
            )
            
            if options:
                customizations = self._convert_gemini_options(options)
                print(f"    ✓ Extracted {len(options)} options via Gemini+Playwright")
                return {
                    'success': True,
                    'customizations': customizations,
                    'method': 'gemini_interactive'
                }
            else:
                print(f"    ⚠️ No options extracted")
                return {'success': False, 'customizations': {}}
                
        except Exception as e:
            print(f"    ✗ Gemini+Playwright extraction failed: {e}")
            return {'success': False, 'customizations': {}, 'error': str(e)}
    
    async def scrape_all_products(self) -> Dict:
        """Enhanced LAM workflow: Identify pages → Detect configurators → Extract."""
        print(f"\n{'='*80}")
        print(f"[LAM MODEL] Starting Enhanced Workflow")
        print(f"{'='*80}")
        
        # Step 1: Identify all product pages
        product_urls = self.identify_all_product_pages()
        
        if not product_urls:
            print("\n❌ No product pages found")
            return {'products': [], 'total_products': 0}
        
        # Step 2: Detect configurators with Gemini
        configurator_map = self.detect_configurators_with_gemini(product_urls)
        
        # Check if any configurators were found
        configurators_found = sum(1 for c in configurator_map.values() if c['has_configurator'])
        
        if configurators_found == 0:
            print(f"\n{'⚠️'*40}")
            print(f"⚠️  NO CONFIGURATORS DETECTED")
            print(f"⚠️  Automatically switching to Model S (Static Extraction)")
            print(f"{'⚠️'*40}\n")
            
            # Fall back to parent class (BalancedScraper = Model S) workflow
            products = []
            for i, url in enumerate(product_urls, 1):
                print(f"\n[{i}/{len(product_urls)}] Processing with Model S: {url}")
                
                # Use parent's scrape_product method (sync)
                product_data = super().scrape_product(url)
                
                if product_data:
                    products.append(product_data)
                
                # Respect crawl delay
                if i < len(product_urls):
                    time.sleep(self.config.crawl_delay)
            
            catalog = {
                'products': products,
                'total_products': len(products),
                'configurators_detected': 0,
                'model': 'S (auto-fallback from LAM)',
                'workflow': 'static_extraction'
            }
            
            print(f"\n{'='*80}")
            print(f"[Model S] Extraction Complete (LAM auto-fallback)")
            print(f"{'='*80}")
            print(f"  Total products: {len(products)}")
            
            return catalog
        
        # Step 3: Extract from each product
        print(f"\n{'='*80}")
        print(f"[LAM Step 3] Extracting Product Data")
        print(f"{'='*80}")
        
        products = []
        
        for i, url in enumerate(product_urls, 1):
            print(f"\n[{i}/{len(product_urls)}] Processing: {url}")
            
            # Get configurator info from map
            config_info = configurator_map.get(url, {
                'has_configurator': False,
                'configurator_type': 'none',
                'confidence': 0.0
            })
            
            # Scrape the product with LAM method (now async)
            product_data = await self._scrape_product_with_config_info(url, config_info)
            
            if product_data:
                products.append(product_data)
            
            # Respect crawl delay
            if i < len(product_urls):
                await asyncio.sleep(self.config.crawl_delay)
        
        catalog = {
            'products': products,
            'total_products': len(products),
            'configurators_detected': sum(1 for c in configurator_map.values() 
                                         if c['has_configurator']),
            'model': 'LAM',
            'workflow': 'identify_then_extract'
        }
        
        print(f"\n{'='*80}")
        print(f"[LAM] Extraction Complete")
        print(f"{'='*80}")
        print(f"  Total products: {len(products)}")
        print(f"  Configurators found: {catalog['configurators_detected']}")
        
        return catalog
    
    async def _scrape_product_with_config_info(self, url: str, config_info: Dict) -> Optional[Dict]:
        """Scrape a product with pre-detected configurator information."""
        # Get page content
        markdown = self.http_client.scrape_with_jina(url)
        if not markdown:
            return None
        
        # Extract basic info
        product_name = self.product_extractor.extract_product_name(url, markdown)
        base_price = self.product_extractor.extract_base_price(markdown)
        specifications = self.product_extractor.extract_specifications(markdown)
        
        print(f"  Product: {product_name}")
        print(f"  Base Price: {base_price or 'N/A'}")
        print(f"  Specifications: {len(specifications)}")
        print(f"  Configurator: {config_info.get('has_configurator')}")
        print(f"  Requires Interaction: {config_info.get('requires_interaction')}")
        
        customizations = {}
        extraction_method = 'none'
        
        # Decide extraction method based on Gemini's recommendation
        if config_info.get('requires_interaction') and self.gemini_extractor:
            # Use Gemini + Playwright (async - now properly awaited)
            result = await self.extract_with_gemini_playwright(url, config_info)
            if result['success']:
                customizations = result['customizations']
                extraction_method = 'gemini_interactive'
                self.lam_stats['interactive_extractions'] += 1
            else:
                # Fallback to static
                extraction_method = self._extract_static_fallback(
                    url, markdown, product_name, config_info
                )
                customizations = self._get_extracted_customizations()
                self.lam_stats['static_fallbacks'] += 1
        
        elif config_info.get('has_configurator'):
            # Use static extraction
            extraction_method = self._extract_static_fallback(
                url, markdown, product_name, config_info
            )
            customizations = self._get_extracted_customizations()
            self.lam_stats['static_fallbacks'] += 1
        
        else:
            # No configurator, extract from page
            customizations = self.product_extractor.extract_customizations(markdown)
            extraction_method = 'product_page'
        
        return {
            'product_name': product_name,
            'url': url,
            'base_price': base_price,
            'specifications': specifications,
            'extraction_method': extraction_method,
            'model': 'LAM',
            'has_configurator': config_info.get('has_configurator'),
            'configurator_type': config_info.get('configurator_type'),
            'requires_interaction': config_info.get('requires_interaction'),
            'detection_method': config_info.get('detection_method'),
            'customizations': customizations,
            'customization_categories': list(customizations.keys()),
            'total_customization_options': sum(len(opts) for opts in customizations.values())
        }
    
    def print_statistics(self):
        """Print scraping statistics including LAM-specific stats."""
        # Call parent statistics
        super().print_statistics()
        
        # Add LAM stats
        print(f"\n\033[36m[LAM STATS]\033[0m Gemini Usage:")
        print(f"   Gemini consultations: {self.lam_stats['gemini_consultations']}")
        print(f"   Interactive extractions: {self.lam_stats['interactive_extractions']}")
        print(f"   Static fallbacks: {self.lam_stats['static_fallbacks']}")
        print(f"   Gemini failures: {self.lam_stats['gemini_failures']}")
        
        if self.lam_stats['gemini_consultations'] > 0:
            success_rate = (
                self.lam_stats['interactive_extractions'] 
                / self.lam_stats['gemini_consultations'] * 100
            )
            print(f"   Gemini success rate: {success_rate:.1f}%")
