"""Intelligent Scraper Selector
---------------------------------
Uses Gemini to analyze URLs and route them to the optimal scraper:
- LAM: Interactive configurators, complex customization flows
- Static (BalancedScraper): Standard product pages with clear structure
- AI: Vague information, services, projects, case studies, non-standard content

Workflow:
1. Receive list of discovered URLs from crawler
2. Batch analyze with Gemini to determine content type
3. Route each URL to appropriate scraper
4. Aggregate results
"""

import os
import json
import asyncio
from typing import Dict, List, Set, Optional
from dataclasses import dataclass

import google.generativeai as genai

from .config import ScraperConfig
from .balanced_scraper import BalancedScraper
from .lam_scraper import LAMScraper
from .ai_scraper import AIScraper


@dataclass
class ScraperAssignment:
    """Assignment of URL to specific scraper."""
    url: str
    scraper_type: str  # 'LAM' | 'STATIC' | 'AI'
    confidence: float
    reasoning: str
    page_characteristics: Dict


class ScraperSelector:
    """Intelligent selector that routes URLs to optimal scrapers."""
    
    def __init__(
        self,
        config: ScraperConfig,
        gemini_api_key: Optional[str] = None,
        user_intent: Optional[str] = None,
        optimize_results: bool = True
    ):
        """
        Initialize scraper selector.
        
        Args:
            config: Scraper configuration
            gemini_api_key: Gemini API key for analysis
            user_intent: User's extraction intent (for AI scraper)
            optimize_results: Enable post-processing optimization to remove duplicates and invalid entries
        """
        self.config = config
        self.user_intent = user_intent or config.user_intent or "Extract product information"
        self.optimize_results = optimize_results
        
        # Get API key
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY not found - required for intelligent routing")
        
        # Initialize Gemini
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Initialize scrapers (lazy)
        self._lam_scraper = None
        self._static_scraper = None
        self._ai_scraper = None
        
        # Initialize optimizer
        if optimize_results:
            try:
                self.optimizer = CatalogOptimizer(
                    gemini_api_key=self.gemini_api_key,
                    user_intent=self.user_intent
                )
            except Exception as e:
                print(f"⚠️  Optimizer initialization failed: {e}")
                self.optimize_results = False
                self.optimizer = None
        else:
            self.optimizer = None
        
        # Statistics
        self.stats = {
            'total_urls': 0,
            'lam_assigned': 0,
            'static_assigned': 0,
            'ai_assigned': 0,
            'blog_skipped': 0,
            'errors': 0
        }
        
        print(f"\033[32m[✓]\033[0m Scraper Selector initialized")
        print(f"  Mode: Intelligent Routing (Gemini-powered)")
        print(f"  Intent: {self.user_intent}")
    
    def _is_blog_or_faq_url(self, url: str) -> bool:
        """Detect if URL is a blog, FAQ, or question-based content page."""
        url_lower = url.lower()
        
        # Common blog/FAQ/question patterns in URLs
        blog_patterns = [
            '/blog', '/blogs', '/article', '/articles', '/news',
            '/faq', '/faqs', '/questions', '/q-and-a', '/qa',
            '/how-to', '/guide', '/guides', '/tips', '/advice',
            '/learn', '/learning', '/tutorial', '/tutorials',
            '/what-is', '/why-', '/when-', '/where-', '/how-',
            '/resources', '/insights', '/stories', '/posts',
            '?p=', '?page_id=', '?article=', '?post='
        ]
        
        return any(pattern in url_lower for pattern in blog_patterns)
    
    def _get_lam_scraper(self) -> LAMScraper:
        """Lazy initialize LAM scraper."""
        if self._lam_scraper is None:
            self._lam_scraper = LAMScraper(
                config=self.config,
                strictness="balanced",
                enable_gemini=True,
                gemini_api_key=self.gemini_api_key,
                force_ai=False,
                headless=False
            )
        return self._lam_scraper
    
    def _get_static_scraper(self) -> BalancedScraper:
        """Lazy initialize static scraper."""
        if self._static_scraper is None:
            self._static_scraper = BalancedScraper(
                config=self.config,
                strictness="balanced"
            )
        return self._static_scraper
    
    def _get_ai_scraper(self) -> AIScraper:
        """Lazy initialize AI scraper."""
        if self._ai_scraper is None:
            self._ai_scraper = AIScraper(
                config=self.config,
                user_intent=self.user_intent,
                gemini_api_key=self.gemini_api_key
            )
        return self._ai_scraper
    
    async def analyze_and_scrape(
        self,
        product_urls: Set[str]
    ) -> Dict:
        """
        Analyze URLs, route to appropriate scrapers, and aggregate results.
        
        Args:
            product_urls: Set of product URLs to scrape
            
        Returns:
            Aggregated catalog from all scrapers
        """
        print(f"\n{'='*80}")
        print("INTELLIGENT SCRAPER SELECTION")
        print(f"{'='*80}")
        print(f"Total URLs to analyze: {len(product_urls)}")
        print(f"{'='*80}\n")
        
        self.stats['total_urls'] = len(product_urls)
        
        # Step 0: Pre-filter blog and FAQ URLs
        print("Phase 0: Pre-filtering blog/FAQ URLs...")
        print("-" * 80)
        filtered_urls = []
        blog_urls = []
        
        for url in product_urls:
            if self._is_blog_or_faq_url(url):
                blog_urls.append(url)
                print(f"  📝 SKIPPING (Blog/FAQ): {url}")
            else:
                filtered_urls.append(url)
        
        self.stats['blog_skipped'] = len(blog_urls)
        
        if blog_urls:
            print(f"\n✓ Filtered out {len(blog_urls)} blog/FAQ URLs")
        print(f"✓ {len(filtered_urls)} URLs remaining for analysis\n")
        
        if not filtered_urls:
            print("⚠️  No URLs remaining after filtering")
            return {
                'products': [],
                'total_products': 0,
                'scraper_assignments': {'lam': 0, 'static': 0, 'ai': 0, 'blog_skipped': len(blog_urls)},
                'model': 'INTELLIGENT_ROUTING',
                'workflow': 'analyze_then_route'
            }
        
        # Step 1: Analyze remaining URLs and assign scrapers
        assignments = await self._analyze_urls(filtered_urls)
        
        # Step 2: Group by scraper type (filter out SKIP/BLOG types)
        lam_urls = [a.url for a in assignments if a.scraper_type == 'LAM']
        static_urls = [a.url for a in assignments if a.scraper_type == 'STATIC']
        ai_urls = [a.url for a in assignments if a.scraper_type == 'AI']
        
        # Count additional blog/skip classifications from Gemini
        gemini_skipped = [a for a in assignments if a.scraper_type in ['SKIP', 'BLOG']]
        if gemini_skipped:
            self.stats['blog_skipped'] += len(gemini_skipped)
            print(f"\n📝 Gemini detected {len(gemini_skipped)} additional blog/FAQ URLs to skip")
            for assignment in gemini_skipped:
                print(f"  → {assignment.url}")
                print(f"     Reason: {assignment.reasoning}")
        
        self.stats['lam_assigned'] = len(lam_urls)
        self.stats['static_assigned'] = len(static_urls)
        self.stats['ai_assigned'] = len(ai_urls)
        
        print(f"\n📊 Assignment Summary:")
        print(f"   LAM Scraper: {len(lam_urls)} URLs (interactive configurators)")
        print(f"   Static Scraper: {len(static_urls)} URLs (standard products)")
        print(f"   AI Scraper: {len(ai_urls)} URLs (vague/services/projects)")
        print(f"   Skipped (Blogs/FAQs): {self.stats['blog_skipped']} URLs")
        
        # Step 3: Scrape with assigned scrapers
        all_products = []
        
        # LAM scraper
        if lam_urls:
            print(f"\n{'='*80}")
            print(f"SCRAPING WITH LAM SCRAPER ({len(lam_urls)} URLs)")
            print(f"{'='*80}")
            lam_scraper = self._get_lam_scraper()
            lam_results = await lam_scraper.scrape_all_products(product_urls=lam_urls)
            all_products.extend(lam_results.get('products', []))
        
        # Static scraper
        if static_urls:
            print(f"\n{'='*80}")
            print(f"SCRAPING WITH STATIC SCRAPER ({len(static_urls)} URLs)")
            print(f"{'='*80}")
            static_scraper = self._get_static_scraper()
            for url in static_urls:
                product_data = static_scraper.scrape_product(url)
                if product_data:
                    all_products.append(product_data)
        
        # AI scraper
        if ai_urls:
            print(f"\n{'='*80}")
            print(f"SCRAPING WITH AI SCRAPER ({len(ai_urls)} URLs)")
            print(f"{'='*80}")
            ai_scraper = self._get_ai_scraper()
            ai_results = await ai_scraper.scrape_all_products(product_urls=set(ai_urls))
            
            # AI scraper returns dict with URLs as keys
            for url, product_data in ai_results.items():
                if isinstance(product_data, list):
                    all_products.extend(product_data)
                else:
                    all_products.append(product_data)
        
        # Step 4: Build final catalog
        catalog = {
            'products': all_products,
            'total_products': len(all_products),
            'scraper_assignments': {
                'lam': len(lam_urls),
                'static': len(static_urls),
                'ai': len(ai_urls),
                'blog_skipped': self.stats['blog_skipped']
            },
            'model': 'INTELLIGENT_ROUTING',
            'workflow': 'analyze_then_route'
        }
        
        # Optimize catalog if enabled
        if self.optimize_results and self.optimizer:
            print(f"\n{'='*80}")
            print("OPTIMIZING RESULTS")
            print(f"{'='*80}")
            catalog = await self.optimizer.optimize_catalog(catalog)
        
        self._print_final_summary(catalog)
        
        return catalog
    
    async def _analyze_urls(
        self,
        urls: List[str],
        batch_size: int = 20
    ) -> List[ScraperAssignment]:
        """
        Analyze URLs in batches and assign scrapers.
        
        Args:
            urls: List of URLs to analyze
            batch_size: Number of URLs per batch
            
        Returns:
            List of scraper assignments
        """
        print("\nPhase 1: Analyzing URLs with Gemini...")
        print("-" * 80)
        
        all_assignments = []
        
        # Process in batches
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i+batch_size]
            print(f"\nAnalyzing batch {i//batch_size + 1} ({len(batch)} URLs)...")
            
            assignments = await self._analyze_batch(batch)
            all_assignments.extend(assignments)
            
            # Rate limiting
            if i + batch_size < len(urls):
                await asyncio.sleep(1)
        
        return all_assignments
    
    async def _analyze_batch(
        self,
        urls: List[str]
    ) -> List[ScraperAssignment]:
        """Analyze a batch of URLs with Gemini."""
        
        # Build prompt
        url_list = "\n".join([f"{i+1}. {url}" for i, url in enumerate(urls)])
        
        prompt = f"""
You are analyzing web pages to determine the BEST SCRAPER for each URL.

USER INTENT:
{self.user_intent}

URLS TO ANALYZE:
{url_list}

AVAILABLE SCRAPERS:

1. **LAM SCRAPER** (Gemini + Playwright Interactive Extraction)
   USE FOR:
   - Pages with interactive configurators
   - Build-your-own / customize product interfaces
   - Multi-step configuration flows
   - Dynamic content that reveals options on interaction
   - Complex product builders
   
   SIGNALS:
   - URL contains: /configure, /customize, /build, /design, /builder
   - Page likely has dropdowns, tabs, option cards that require clicking
   - Configurator that needs user interaction to reveal all options

2. **STATIC SCRAPER** (Traditional HTML/Markdown Extraction)
   USE FOR:
   - Standard product pages with clear structure
   - Product details visible in HTML/markdown
   - Simple option lists (sizes, colors) visible on page
   - Well-structured e-commerce pages
   - All information is static and extractable without interaction
   
   SIGNALS:
   - Standard product page URL pattern
   - Clear product name, price, specifications visible
   - Options listed as simple HTML elements
   - Traditional e-commerce structure

3. **AI SCRAPER** (Gemini-powered Semantic Extraction)
   USE FOR:
   - Vague or unstructured content
   - Service descriptions (not physical products)
   - Past projects / case studies / portfolio items
   - Custom work examples
   - Pages without clear product structure
   - Content that requires semantic understanding
   - Non-standard content formats
   
   SIGNALS:
   - Service-oriented pages
   - Project galleries / case studies
   - Custom work examples
   - Unclear structure or mixed content types
   - Requires semantic understanding to extract value
   - Not a traditional product page

4. **SKIP** (Do Not Scrape)
   USE FOR:
   - Blog posts and articles about products
   - FAQ pages with questions and answers
   - Question-based content (How-to, What is, Why, etc.)
   - News articles and press releases
   - Educational content and tutorials
   - General information pages without products
   - Resource pages and guides
   
   SIGNALS:
   - URL contains: /blog, /article, /faq, /questions, /how-to, /guide, /news
   - Page title suggests blog/article/FAQ format
   - Question-based titles ("How to...", "What is...", "Why...", etc.)
   - Informational content without product listings
   - Educational or news-oriented content

TASK: For each URL, determine the BEST scraper.

Return JSON array:
[
  {{
    "url_number": 1,
    "scraper_type": "LAM" | "STATIC" | "AI" | "SKIP",
    "confidence": 0.85,
    "reasoning": "brief explanation of why this scraper",
    "page_characteristics": {{
      "has_configurator": boolean,
      "is_interactive": boolean,
      "is_service": boolean,
      "is_project": boolean,
      "is_structured": boolean,
      "is_blog": boolean,
      "is_faq": boolean,
      "content_type": "product|service|project|configurator|standard|blog|faq"
    }}
  }}
]

IMPORTANT DECISION RULES:
- **HIGHEST PRIORITY**: If URL is blog/FAQ/question-based/news/article → SKIP
- If URL suggests configurator (build/configure/customize) → LAM
- If URL is standard product with clear structure → STATIC
- If page is service/project/case-study/vague → AI
- Default to STATIC for typical product pages
- Use LAM only when interaction is needed
- Use AI when content is non-standard or semantic extraction helps
- **ALWAYS SKIP** blogs, FAQs, news articles, how-to guides, and question-based content

Return valid JSON only, no explanations.
"""
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.2,
                    "response_mime_type": "application/json"
                }
            )
            
            analyses = json.loads(response.text)
            
            assignments = []
            for item in analyses:
                url_num = item.get('url_number', 0) - 1
                if 0 <= url_num < len(urls):
                    assignment = ScraperAssignment(
                        url=urls[url_num],
                        scraper_type=item.get('scraper_type', 'STATIC'),
                        confidence=float(item.get('confidence', 0.5)),
                        reasoning=item.get('reasoning', ''),
                        page_characteristics=item.get('page_characteristics', {})
                    )
                    assignments.append(assignment)
                    
                    # Print assignment
                    icon = {
                        'LAM': '🤖',
                        'STATIC': '📄',
                        'AI': '🧠',
                        'SKIP': '🚫',
                        'BLOG': '📝'
                    }.get(assignment.scraper_type, '❓')
                    
                    print(f"  {icon} {assignment.scraper_type:8} → {urls[url_num]}")
                    print(f"     Reason: {assignment.reasoning}")
            
            return assignments
            
        except Exception as e:
            print(f"  ✗ Batch analysis failed: {e}")
            self.stats['errors'] += 1
            
            # Fallback: assign all to STATIC
            return [
                ScraperAssignment(
                    url=url,
                    scraper_type='STATIC',
                    confidence=0.5,
                    reasoning='Fallback due to analysis error',
                    page_characteristics={}
                )
                for url in urls
            ]
    
    def _print_final_summary(self, catalog: Dict):
        """Print final summary."""
        print(f"\n{'='*80}")
        print("INTELLIGENT ROUTING COMPLETE")
        print(f"{'='*80}")
        print(f"📊 Statistics:")
        print(f"   Total URLs analyzed: {self.stats['total_urls']}")
        print(f"   LAM Scraper: {self.stats['lam_assigned']} URLs")
        print(f"   Static Scraper: {self.stats['static_assigned']} URLs")
        print(f"   AI Scraper: {self.stats['ai_assigned']} URLs")
        print(f"   Skipped (Blogs/FAQs): {self.stats['blog_skipped']} URLs")
        print(f"   Total products extracted: {catalog['total_products']}")
        print(f"   Errors: {self.stats['errors']}")
        print(f"{'='*80}\n")
    
    def save_assignments(self, assignments: List[ScraperAssignment], filepath: str):
        """Save scraper assignments to JSON for debugging."""
        data = [
            {
                'url': a.url,
                'scraper_type': a.scraper_type,
                'confidence': a.confidence,
                'reasoning': a.reasoning,
                'page_characteristics': a.page_characteristics
            }
            for a in assignments
        ]
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✓ Scraper assignments saved: {filepath}")
    
    def save_catalog(self, catalog: Dict, export_formats: list = ['json']):
        """
        Save catalog to file(s).
        
        Args:
            catalog: The catalog to save
            export_formats: List of formats ['json', 'csv', 'csv_prices', 'google_sheets', 'quotation']
        """
        from ..storage.json_storage import JSONStorage
        from ..storage.csv_storage import CSVStorage
        from ..storage.quotation_template import QuotationTemplate
        from ..storage.google_sheets import GoogleSheetsStorage
        
        json_storage = JSONStorage()
        csv_storage = CSVStorage()
        quotation_template = QuotationTemplate()
        google_sheets = None
        
        for fmt in export_formats:
            if fmt == 'json':
                json_storage.save(catalog, self.config.full_output_path)
            
            elif fmt == 'csv':
                csv_path = self.config.full_output_path.replace('.json', '.csv')
                csv_storage.save_simple(catalog, csv_path)
            
            elif fmt == 'csv_prices':
                csv_path = self.config.full_output_path.replace('.json', '_with_prices.csv')
                csv_storage.save_with_prices(catalog, csv_path)
            
            elif fmt == 'quotation':
                quot_path = self.config.full_output_path.replace('.json', '_quotation_template.json')
                quotation_template.create(catalog, quot_path)
            
            elif fmt == 'google_sheets':
                if google_sheets is None:
                    credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
                    google_sheets = GoogleSheetsStorage(credentials_file)
                
                spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID')
                
                if google_sheets.service:
                    google_sheets.save_catalog(
                        catalog,
                        spreadsheet_id=spreadsheet_id,
                        title="Product Catalog"
                    )
    
    def print_summary(self, catalog: Dict):
        """
        Print catalog summary with routing statistics.
        
        Args:
            catalog: The catalog to summarize
        """
        print("\n" + "="*80)
        print("CATALOG SUMMARY")
        print("="*80 + "\n")
        
        # Handle both dict format (product_name: data) and list format (products: [...])
        if isinstance(catalog, dict) and 'products' in catalog:
            # New format
            products = catalog['products']
        else:
            # Old format (dict of product_name: data)
            products = list(catalog.values()) if isinstance(catalog, dict) else []
        
        total_products = len(products)
        if total_products == 0:
            print("No products found.")
            return
        
        print(f"📦 Total Products: {total_products}")
        print(f"\n🤖 Routing Statistics:")
        print(f"   LAM Scraper: {self.stats['lam_assigned']} URLs")
        print(f"   Static Scraper: {self.stats['static_assigned']} URLs")
        print(f"   AI Scraper: {self.stats['ai_assigned']} URLs")
        print(f"   Skipped (Blogs/FAQs): {self.stats['blog_skipped']} URLs")
        print(f"   Errors: {self.stats['errors']}")
        
        # Sample products
        if total_products > 0:
            print(f"\n📋 Sample Products:")
            for i, product in enumerate(products[:3], 1):
                name = product.get('product_name', 'Unknown')
                price = product.get('base_price', 'N/A')
                print(f"   {i}. {name} - ${price}")
            
            if total_products > 3:
                print(f"   ... and {total_products - 3} more")

