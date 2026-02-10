"""Master Flow Recommender
--------------------------
Gemini = System Architect, Not Worker

Responsibilities:
- Decides optimal crawler/scraper combination
- Sets strictness level
- Defines fallback plan
- Enforces stopping rules

Does NOT:
- Scrape pages
- Parse HTML
- Extract products
- Click links

Architecture:
1. Preflight Probe (cheap heuristics) → Site Signal Snapshot
2. Gemini Flow Recommender (strategy) → Execution Contract
3. Orchestrator (execution) → Results
"""

import os
import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, urljoin
import requests
import google.generativeai as genai

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, will use system environment variables


@dataclass
class SiteSignals:
    """Lightweight metadata about a site with essential content."""
    url: str
    homepage_signals: Dict
    url_patterns: List[str]
    js_dependency: bool
    forms_detected: bool
    html_density: str
    keywords_found: List[str]
    # Content signals for Gemini
    page_title: str
    meta_description: str
    sample_text: str  # First 500 chars of visible text
    site_category_hints: List[str]  # e.g., ['sauna', 'wellness', 'construction']
    navbar_links: List[Dict]  # Navigation menu structure - richest signal
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class FlowRecommendation:
    """Execution contract for the orchestrator."""
    crawler: str  # 'web' | 'ai' | 'unified'
    scraper: str  # 'static' | 'lam' | 'ai' | 'auto'
    strictness: str  # 'lenient' | 'balanced' | 'strict'
    reasoning: Dict
    fallback_plan: List[Dict]
    exploration_config: Dict
    
    def to_dict(self) -> Dict:
        return asdict(self)


