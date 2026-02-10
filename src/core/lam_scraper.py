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
        Consult Gemini to determine the best extraction method.
        
        Args:
            url: Product page URL
            configurator_info: Result from ConfiguratorDetector
            markdown: Page content
            
        Returns:
            Dictionary with extraction_method ('INTERACTIVE', 'STATIC', or 'AI') and reasoning
        """
        if not self.enabled:
            return {
                'extraction_method': 'STATIC',
                'use_interactive': False,
                'reason': 'Gemini not available',
                'configurator_url': configurator_info.get('configurator_url'),
                'confidence': 0.0
            }
        
        # Only consult Gemini for high confidence configurators
        if configurator_info.get('confidence', 0) < 0.6:
            return {
                'extraction_method': 'STATIC',
                'use_interactive': False,
                'reason': 'Configurator confidence too low',
                'configurator_url': configurator_info.get('configurator_url'),
                'confidence': configurator_info.get('confidence', 0)
            }
        
        try:
            prompt = f"""
Analyze this product page to determine the BEST EXTRACTION METHOD.

Product URL: {url}
Configurator Detected: {configurator_info.get('has_configurator')}
Configurator Type: {configurator_info.get('configurator_type')}
Configurator URL: {configurator_info.get('configurator_url')}
Confidence: {configurator_info.get('confidence')}
Indicators: {configurator_info.get('indicators')}

Page Content (first 3000 chars):
{markdown[:3000]}

TASK: Determine the optimal extraction method for this product page.

AVAILABLE METHODS:

1. **INTERACTIVE** (Playwright + Gemini browser automation)
   USE WHEN:
   - Configurator requires clicking through tabs/accordions/option cards
   - Content loads dynamically based on user interaction
   - Options are revealed progressively through clicks
   - Complex multi-step configuration process
   - JavaScript-heavy interactive elements

2. **STATIC** (Traditional HTML/Markdown extraction)
   USE WHEN:
   - All options and data are visible in the HTML/markdown
   - Simple form-based configuration with static options
   - Options are presented in flat lists/tables
   - Well-structured, non-interactive content
   - Standard product page with clear structure

3. **AI** (Gemini semantic extraction)
   USE WHEN:
   - Content is vague or unstructured
   - Service descriptions or project pages (not standard products)
   - Requires semantic understanding to extract meaningful data
   - Non-standard content format or mixed content types
   - Page has narrative descriptions rather than structured data
   - Product info embedded in paragraphs/stories

Return JSON with:
{{
  "extraction_method": "INTERACTIVE" | "STATIC" | "AI",
  "use_interactive": boolean (for backward compatibility),
  "reason": "string - explanation of chosen method",
  "recommended_url": "string - best URL to extract from",
  "complexity_score": number (0-10),
  "requires_clicks": boolean,
  "has_dynamic_content": boolean,
  "content_structure": "structured" | "semi-structured" | "unstructured"
}}

