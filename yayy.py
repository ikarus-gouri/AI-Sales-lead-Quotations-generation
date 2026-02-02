"""
Gemini + Playwright Interactive Configurator Extractor
Uses Gemini to guide Playwright on what to click to discover all options
"""

import os
import json
import sys
import google.generativeai as genai
from playwright.sync_api import sync_playwright
from typing import Dict, List, Optional, Tuple
import time
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()


class GeminiInteractiveExtractor:
    """Interactive extraction using Gemini to guide Playwright"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini Flash with API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Store discovered options
        self.discovered_options = []
        self.visited_states = set()
        self.max_depth = 10
        
    def capture_page_state(self, page) -> Dict:
        """Capture current page state with screenshot and elements"""
        try:
            # Take screenshot
            screenshot_bytes = page.screenshot(type='png')
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # Extract interactive elements with their positions
            elements = page.evaluate("""() => {
                const elements = [];
                
                // Find clickable elements
                const selectors = [
                    'button:not([disabled])',
                    '[role="button"]:not([disabled])',
                    'a[href]:not([disabled])',
                    '.card:not([disabled])',
                    '[class*="option"]:not([disabled])',
                    '[class*="choice"]:not([disabled])',
                    '[class*="model"]:not([disabled])',
                    '[class*="selector"]:not([disabled])',
                    'input[type="radio"]',
                    'input[type="checkbox"]',
                    'select'
                ];
                
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        const isVisible = rect.width > 0 && rect.height > 0 && 
                                        window.getComputedStyle(el).visibility !== 'hidden' &&
                                        window.getComputedStyle(el).display !== 'none';
                        
                        if (isVisible) {
                            elements.push({
                                selector: selector,
                                text: el.innerText?.substring(0, 100) || el.value || '',
                                tag: el.tagName,
                                id: el.id,
                                classes: el.className,
                                position: {
                                    x: Math.round(rect.left + rect.width / 2),
                                    y: Math.round(rect.top + rect.height / 2)
                                },
                                attributes: {
                                    href: el.href,
                                    type: el.type,
                                    name: el.name,
                                    value: el.value
                                }
                            });
                        }
                    });
                });
                
                return elements;
            }""")
            
            # Get current visible text
            visible_text = page.inner_text('body')
            
            return {
                'screenshot': screenshot_b64,
                'elements': elements[:50],  # Limit to first 50
                'visible_text': visible_text[:5000],
                'url': page.url
            }
            
        except Exception as e:
            print(f"Error capturing page state: {e}")
            return None
    
    def ask_gemini_what_to_click(self, page_state: Dict, discovered_so_far: List) -> Dict:
        """Ask Gemini what to click next to discover more options"""
        
        prompt = f"""
You are guiding an automated browser to extract ALL customization options from a product configurator.

Current Page URL: {page_state['url']}

Discovered Options So Far ({len(discovered_so_far)} items):
{json.dumps(discovered_so_far[-10:], indent=2) if discovered_so_far else 'None yet'}

Current Page Visible Text:
{page_state['visible_text'][:3000]}

Available Interactive Elements (with positions):
{json.dumps(page_state['elements'][:30], indent=2)}

TASK: Analyze the page and tell me:
1. What should I click next to reveal MORE customization options?
2. What NEW options are visible on the current page that we haven't captured yet?
3. Are there any dropdowns, tabs, buttons, or cards that would reveal more options when clicked?

Return JSON with this structure:
{{
  "new_options_visible": [
    {{
      "category": "string - category name",
      "component": "string - option name",
      "price": "string - price if visible, else N/A",
      "reference": "string - image URL or link if visible"
    }}
  ],
  "click_recommendation": {{
    "should_click": boolean,
    "element_description": "string - describe what to click (e.g., 'the blue Model X card')",
    "element_text": "string - exact text of element to click",
    "reason": "string - why clicking this will reveal more options",
    "selector_hints": {{
      "text_contains": "string",
      "class_contains": "string",
      "position_x": number,
      "position_y": number
    }}
  }},
  "exploration_complete": boolean
}}