class PreflightProbe:
    """Cheap heuristic analysis of a site (NO Gemini)."""
    
    def __init__(self, timeout: int = 10):
        """
        Initialize preflight probe.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.jina_available = bool(os.getenv('JINA_API_KEY'))
    
    def probe(self, url: str) -> SiteSignals:
        """
        Analyze site with cheap heuristics.
        
        Args:
            url: Base URL to probe
            
        Returns:
            Site signal snapshot
        """
        print(f"\n🔍 Preflight Probe: {url}")
        
        try:
            # Fetch homepage
            html = self._fetch_homepage(url)
            
            # Extract signals
            homepage_signals = self._analyze_links(html, url)
            url_patterns = self._extract_url_patterns(html)
            js_dependency = self._detect_js_dependency(html)
            forms_detected = self._detect_forms(html)
            html_density = self._estimate_html_density(html)
            keywords_found = self._find_keywords(html)
            
            # Extract content signals for Gemini
            page_title = self._extract_title(html)
            meta_description = self._extract_meta_description(html)
            sample_text = self._extract_sample_text(html)
            site_category_hints = self._detect_site_category(html, url)
            navbar_links = self._extract_navbar_links(html, url)
            
            signals = SiteSignals(
                url=url,
                homepage_signals=homepage_signals,
                url_patterns=url_patterns,
                js_dependency=js_dependency,
                forms_detected=forms_detected,
                html_density=html_density,
                keywords_found=keywords_found,
                page_title=page_title,
                meta_description=meta_description,
                sample_text=sample_text,
                site_category_hints=site_category_hints,
                navbar_links=navbar_links
            )
            
            print(f"  ✓ Signals captured:")
            print(f"    Title: {page_title[:60]}..." if len(page_title) > 60 else f"    Title: {page_title}")
            print(f"    Navbar Links: {len(navbar_links)} ({', '.join([link['text'] for link in navbar_links[:5]])}...)")
            print(f"    Links: {homepage_signals['link_count']}")
            print(f"    URL patterns: {len(url_patterns)}")
            print(f"    JS dependency: {js_dependency}")
            print(f"    Forms: {forms_detected}")
            print(f"    Category hints: {', '.join(site_category_hints[:3])}")
            print(f"    Keywords: {', '.join(keywords_found[:5])}")
            
            return signals
            
        except Exception as e:
            print(f"  ✗ Probe failed: {e}")
            # Return minimal signals
            return SiteSignals(
                url=url,
                homepage_signals={'link_count': 0, 'product_like_links': 0, 'project_like_links': 0, 'blog_like_links': 0},
                url_patterns=[],
                js_dependency=False,
                forms_detected=False,
                html_density='unknown',
                keywords_found=[],
                page_title='',
                meta_description='',
                sample_text='',
                site_category_hints=[],
                navbar_links=[]
            )
    
    def _fetch_homepage(self, url: str) -> str:
        """Fetch homepage HTML."""
        if self.jina_available:
            # Use Jina for better rendering
            jina_url = f"https://r.jina.ai/{url}"
            headers = {'Authorization': f'Bearer {os.getenv("JINA_API_KEY")}'}
            response = requests.get(jina_url, headers=headers, timeout=self.timeout)
            return response.text
        else:
            # Fallback to direct request
            response = requests.get(url, timeout=self.timeout)
            return response.text
    
    def _analyze_links(self, html: str, base_url: str) -> Dict:
        """Analyze link patterns in HTML."""
        # Extract all href attributes
        href_pattern = r'href=["\']([^"\']+)["\']'
        links = re.findall(href_pattern, html, re.IGNORECASE)
        
        # Classify links
        product_keywords = ['product', 'item', 'shop', 'catalog', 'store', 'buy', 'model']
        project_keywords = ['project', 'case-study', 'portfolio', 'work', 'gallery', 'showcase']
        blog_keywords = ['blog', 'news', 'article', 'post', 'story']
        
        product_like = 0
        project_like = 0
        blog_like = 0
        
        for link in links:
            link_lower = link.lower()
            if any(kw in link_lower for kw in product_keywords):
                product_like += 1
            if any(kw in link_lower for kw in project_keywords):
                project_like += 1
            if any(kw in link_lower for kw in blog_keywords):
                blog_like += 1
        
        return {
            'link_count': len(links),
            'product_like_links': product_like,
            'project_like_links': project_like,
            'blog_like_links': blog_like
        }
    
    def _extract_url_patterns(self, html: str) -> List[str]:
        """Extract common URL patterns."""
        href_pattern = r'href=["\']([^"\']+)["\']'
        links = re.findall(href_pattern, html, re.IGNORECASE)
        
        # Extract unique path segments
        patterns = set()
        for link in links:
            try:
                parsed = urlparse(link)
                path = parsed.path.strip('/')
                if path:
                    segments = path.split('/')
                    if segments:
                        patterns.add(f"/{segments[0]}/")
            except:
                pass
        
        return sorted(list(patterns))[:20]  # Top 20 patterns
    
    def _detect_js_dependency(self, html: str) -> bool:
        """Detect if site heavily relies on JavaScript."""
        # Look for SPA frameworks
        spa_indicators = [
            'react', 'vue', 'angular', 'next.js', 'nuxt',
            'data-react', 'ng-app', 'v-app', '__NEXT_DATA__'
        ]
        
        html_lower = html.lower()
        for indicator in spa_indicators:
            if indicator in html_lower:
                return True
        
        # Count script tags
        script_count = len(re.findall(r'<script', html, re.IGNORECASE))
        if script_count > 15:
            return True
        
        return False
    
    def _detect_forms(self, html: str) -> bool:
        """Detect form elements."""
        form_indicators = ['<form', '<input', '<select', '<button']
        html_lower = html.lower()
        return any(indicator in html_lower for indicator in form_indicators)
    
    def _estimate_html_density(self, html: str) -> str:
        """Estimate HTML complexity."""
        tag_count = len(re.findall(r'<[^>]+>', html))
        if tag_count < 100:
            return 'low'
        elif tag_count < 500:
            return 'medium'
        else:
            return 'high'
    
    def _find_keywords(self, html: str) -> List[str]:
        """Find relevant keywords."""
        keywords = [
            'configure', 'build', 'custom', 'customize', 'design',
            'project', 'portfolio', 'case study', 'work',
            'product', 'catalog', 'shop', 'store',
            'service', 'solution', 'offering'
        ]
        
        html_lower = html.lower()
        found = []
        for kw in keywords:
            if kw in html_lower:
                found.append(kw)
        
        return found
    
    def _extract_title(self, html: str) -> str:
        """Extract page title."""
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
        return title_match.group(1).strip() if title_match else ''
    
    def _extract_meta_description(self, html: str) -> str:
        """Extract meta description."""
        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if not desc_match:
            desc_match = re.search(r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']', html, re.IGNORECASE)
        return desc_match.group(1).strip() if desc_match else ''
    
    def _extract_sample_text(self, html: str) -> str:
        """Extract first 500 characters of visible text."""
        # Remove script and style tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:500]
    
    def _detect_site_category(self, html: str, url: str) -> List[str]:
        """Detect site category based on content analysis."""
        html_lower = html.lower()
        url_lower = url.lower()
        
        categories = []
        
        # E-commerce indicators
        if any(term in html_lower for term in ['add to cart', 'shopping cart', 'checkout', 'buy now', 'add to bag']):
            categories.append('e-commerce')
        
        # Configurator indicators
        if any(term in html_lower for term in ['configure', 'build your', 'customize', 'configurator', 'builder']):
            categories.append('configurator')
        
        # Portfolio/Agency indicators
        if any(term in html_lower for term in ['our work', 'portfolio', 'case studies', 'our projects']):
            categories.append('portfolio')
        
        # Service-based indicators
        if any(term in html_lower for term in ['our services', 'what we do', 'service', 'consultation', 'contact us for']):
            categories.append('services')
        
        # Manufacturing/Industrial
        if any(term in html_lower for term in ['manufacturer', 'industrial', 'wholesale', 'distributor']):
            categories.append('manufacturing')
        
        # Construction/Contractor
        if any(term in html_lower for term in ['contractor', 'construction', 'installation', 'remodeling']):
            categories.append('construction')
        
        # Detect specific industries from URL and content
        industry_keywords = {
            'sauna': ['sauna', 'spa'],
            'rv': ['rv', 'recreational vehicle', 'motorhome', 'camper'],
            'automotive': ['automotive', 'car', 'vehicle', 'auto'],
            'home': ['home', 'house', 'residential'],
            'furniture': ['furniture', 'furnishing'],
            'technology': ['software', 'tech', 'digital', 'app'],
            'fashion': ['fashion', 'clothing', 'apparel'],
            'food': ['restaurant', 'food', 'catering', 'menu']
        }
        
        for industry, keywords in industry_keywords.items():
            if any(kw in html_lower or kw in url_lower for kw in keywords):
                categories.append(industry)
        
        return categories[:5]  # Return top 5 categories
    
    def _extract_navbar_links(self, html: str, base_url: str) -> List[Dict]:
        """Extract navigation bar links - the richest signal about site structure."""
        from urllib.parse import urljoin, urlparse
        
        navbar_links = []
        
        # Try to find nav element first
        nav_match = re.search(r'<nav[^>]*>(.*?)</nav>', html, re.IGNORECASE | re.DOTALL)
        if nav_match:
            nav_html = nav_match.group(1)
        else:
            # Fallback: look for header with navigation-like classes
            header_match = re.search(r'<header[^>]*>(.*?)</header>', html, re.IGNORECASE | re.DOTALL)
            if header_match:
                nav_html = header_match.group(1)
            else:
                # Last resort: look for common nav class patterns in divs
                nav_class_patterns = [
                    r'<div[^>]*class=["\'][^"\']*(nav|menu|header-nav)[^"\']["\'][^>]*>(.*?)</div>',
                    r'<ul[^>]*class=["\'][^"\']*(nav|menu|navigation)[^"\']["\'][^>]*>(.*?)</ul>'
                ]
                for pattern in nav_class_patterns:
                    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                    if match:
                        nav_html = match.group(2)
                        break
                else:
                    nav_html = html[:5000]  # Use first 5000 chars as fallback
        
        # Extract links from nav section
        link_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>'
        matches = re.findall(link_pattern, nav_html, re.IGNORECASE)
        
        for href, text in matches:
            text = text.strip()
            if not text or len(text) < 2:  # Skip empty or very short text
                continue
            
            # Skip common non-navigation links
            skip_patterns = ['javascript:', 'mailto:', 'tel:', '#']
            if any(pattern in href.lower() for pattern in skip_patterns):
                continue
            
            # Clean text
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Make URL absolute
            try:
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                # Only include links from same domain or relative links
                if parsed.netloc == '' or parsed.netloc in base_url:
                    navbar_links.append({
                        'text': text,
                        'href': href,
                        'full_url': full_url
                    })
            except:
                pass
        
        # Remove duplicates based on text (keep first occurrence)
        seen_texts = set()
        unique_links = []
        for link in navbar_links:
            text_lower = link['text'].lower()
            if text_lower not in seen_texts and len(text_lower) > 1:
                seen_texts.add(text_lower)
                unique_links.append(link)
        
        return unique_links[:15]  # Return top 15 navbar links


class GeminiFlowRecommender:
    """Gemini-powered strategic decision maker."""
    
    def __init__(self, gemini_api_key: Optional[str] = None):
        """
        Initialize Gemini flow recommender.
        
        Args:
            gemini_api_key: Gemini API key (defaults to env var)
        """
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        
        if not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY required for flow recommendation")
        
        genai.configure(api_key=self.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
    
    def recommend_flow(
        self,
        user_intent: str,
        site_signals: SiteSignals,
        project_context: Optional[str] = None
    ) -> FlowRecommendation:
        """
        Recommend optimal scraping flow.
        
        Args:
            user_intent: What user wants to extract
            site_signals: Site signal snapshot from preflight probe
            project_context: Optional project architecture description
            
        Returns:
            Flow recommendation (execution contract)
        """
        print(f"\n🤖 Gemini Flow Recommender")
        print(f"  Analyzing strategy for: {site_signals.url}")
        
        prompt = self._build_recommendation_prompt(user_intent, site_signals, project_context)
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,
                    response_mime_type="application/json"
                )
            )
            
            recommendation_data = json.loads(response.text)
            
            recommendation = FlowRecommendation(
                crawler=recommendation_data.get('crawler', 'web'),
                scraper=recommendation_data.get('scraper', 'static'),
                strictness=recommendation_data.get('strictness', 'balanced'),
                reasoning=recommendation_data.get('reasoning', {}),
                fallback_plan=recommendation_data.get('fallback_plan', []),
                exploration_config=recommendation_data.get('exploration_config', {
                    'max_pages': 10,
                    'max_depth': 3,
                    'crawl_delay': 0.5
                })
            )
            
            self._print_recommendation(recommendation)
            
            return recommendation
            
        except Exception as e:
            print(f"  ✗ Recommendation failed: {e}")
            # Return safe default
            return self._get_default_recommendation()
    
    def _build_recommendation_prompt(
        self,
        user_intent: str,
        site_signals: SiteSignals,
        project_context: Optional[str]
    ) -> str:
        """Build Gemini prompt for flow recommendation."""
        
        default_context = """
