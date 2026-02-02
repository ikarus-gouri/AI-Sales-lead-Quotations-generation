"""
Page Navigator - Find configurator/customization pages automatically
Uses Gemini to intelligently navigate through website pages
"""

import os
import json
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional
import time
from urllib.parse import urljoin, urlparse


class PageNavigator:
    """Navigate through pages to find configurator/customization pages"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Gemini API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        self.visited_urls = set()
        self.configurator_keywords = [
            'configurator', 'configure', 'customization', 'customize',
            'build', 'builder', 'design', 'personalize', 'options'
        ]
    
    def get_page_links(self, page) -> List[Dict]:
        """Extract all links from the current page"""
        try:
            links = page.evaluate("""() => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    const text = a.innerText?.trim() || '';
                    const isVisible = a.offsetParent !== null;
                    
                    if (href && isVisible && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
                        links.push({
                            url: href,
                            text: text,
                            classes: a.className,
                            id: a.id
                        });
                    }
                });
                return links;
            }""")
            
            return links
        except Exception as e:
            print(f"Error extracting links: {e}")
            return []
    
    def get_page_content(self, page) -> str:
        """Get visible text content from page"""
        try:
            content = page.inner_text('body')
            return content[:10000]  # Limit to first 10k chars
        except Exception as e:
            print(f"Error getting page content: {e}")
            return ""
    
    def ask_gemini_about_links(self, current_url: str, page_content: str, links: List[Dict]) -> Dict:
        """Ask Gemini which link is most likely to lead to configurator"""
        
        # Filter links to reasonable candidates
        candidate_links = []
        for link in links[:50]:  # Limit to first 50 links
            text = link['text'].lower()
            url = link['url'].lower()
            
            # Check if link contains configurator keywords
            if any(keyword in text or keyword in url for keyword in self.configurator_keywords):
                candidate_links.append(link)
        
        # If no keyword matches, use all links
        if not candidate_links:
            candidate_links = links[:20]
        
        prompt = f"""
You are helping navigate a website to find a product configurator/customization page.

Current Page URL: {current_url}

Page Content (excerpt):
{page_content[:2000]}

Available Links ({len(candidate_links)} candidates):
{json.dumps(candidate_links[:15], indent=2)}

TASK: Analyze these links and identify which one is MOST LIKELY to lead to a product configurator or customization page.

Look for links with text like:
- "Configure", "Customize", "Build Your Own", "Design", "Personalize"
- "Options", "Choose", "Select", "Create"
- Any link that suggests product customization or configuration

Return JSON with this structure:
{{
  "is_configurator_page": boolean,  // Is the CURRENT page already a configurator?
  "confidence": number,  // 0-100, how confident are you this is/leads to configurator
  "recommended_link": {{
    "url": "string - full URL to visit next",
    "text": "string - link text",
    "reason": "string - why this link is promising"
  }},
  "reasoning": "string - explain your analysis"
}}

If the current page already looks like a configurator (has product options, customization controls), set is_configurator_page to true.
If no promising links found, set recommended_link to null.

Only return valid JSON.
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Clean JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            result = json.loads(response_text.strip())
            return result
            
        except Exception as e:
            print(f"Error asking Gemini: {e}")
            return {
                'is_configurator_page': False,
                'confidence': 0,
                'recommended_link': None,
                'reasoning': f'Error: {str(e)}'
            }
    
    def find_configurator(self, start_url: str, max_pages: int = 10) -> Dict:
        """
        Navigate through pages to find configurator
        
        Args:
            start_url: Starting URL (can be homepage or any page)
            max_pages: Maximum pages to visit
            
        Returns:
            Dict with results including configurator URL if found
        """
        print(f"\n{'='*80}")
        print("PAGE NAVIGATOR - FINDING CONFIGURATOR")
        print(f"{'='*80}\n")
        print(f"Starting URL: {start_url}")
        print(f"Max Pages: {max_pages}\n")
        
        navigation_path = []
        found_configurator = False
        configurator_url = None
        final_confidence = 0
        final_reasoning = ""
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            try:
                current_url = start_url
                
                for iteration in range(max_pages):
                    if current_url in self.visited_urls:
                        print(f"→ Already visited {current_url}, skipping...")
                        break
                    
                    print(f"\n{'─'*80}")
                    print(f"PAGE {iteration + 1}/{max_pages}")
                    print(f"{'─'*80}")
                    print(f"Visiting: {current_url}")
                    
                    # Load page
                    try:
                        page.goto(current_url, wait_until='domcontentloaded', timeout=30000)
                        page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"✗ Failed to load page: {e}")
                        break
                    
                    self.visited_urls.add(current_url)
                    navigation_path.append(current_url)
                    
                    # Get page content and links
                    print("→ Analyzing page...")
                    page_content = self.get_page_content(page)
                    links = self.get_page_links(page)
                    
                    print(f"  Found {len(links)} links on page")
                    
                    # Ask Gemini for analysis
                    print("→ Consulting Gemini...")
                    analysis = self.ask_gemini_about_links(current_url, page_content, links)
                    
                    # Check if current page is configurator
                    if analysis.get('is_configurator_page'):
                        print(f"\n✓ CONFIGURATOR FOUND!")
                        print(f"  Confidence: {analysis.get('confidence')}%")
                        print(f"  Reasoning: {analysis.get('reasoning')}")
                        found_configurator = True
                        configurator_url = current_url
                        final_confidence = analysis.get('confidence')
                        final_reasoning = analysis.get('reasoning')
                        break
                    
                    # Follow recommended link
                    recommended = analysis.get('recommended_link')
                    if recommended and recommended.get('url'):
                        next_url = recommended['url']
                        print(f"\n→ Following link: {recommended.get('text')}")
                        print(f"  Reason: {recommended.get('reason')}")
                        print(f"  URL: {next_url}")
                        current_url = next_url
                    else:
                        print("\n→ No more promising links found")
                        break
                
                print(f"\n{'='*80}")
                print("NAVIGATION COMPLETE")
                print(f"{'='*80}")
                print(f"Pages visited: {len(self.visited_urls)}")
                
                if found_configurator:
                    print(f"✓ Configurator URL: {configurator_url}")
                else:
                    print("✗ Configurator not found")
                
            except Exception as e:
                print(f"\n✗ Error during navigation: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
        
        return {
            'found': found_configurator,
            'configurator_url': configurator_url,
            'confidence': final_confidence,
            'reasoning': final_reasoning,
            'path': navigation_path,
            'pages_explored': len(self.visited_urls),
            'visited_pages': list(self.visited_urls)
        }


def main():
    """Test the page navigator"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python page_navigator.py <start_url> [max_pages]")
        print("\nExample:")
        print("  python page_navigator.py https://www.newmarcorp.com 10")
        sys.exit(1)
    
    start_url = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    
    try:
        navigator = PageNavigator()
        result = navigator.find_configurator(start_url, max_pages)
        
        print(f"\n{'='*80}")
        print("RESULT")
        print(f"{'='*80}")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