IMPORTANT:
- Look for tabs, accordion sections, model cards, option buttons that need to be clicked
- Suggest clicking elements that look like they expand/reveal more content
- Set exploration_complete to true only if you're confident all options are extracted
- Extract ALL visible options in new_options_visible before recommending a click

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
                'new_options_visible': [],
                'click_recommendation': {'should_click': False},
                'exploration_complete': True
            }
    
    def find_and_click_element(self, page, recommendation: Dict) -> bool:
        """Find and click the element recommended by Gemini"""
        try:
            hints = recommendation.get('selector_hints', {})
            text_contains = hints.get('text_contains', '')
            class_contains = hints.get('class_contains', '')
            position = (hints.get('position_x'), hints.get('position_y'))
            
            print(f"  → Looking for element with text: '{text_contains}'")
            
            # Strategy 1: Try exact text match
            if text_contains:
                try:
                    element = page.get_by_text(text_contains, exact=False).first
                    if element.is_visible():
                        element.scroll_into_view_if_needed()
                        element.click(timeout=3000)
                        print(f"  ✓ Clicked element by text: '{text_contains}'")
                        return True
                except:
                    pass
            
            # Strategy 2: Try by role and text
            if text_contains:
                try:
                    element = page.get_by_role('button', name=text_contains).first
                    if element.is_visible():
                        element.scroll_into_view_if_needed()
                        element.click(timeout=3000)
                        print(f"  ✓ Clicked button: '{text_contains}'")
                        return True
                except:
                    pass
            
            # Strategy 3: Try finding by class
            if class_contains:
                try:
                    element = page.locator(f'[class*="{class_contains}"]').first
                    if element.is_visible():
                        element.scroll_into_view_if_needed()
                        element.click(timeout=3000)
                        print(f"  ✓ Clicked element by class: '{class_contains}'")
                        return True
                except:
                    pass
            
            # Strategy 4: Try clicking at position
            if position[0] and position[1]:
                try:
                    page.mouse.click(position[0], position[1])
                    print(f"  ✓ Clicked at position: {position}")
                    return True
                except:
                    pass
            
            print(f"  ✗ Could not find element to click")
            return False
            
        except Exception as e:
            print(f"  ✗ Error clicking: {e}")
            return False
    
    def interactive_extraction(self, url: str, max_iterations: int = 15) -> List[Dict]:
        """
        Interactively explore configurator using Gemini's guidance
        
        Args:
            url: The configurator URL
            max_iterations: Maximum number of click iterations
            
        Returns:
            List of all discovered options
        """
        print(f"\n{'='*80}")
        print(f"GEMINI + PLAYWRIGHT INTERACTIVE EXTRACTION")
        print(f"{'='*80}\n")
        print(f"Target URL: {url}")
        print(f"Max Iterations: {max_iterations}\n")
        
        all_options = []
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            
            try:
                # Initial page load
                print("→ Loading initial page...")
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_timeout(3000)
                
                # Iterative exploration
                for iteration in range(max_iterations):
                    print(f"\n{'─'*80}")
                    print(f"ITERATION {iteration + 1}/{max_iterations}")
                    print(f"{'─'*80}")
                    
                    # Capture current state
                    print("→ Capturing page state...")
                    page_state = self.capture_page_state(page)
                    
                    if not page_state:
                        print("✗ Failed to capture page state")
                        break
                    
                    # Ask Gemini what to do
                    print("→ Consulting Gemini for guidance...")
                    guidance = self.ask_gemini_what_to_click(page_state, all_options)
                    
                    # Extract newly visible options
                    new_options = guidance.get('new_options_visible', [])
                    if new_options:
                        print(f"✓ Found {len(new_options)} new options:")
                        for opt in new_options:
                            print(f"  • {opt.get('category')} → {opt.get('component')}")
                        all_options.extend(new_options)
                    
                    # Check if exploration is complete
                    if guidance.get('exploration_complete'):
                        print("\n✓ Gemini says exploration is complete!")
                        break
                    
                    # Follow click recommendation
                    click_rec = guidance.get('click_recommendation', {})
                    if click_rec.get('should_click'):
                        print(f"\n→ Gemini recommends: {click_rec.get('reason')}")
                        print(f"  Target: {click_rec.get('element_description')}")
                        
                        clicked = self.find_and_click_element(page, click_rec)
                        
                        if clicked:
                            page.wait_for_timeout(2000)  # Wait for content to load
                        else:
                            print("  → Trying next iteration...")
                    else:
                        print("\n→ Gemini has no more click recommendations")
                        break
                
                print(f"\n{'='*80}")
                print(f"EXTRACTION COMPLETE")
                print(f"{'='*80}")
                print(f"Total options discovered: {len(all_options)}")
                
            except Exception as e:
                print(f"\n✗ Error during extraction: {e}")
                import traceback
                traceback.print_exc()
            finally:
                browser.close()
        
        return all_options
    
    def save_results(self, options: List[Dict], url: str) -> Tuple[str, str]:
        """Save results to JSON and CSV"""
        import csv
        
        timestamp = int(time.time())
        
        # Save JSON
        json_filename = f"interactive_extraction_{timestamp}.json"
        result = {
            'url': url,
            'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'method': 'gemini-interactive',
            'total_options': len(options),
            'options': options
        }
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Save CSV
        csv_filename = f"interactive_extraction_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Categories', 'Component', 'Price', 'References'])
            writer.writeheader()
            
            for opt in options:
                writer.writerow({
                    'Categories': opt.get('category', ''),
                    'Component': opt.get('component', ''),
                    'Price': opt.get('price', 'N/A'),
                    'References': opt.get('reference', '')
                })
        
        return json_filename, csv_filename
    
    def print_summary(self, options: List[Dict]):
        """Print summary of extracted options"""
        print(f"\n{'='*80}")
        print("SALES QUOTATION - EXTRACTED OPTIONS")
        print(f"{'='*80}\n")
        
        print(f"{'Categories':<30} {'Component':<30} {'Price':<10} {'References':<30}")
        print(f"{'='*80}")
        
        current_category = None
        for opt in options:
            category = opt.get('category', '')
            component = opt.get('component', '')
            price = opt.get('price', 'N/A')
            reference = opt.get('reference', '')[:30]
            
            if category != current_category:
                print(f"{category:<30} {component:<30} {price:<10} {reference}")
                current_category = category
            else:
                print(f"{'':<30} {component:<30} {price:<10} {reference}")
        
        print(f"{'='*80}")
        print(f"Total: {len(options)} options")
        print(f"{'='*80}\n")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python gemini_interactive_extractor.py <url> [max_iterations]")
        print("\nExample:")
        print("  python gemini_interactive_extractor.py https://www.newmarcorp.com/configure-customization/build-your-coach 20")
        sys.exit(1)
    
    url = sys.argv[1]
    max_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    
    try:
        extractor = GeminiInteractiveExtractor()
        options = extractor.interactive_extraction(url, max_iterations)
        
        if options:
            extractor.print_summary(options)
            json_file, csv_file = extractor.save_results(options, url)
            print(f"✓ Results saved to:")
            print(f"  - {json_file}")
            print(f"  - {csv_file}")
        else:
            print("\n⚠ No options were extracted")
        
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\nSet GEMINI_API_KEY in your .env file")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