SYSTEM ARCHITECTURE:

Available Crawlers:
- 'web': Traditional web crawler with rule-based classification (fast, reliable, no API costs)
- 'ai': Legacy AI crawler using Jina + Gemini (semantic classification, requires Jina API)
- 'unified': Discover all URLs + Gemini filtering (recommended, no Jina dependency)

Available Scrapers:
- 'static': Fast HTML parsing with Jina AI (works on most sites, no browser)
- 'lam': Gemini + Playwright interactive extraction (for configurators, high accuracy)
- 'ai': AI-powered semantic extraction (for vague content, services, projects)
- 'auto': Intelligent routing - analyzes each URL and routes to optimal scraper

Strictness Levels:
- 'lenient': Captures more products, may include noise (good for clean e-commerce)
- 'balanced': Optimal balance (recommended for most sites)
- 'strict': High precision, may miss some products (use when high blog/noise ratio)

Selection Guidelines:
- Clean e-commerce with clear product pages → web + static + lenient
- Interactive configurators (build/customize flows) → unified + lam + balanced
- Portfolio/case studies/services → unified + ai + strict
- Mixed content types → web + auto + balanced
- Heavy JavaScript dependency → unified + lam + balanced
"""
        
        context = project_context or default_context
        
        prompt = f"""You are a scraping strategy architect. Design the optimal scraping flow.