DECISION RULES:
- If interactive elements require clicking → INTERACTIVE
- If all data is visible in clean HTML/markdown → STATIC  
- If content is vague, narrative, or needs semantic extraction → AI
- Default to STATIC for typical product pages

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
            
            # Ensure extraction_method is set (backward compatibility)
            if 'extraction_method' not in result:
                result['extraction_method'] = 'INTERACTIVE' if result.get('use_interactive') else 'STATIC'
            
            # Ensure use_interactive is set (backward compatibility)
            if 'use_interactive' not in result:
                result['use_interactive'] = (result.get('extraction_method') == 'INTERACTIVE')
            
            return result
            
        except Exception as e:
            print(f"  ⚠️ Gemini consultation failed: {e}")
            return {
                'extraction_method': 'STATIC',
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
        gemini_api_key: Optional[str] = None,
        force_ai: bool = False,
        headless: bool = False,
        optimize_results: bool = True
    ):
        """
        Initialize LAM scraper.
        
        Args:
            config: Scraper configuration
            strictness: Classification strictness
            enable_gemini: Enable Gemini interactive extraction
            gemini_api_key: Optional Gemini API key
            force_ai: Force Gemini AI extraction even for static sites
            headless: Run Playwright in headless mode (default True for server environments)
            optimize_results: Enable post-processing optimization to remove duplicates and invalid entries
        """
        # Initialize parent (BalancedScraper)
        super().__init__(config, strictness=strictness)
        
        # Initialize Gemini components
        self.enable_gemini = enable_gemini
        self.force_ai = force_ai
        self.headless = headless
        self.optimize_results = optimize_results
        self.gemini_consultant = GeminiConfiguatorConsultant(gemini_api_key)
        self.gemini_extractor = None
        
        # Initialize optimizer
        if optimize_results:
            try:
                self.optimizer = CatalogOptimizer(
                    gemini_api_key=gemini_api_key,
                    user_intent=config.user_intent
                )
            except Exception as e:
                print(f"⚠️  Optimizer initialization failed: {e}")
                self.optimize_results = False
                self.optimizer = None
        else:
            self.optimizer = None
        
        if enable_gemini and self.gemini_consultant.enabled:
            try:
                # Import from the correct location
                from ..extractors.gemini_interactive_extractor import GeminiInteractiveExtractor
                self.gemini_extractor = GeminiInteractiveExtractor(gemini_api_key, headless=headless)
                headless_msg = "headless" if headless else "headed"
                print(f"  ✓ Gemini interactive extraction enabled ({headless_msg} mode)")
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
            'ai_extractions': 0,
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
    
    async def _extract_with_ai_method(
        self,
        url: str,
        markdown: str,
        product_name: str,
        config_info: Dict
    ) -> Optional[List[Dict]]:
        """
        Extract product data using AI semantic extraction (Gemini).
        
        This method is used when Gemini determines the page content requires
        semantic understanding rather than structured extraction.
        
        Args:
            url: Product page URL
            markdown: Page content
            product_name: Product name
            config_info: Configurator info
            
        Returns:
            List of product dictionaries or None if extraction fails
        """
        try:
            import json
            from ..utils.http_client import JinaClient
            
            # Fetch fresh content with Jina for better quality
            jina_client = JinaClient(api_key=os.getenv('JINA_API_KEY'))
            try:
                page = jina_client.fetch(url)
                markdown = page.text
                page_title = page.title
            except Exception as e:
                print(f"     ⚠️ Jina fetch failed, using existing markdown: {e}")
                page_title = product_name
            
            if not markdown:
                return None
            
            # Use Gemini for semantic extraction
            prompt = f"""
You are extracting structured product data from a webpage using semantic understanding.

URL: {url}
PAGE TITLE: {page_title}
PRODUCT NAME: {product_name}

PAGE CONTENT (first 8000 chars):
{markdown[:8000]}

TASK:
Extract ALL products/services/projects/offerings from this page with semantic understanding.

CRITICAL DISTINCTION:
- If the page shows DIFFERENT PRODUCTS/MODELS → Extract each as SEPARATE item
- If the page shows ONE PRODUCT with OPTIONS → Extract as ONE item with customizations

OUTPUT STRICT JSON (ARRAY):
[
  {{
    "product_name": "Name of product",
    "page_type": "PRODUCT or OFFERING",
    "base_price": "Price string or null",
    "price_note": "Custom quote, Starting from, etc.",
    "specifications": {{
      "spec_name": "value"
    }},
    "customizations": {{
      "category": ["option1", "option2"]
    }},
    "description": "Brief product description",
    "features": ["feature1", "feature2"]
  }}
]

RULES:
- Use semantic understanding to extract meaningful data
- If multiple distinct products exist, create SEPARATE array items
- If ONE product with options exists, create ONE array item with customizations
- specifications: technical specs, dimensions, materials
- customizations: options/variants for this product
- If no price shown, set base_price to null and price_note to "Custom quote"
- Return ONLY JSON array, no explanations
- Even if only one item, return it in an array
"""
            
            # Initialize Gemini model
            if not hasattr(self, '_ai_gemini_model'):
                import google.generativeai as genai
                api_key = os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
                genai.configure(api_key=api_key)
                self._ai_gemini_model = genai.GenerativeModel("gemini-2.5-flash")
            
            response = self._ai_gemini_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )
            
            extracted_data = json.loads(response.text)
            
            # Ensure we have a list
            if isinstance(extracted_data, dict):
                extracted_data = [extracted_data]
            elif not isinstance(extracted_data, list):
                print(f"     ✗ Gemini returned invalid format: {type(extracted_data)}")
                return None
            
            if not extracted_data:
                print(f"     ✗ Gemini returned empty list")
                return None
            
            # Build final product data for each extracted item
            products_list = []
            for item in extracted_data:
                if not isinstance(item, dict):
                    continue
                
                product_data = {
                    "product_name": item.get("product_name", product_name),
                    "url": url,
                    "page_type": item.get("page_type", "PRODUCT"),
                    "base_price": item.get("base_price"),
                    "price_note": item.get("price_note", ""),
                    "specifications": item.get("specifications", {}),
                    "customizations": item.get("customizations", {}),
                    "description": item.get("description", ""),
                    "features": item.get("features", []),
                    "total_customization_options": sum(
                        len(opts) for opts in item.get("customizations", {}).values()
                    ),
                    
                    # LAM metadata
                    "extraction_method": "ai_semantic",
                    "model": "LAM",
                    "has_configurator": config_info.get('has_configurator'),
                    "configurator_type": config_info.get('configurator_type'),
                    "detection_method": config_info.get('detection_method')
                }
                products_list.append(product_data)
            
            if products_list:
                print(f"     ✓ AI extraction successful: {len(products_list)} item(s)")
                self.lam_stats['ai_extractions'] += 1
                return products_list
            else:
                print(f"     ✗ No valid items extracted")
                return None
        
        except Exception as e:
            print(f"     ✗ AI extraction failed: {e}")
            return None
    
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
            target_url = (
                configurator_info.get('configurator_url')
                if configurator_info.get('configurator_url')
                else url
            )

            options = await self.gemini_extractor.interactive_extraction(
                target_url,
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
    
    async def scrape_all_products(self, product_urls: List[str] = None) -> Dict:
        """Enhanced LAM workflow: Get product URLs → Detect configurators → Extract.
        
        Args:
            product_urls: Optional pre-discovered product URLs (from any crawler)
                         If None, uses identify_all_product_pages() to discover
        """
        print(f"\n{'='*80}")
        print(f"[LAM MODEL] Starting Enhanced Workflow")
        print(f"{'='*80}")
        
        # Step 1: Get product URLs (either provided or discover)
        if product_urls is None:
            product_urls = self.identify_all_product_pages()
        else:
            product_urls = list(product_urls)
            print(f"\nUsing {len(product_urls)} pre-discovered product URLs")
        
        if not product_urls:
            print("\n❌ No product pages found")
            return {'products': [], 'total_products': 0}
        
        # Step 2: Detect configurators with Gemini
        configurator_map = self.detect_configurators_with_gemini(product_urls)
        
        # Check if any configurators were found
        configurators_found = sum(1 for c in configurator_map.values() if c['has_configurator'])
        
        if configurators_found == 0 and not self.force_ai:
            print(f"\n{'='*40}")
            print(f"🧠  NO CONFIGURATORS DETECTED")
            print(f"🧠  Automatically switching to AI Semantic Extraction")
            print(f"🧠  Using Gemini for intelligent content understanding")
            print(f"{'='*40}\n")
            
            # Use AI extraction for all pages when no configurators detected
            products = []
            for i, url in enumerate(product_urls, 1):
                print(f"\n[{i}/{len(product_urls)}] Processing with AI Extraction: {url}")
                
                # Fetch page content
                markdown = self.http_client.scrape_with_jina(url)
                if not markdown:
                    print(f"  ✗ Failed to fetch page")
                    continue
                
                # Extract basic info for AI method
                product_name = self.product_extractor.extract_product_name(url, markdown)
                config_info = {
                    'has_configurator': False,
                    'configurator_type': 'none',
                    'confidence': 0.0,
                    'detection_method': 'none'
                }
                
                # Use AI extraction method
                print(f"  🧠 Using AI semantic extraction...")
                products_from_page = await self._extract_with_ai_method(url, markdown, product_name, config_info)
                
                if products_from_page:
                    products.extend(products_from_page)
                    print(f"  ✓ Added {len(products_from_page)} item(s) from AI extraction")
                else:
                    print(f"  ✗ AI extraction failed")
                
                # Respect crawl delay
                if i < len(product_urls):
                    await asyncio.sleep(self.config.crawl_delay)
            
            catalog = {
                'products': products,
                'total_products': len(products),
                'configurators_detected': 0,
                'model': 'LAM (AI Extraction Mode)',
                'workflow': 'ai_semantic_extraction'
            }
            
            print(f"\n{'='*80}")
            print(f"[LAM-AI] Extraction Complete")
            print(f"{'='*80}")
            print(f"  Total products: {len(products)}")
            print(f"  Extraction method: AI Semantic")
            
            return catalog
        
        elif configurators_found == 0 and self.force_ai:
            print(f"\n{'🤖'*40}")
            print(f"🤖  NO CONFIGURATORS DETECTED")
            print(f"🤖  FORCE AI MODE ENABLED - Using Gemini for all pages")
            print(f"{'🤖'*40}\n")
        
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
            
            # Scrape the product with LAM method (now async, returns list)
            products_from_page = await self._scrape_product_with_config_info(url, config_info)
            
            if products_from_page:
                products.extend(products_from_page)
                if len(products_from_page) > 1:
                    print(f"  ✓ Added {len(products_from_page)} products from this page")
            
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
    
    async def _scrape_product_with_config_info(self, url: str, config_info: Dict) -> Optional[List[Dict]]:
        """Scrape a product with pre-detected configurator information.
        
        Returns:
            List of product dictionaries (multiple if page contains multiple products)
        """
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
        
        # Consult Gemini for extraction method (if enabled)
        if self.gemini_consultant.enabled and config_info.get('has_configurator'):
            self.lam_stats['gemini_consultations'] += 1
            
            print(f"  🤖 Consulting Gemini for extraction method...")
            consultation = self.gemini_consultant.should_use_interactive_extraction(
                url, config_info, markdown
            )
            
            recommended_method = consultation.get('extraction_method', 'STATIC')
            print(f"  🤖 Gemini recommends: {recommended_method}")
            print(f"     Reason: {consultation.get('reason', 'N/A')}")
            
            # Route to appropriate extraction method
            if recommended_method == 'INTERACTIVE' and self.gemini_extractor:
                # Use Gemini + Playwright interactive extraction
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
            
            elif recommended_method == 'AI':
                # Use AI semantic extraction
                print(f"  🧠 Using AI semantic extraction...")
                result = await self._extract_with_ai_method(url, markdown, product_name, config_info)
                if result:
                    # AI extraction returns complete product data
                    return result
                else:
                    # Fallback to static
                    extraction_method = self._extract_static_fallback(
                        url, markdown, product_name, config_info
                    )
                    customizations = self._get_extracted_customizations()
                    self.lam_stats['static_fallbacks'] += 1
            
            else:
                # Use static extraction (STATIC method or fallback)
                extraction_method = self._extract_static_fallback(
                    url, markdown, product_name, config_info
                )
                customizations = self._get_extracted_customizations()
                self.lam_stats['static_fallbacks'] += 1
        
        # Legacy path: Direct decision based on requires_interaction flag
        elif config_info.get('requires_interaction') and self.gemini_extractor:
            # Use Gemini + Playwright
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
            # No configurator detected on this page - use AI semantic extraction
            print(f"  🧠 No configurator detected - using AI semantic extraction...")
            result = await self._extract_with_ai_method(url, markdown, product_name, config_info)
            if result:
                # AI extraction returns complete product data
                return result
            else:
                # Fallback to basic extraction if AI fails
                print(f"  ⚠️ AI extraction failed, using basic extraction...")
                customizations = self.product_extractor.extract_customizations(markdown)
                extraction_method = 'product_page'
        
        # Check if customizations are actually multiple distinct products
        products_list = self._split_multiple_products(
            url=url,
            product_name=product_name,
            base_price=base_price,
            specifications=specifications,
            customizations=customizations,
            extraction_method=extraction_method,
            config_info=config_info
        )
        
        if len(products_list) > 1:
            print(f"  ✓ Split into {len(products_list)} separate products")
        
        return products_list
    
    def _split_multiple_products(
        self, 
        url: str,
        product_name: str,
        base_price: str,
        specifications: Dict,
        customizations: Dict,
        extraction_method: str,
        config_info: Dict
    ) -> List[Dict]:
        """Use Gemini to intelligently determine if customizations are separate products.
        
        Distinguishes between:
        - Different products/models (each gets its own entry)
        - Actual customizations (options for the SAME product)
        
        Returns:
            List of product dictionaries
        """
        if not customizations or not self.gemini_consultant.enabled:
            # No customizations or Gemini not available - return single product
            return [{
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
            }]
        
        # Ask Gemini to analyze if these are separate products or customizations
        try:
            import json
            
            prompt = f"""
Analyze these extracted options to determine if they are SEPARATE PRODUCTS or CUSTOMIZATIONS of the same product.

Original Product/Page: {product_name}
URL: {url}

Extracted Options by Category:
{json.dumps(customizations, indent=2)}

TASK: For each category, determine if the items are:
1. SEPARATE_PRODUCTS: Different products/models that should each get their own entry
   - Example: Different RV models, different floor plans, different product lines
   - Each item is a complete standalone product
   - Selecting one means you're choosing a different product entirely

2. CUSTOMIZATIONS: Options/variants for the SAME product
   - Example: Paint colors, interior fabrics, add-on features
   - These are modifications to the same base product
   - You can have multiple customizations together

CLUES FOR SEPARATE PRODUCTS:
- Category names like: "Select a model", "Choose your coach", "Available models"
- Items have distinctive names (e.g., "2026 King Aire", "2026 Essex", "2026 London Aire")
- Items often have images and may have prices
- Items are fundamentally different products

CLUES FOR CUSTOMIZATIONS:
- Category names like: "Exterior colors", "Interior fabric", "Optional features"
- Items are variations of the same thing (e.g., "Red", "Blue", "Green")
- Items modify/enhance the base product
- Multiple can be selected together

Return JSON:
{{
  "categories_analysis": [
    {{
      "category_name": "string",
      "classification": "SEPARATE_PRODUCTS" | "CUSTOMIZATIONS",
      "confidence": 0.0-1.0,
      "reasoning": "why you classified it this way",
      "sample_items": ["first 3 item names"]
    }}
  ],
  "recommended_split": {{
    "should_split": boolean,
    "split_category": "category name to split on" or null,
    "reasoning": "explain why or why not"
  }}
}}

Only return valid JSON.
"""
            
            response = self.gemini_consultant.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json"
                }
            )
            
            analysis = json.loads(response.text)
            
            # Check if we should split
            should_split = analysis.get('recommended_split', {}).get('should_split', False)
            split_category = analysis.get('recommended_split', {}).get('split_category')
            
            if not should_split or not split_category:
                print(f"  ℹ️  Gemini: No product splitting needed - these are customizations")
                # Return as single product
                return [{
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
                }]
            
            # Split into multiple products
            print(f"  🤖 Gemini: Detected separate products in category '{split_category}'")
            print(f"     Reason: {analysis.get('recommended_split', {}).get('reasoning', 'N/A')}")
            
            products_list = []
            product_items = customizations.get(split_category, [])
            
            # Remove the products category from remaining customizations
            remaining_customizations = {k: v for k, v in customizations.items() if k != split_category}
            
            for idx, item in enumerate(product_items):
                if isinstance(item, dict):
                    item_name = item.get('label', f'{product_name} - Item {idx+1}')
                    item_price = item.get('price')
                    item_image = item.get('image')
                else:
                    item_name = str(item)
                    item_price = None
                    item_image = None
                
                # Create separate product entry
                product_dict = {
                    'product_name': item_name,
                    'url': f"{url}#product-{idx+1}",
                    'source_url': url,
                    'base_price': item_price or base_price,
                    'product_image': item_image,
                    'specifications': specifications.copy(),
                    'extraction_method': extraction_method,
                    'model': 'LAM',
                    'has_configurator': config_info.get('has_configurator'),
                    'configurator_type': config_info.get('configurator_type'),
                    'requires_interaction': config_info.get('requires_interaction'),
                    'detection_method': config_info.get('detection_method'),
                    'customizations': remaining_customizations.copy(),
                    'customization_categories': list(remaining_customizations.keys()),
                    'total_customization_options': sum(len(opts) for opts in remaining_customizations.values()),
                    'extracted_from_multi_product_page': True,
                    'split_reasoning': analysis.get('recommended_split', {}).get('reasoning', '')
                }
                
                products_list.append(product_dict)
            
            return products_list
            
        except Exception as e:
            print(f"  ⚠️  Gemini analysis failed: {e}")
            print(f"     Falling back to heuristic-based detection")
            
            # Fallback to simple heuristic-based detection
            return self._split_multiple_products_heuristic(
                url, product_name, base_price, specifications,
                customizations, extraction_method, config_info
            )
    
    def _split_multiple_products_heuristic(
        self,
        url: str,
        product_name: str,
        base_price: str,
        specifications: Dict,
        customizations: Dict,
        extraction_method: str,
        config_info: Dict
    ) -> List[Dict]:
        """Fallback heuristic-based product splitting (original logic)."""
        product_indicating_categories = [
            'start by selecting',
            'select a model',
            'choose a model',
            'select a coach',
            'choose a coach',
            'select your',
            'choose your',
            'available models',
            'available coaches',
            'available products',
            'product selection',
            'model selection'
        ]
        
        # Check if any customization category indicates multiple products
        multiple_products_detected = False
        products_category = None
        
        for category_name in customizations.keys():
            category_lower = category_name.lower()
            if any(indicator in category_lower for indicator in product_indicating_categories):
                multiple_products_detected = True
                products_category = category_name
                break
        
        # Also detect if category has many items (>5) with images and prices
        if not multiple_products_detected:
            for category_name, items in customizations.items():
                if len(items) > 5:
                    # Count how many have images
                    items_with_images = sum(1 for item in items if isinstance(item, dict) and item.get('image'))
                    if items_with_images > 5:
                        multiple_products_detected = True
                        products_category = category_name
                        break
        
        if not multiple_products_detected:
            # Return as single product
            return [{
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
            }]
        
        # Split into multiple products
        products_list = []
        product_items = customizations.get(products_category, [])
        
        # Remove the products category from customizations
        remaining_customizations = {k: v for k, v in customizations.items() if k != products_category}
        
        for idx, item in enumerate(product_items):
            if isinstance(item, dict):
                item_name = item.get('label', f'{product_name} - Item {idx+1}')
                item_price = item.get('price')
                item_image = item.get('image')
            else:
                item_name = str(item)
                item_price = None
                item_image = None
            
            # Create separate product entry
            product_dict = {
                'product_name': item_name,
                'url': f"{url}#product-{idx+1}",  # Add anchor to make unique
                'source_url': url,  # Keep original URL for reference
                'base_price': item_price or base_price,
                'product_image': item_image,
                'specifications': specifications.copy(),
                'extraction_method': extraction_method,
                'model': 'LAM',
                'has_configurator': config_info.get('has_configurator'),
                'configurator_type': config_info.get('configurator_type'),
                'requires_interaction': config_info.get('requires_interaction'),
                'detection_method': config_info.get('detection_method'),
                'customizations': remaining_customizations.copy(),
                'customization_categories': list(remaining_customizations.keys()),
                'total_customization_options': sum(len(opts) for opts in remaining_customizations.values()),
                'extracted_from_multi_product_page': True
            }
            
            products_list.append(product_dict)
        
        return products_list
    
    def print_statistics(self):
        """Print scraping statistics including LAM-specific stats."""
        # Call parent statistics
        super().print_statistics()
        
        # Add LAM stats
        print(f"\n\033[36m[LAM STATS]\033[0m Gemini Usage:")
        print(f"   Gemini consultations: {self.lam_stats['gemini_consultations']}")
        print(f"   Interactive extractions: {self.lam_stats['interactive_extractions']}")
        print(f"   AI semantic extractions: {self.lam_stats['ai_extractions']}")
        print(f"   Static fallbacks: {self.lam_stats['static_fallbacks']}")
        print(f"   Gemini failures: {self.lam_stats['gemini_failures']}")
        
        if self.lam_stats['gemini_consultations'] > 0:
            success_rate = (
                (self.lam_stats['interactive_extractions'] + self.lam_stats['ai_extractions'])
                / self.lam_stats['gemini_consultations'] * 100
            )
            print(f"   Gemini success rate: {success_rate:.1f}%")