{context}

USER INTENT:
{user_intent}

SITE SIGNALS:
{json.dumps(site_signals.to_dict(), indent=2)}

IMPORTANT: Pay special attention to 'navbar_links' - this is the RICHEST signal about site structure and offerings.
Navigation menu reveals the true nature of the site:
- E-commerce: "Shop", "Products", "Cart", "Checkout"
- Configurator: "Build", "Configure", "Customize", "Design Your Own"
- Portfolio/Agency: "Portfolio", "Our Work", "Case Studies", "Projects"
- Services: "Services", "What We Do", "Solutions", "Consultation"

TASK:
Recommend the optimal crawler, scraper, and strictness level.

OUTPUT FORMAT (JSON):
{{
  "crawler": "web|ai|unified",
  "scraper": "static|lam|ai|auto",
  "strictness": "lenient|balanced|strict",
  "reasoning": {{
    "site_type": "e-commerce|configurator|portfolio|mixed",
    "likely_products": "description of what will be extracted",
    "interaction_needed": true|false,
    "content_clarity": "clear|vague|mixed",
    "main_factors": ["factor1", "factor2"]
  }},
  "fallback_plan": [
    {{"crawler": "web", "scraper": "static", "reason": "fallback if primary fails"}},
    {{"crawler": "ai", "scraper": "ai", "reason": "last resort for complex sites"}}
  ],
  "exploration_config": {{
    "max_pages": 10,
    "max_depth": 3,
    "crawl_delay": 0.5,
    "stopping_rules": ["stop if blog density > 70%", "stop if no products after 20 pages"]
  }}
}}

DECISION CRITERIA:
1. **NAVBAR ANALYSIS (MOST IMPORTANT)**: Analyze navbar_links to understand site structure
   - "Build/Configure/Customize" in navbar → configurator → unified + lam + balanced
   - "Shop/Products/Cart" in navbar → e-commerce → web + static + lenient
   - "Portfolio/Work/Projects" in navbar → portfolio → unified + ai + strict
   - "Services" heavy navbar → services site → unified + ai + strict
2. If keywords contain "configure/build/custom" → likely configurator → lam scraper
3. If high JS dependency → unified crawler + lam/auto scraper
4. If project/portfolio heavy → unified + ai scraper + strict
5. If high blog links → strict strictness
6. If clear product patterns → web + static + balanced
7. If mixed signals → auto scraper

Respond ONLY with valid JSON matching the format above.
"""
        
        return prompt
    
    def _print_recommendation(self, rec: FlowRecommendation):
        """Print recommendation summary."""
        print(f"\n  ✓ Recommendation:")
        print(f"    Crawler: {rec.crawler}")
        print(f"    Scraper: {rec.scraper}")
        print(f"    Strictness: {rec.strictness}")
        print(f"    Site Type: {rec.reasoning.get('site_type', 'unknown')}")
        print(f"    Interaction Needed: {rec.reasoning.get('interaction_needed', False)}")
        print(f"    Fallback Plans: {len(rec.fallback_plan)}")
    
    def _get_default_recommendation(self) -> FlowRecommendation:
        """Return safe default recommendation."""
        return FlowRecommendation(
            crawler='web',
            scraper='static',
            strictness='balanced',
            reasoning={
                'site_type': 'unknown',
                'likely_products': 'standard products',
                'interaction_needed': False,
                'content_clarity': 'unknown',
                'main_factors': ['default fallback']
            },
            fallback_plan=[
                {'crawler': 'unified', 'scraper': 'lam', 'reason': 'if configurator detected'},
                {'crawler': 'ai', 'scraper': 'ai', 'reason': 'if semantic extraction needed'}
            ],
            exploration_config={
                'max_pages': 10,
                'max_depth': 3,
                'crawl_delay': 0.5,
                'stopping_rules': ['stop if no products after 10 pages']
            }
        )


class MasterOrchestrator:
    """Orchestrates the complete flow recommendation → execution pipeline."""
    
    def __init__(self, gemini_api_key: Optional[str] = None):
        """
        Initialize master orchestrator.
        
        Args:
            gemini_api_key: Gemini API key
        """
        self.probe = PreflightProbe()
        self.recommender = GeminiFlowRecommender(gemini_api_key)
    
    def plan_scraping_strategy(
        self,
        url: str,
        user_intent: str,
        project_context: Optional[str] = None
    ) -> FlowRecommendation:
        """
        Complete planning pipeline: probe → recommend.
        
        Args:
            url: Base URL to scrape
            user_intent: What to extract
            project_context: Optional project architecture description
            
        Returns:
            Flow recommendation ready for execution
        """
        print(f"\n{'='*80}")
        print("MASTER FLOW RECOMMENDATION")
        print(f"{'='*80}")
        print(f"URL: {url}")
        print(f"Intent: {user_intent}")
        
        # Step 1: Preflight probe (cheap, no Gemini)
        site_signals = self.probe.probe(url)
        
        # Step 2: Gemini recommendation (strategic)
        recommendation = self.recommender.recommend_flow(
            user_intent=user_intent,
            site_signals=site_signals,
            project_context=project_context
        )
        
        print(f"\n{'='*80}")
        print("STRATEGY READY FOR EXECUTION")
        print(f"{'='*80}\n")
        
        return recommendation
    
    def save_recommendation(self, recommendation: FlowRecommendation, filepath: str):
        """Save recommendation to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(recommendation.to_dict(), f, indent=2)
        print(f"✓ Recommendation saved: {filepath}")


# Convenience function
def recommend_scraping_strategy(
    url: str,
    user_intent: str,
    project_context: Optional[str] = None,
    gemini_api_key: Optional[str] = None
) -> FlowRecommendation:
    """
    Convenience function to get scraping recommendation.
    
    Args:
        url: Base URL to scrape
        user_intent: What to extract
        project_context: Optional project architecture
        gemini_api_key: Optional Gemini API key
        
    Returns:
        Flow recommendation
    
    Example:
        >>> rec = recommend_scraping_strategy(
        ...     url="https://example.com",
        ...     user_intent="Extract all RV models with pricing"
        ... )
        >>> print(f"Use {rec.crawler} crawler + {rec.scraper} scraper")
    """
    orchestrator = MasterOrchestrator(gemini_api_key)
    recommendation = orchestrator.plan_scraping_strategy(url, user_intent, project_context)
    return recommendation




if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python master.py <url> <intent>")
        print('Example: python master.py "https://example.com" "Extract RV models"')
        sys.exit(1)
    
    url = sys.argv[1]
    intent = sys.argv[2]
    
    recommendation = recommend_scraping_strategy(url, intent)
    
    print("\n📋 Execution Contract:")
    print(json.dumps(recommendation.to_dict(), indent=2))
