"""
Gemini + Playwright Multi-Model Interactive Configurator Extractor
Discovers all models, completes full configuration for each, then moves to next model
Uses cached patterns to minimize Gemini API calls
"""

import os
import json
import sys
import google.generativeai as genai
from playwright.async_api import async_playwright
from typing import Dict, List, Optional, Tuple
import time
import asyncio
from dotenv import load_dotenv
import base64

# Load environment variables
load_dotenv()


class GeminiInteractiveExtractor:
    """Interactive extraction with intelligent multi-model exploration"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Gemini Flash with API key"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # MODEL DISCOVERY & TRACKING
        self.all_models = []              # All discovered models at start
        self.explored_models = set()      # Models that have been fully configured
        self.current_model = None         # Currently exploring model
        
        # NAVIGATION CACHE
        self.restart_button_cache = None   # How to get back to model selection
        self.continue_button_class = None  # Class for "Continue" buttons
        self.workflow_steps = []           # Sequence of customization steps
        
        # OPTIONS STORAGE
        self.all_options = []
        
        # Stats
        self.stats = {
            'total_iterations': 0,
            'gemini_consultations': 0,
            'cached_navigations': 0,
            'models_completed': 0
        }
        
    async def capture_page_state(self, page) -> Dict:
        """Capture current page state"""
        try:
            screenshot_bytes = await page.screenshot(type='png')
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            elements = await page.evaluate("""() => {
                const elements = [];
                const selectors = [
                    'button', '[role="button"]', 'a[href]', '.card',
                    '[class*="option"]', '[class*="choice"]', '[class*="model"]',
                    'input[type="radio"]', 'input[type="checkbox"]', 'select',
                    '[class*="next"]', '[class*="continue"]', '[class*="submit"]',
                    '[class*="start"]', '[class*="restart"]', '[class*="back"]'
                ];
                
                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach((el, idx) => {
                        const rect = el.getBoundingClientRect();
                        const isVisible = rect.width > 0 && rect.height > 0 && 
                                        window.getComputedStyle(el).visibility !== 'hidden' &&
                                        window.getComputedStyle(el).display !== 'none';
                        
                        if (isVisible) {
                            const isDisabled = el.disabled || 
                                             el.hasAttribute('disabled') || 
                                             el.getAttribute('aria-disabled') === 'true' ||
                                             el.classList.contains('disabled') ||
                                             el.style.pointerEvents === 'none';
                            
                            const isSelected = el.checked || el.selected ||
                                             el.classList.contains('selected') ||
                                             el.classList.contains('active');
                            
                            let imageUrl = '';
                            const img = el.querySelector('img');
                            if (img) {
                                imageUrl = img.src || img.getAttribute('data-src') || '';
                            } else if (el.tagName === 'IMG') {
                                imageUrl = el.src || el.getAttribute('data-src') || '';
                            }
                            
                            elements.push({
                                selector: selector,
                                text: el.innerText?.substring(0, 100) || el.value || '',
                                tag: el.tagName,
                                id: el.id,
                                classes: el.className,
                                disabled: isDisabled,
                                selected: isSelected,
                                image: imageUrl,
                                position: {
                                    x: Math.round(rect.left + rect.width / 2),
                                    y: Math.round(rect.top + rect.height / 2)
                                }
                            });
                        }
                    });
                });
                
                return elements;
            }""")
            
            visible_text = await page.inner_text('body')
            
            return {
                'screenshot': screenshot_b64,
                'elements': elements[:50],
                'visible_text': visible_text[:5000],
                'url': page.url
            }
            
        except Exception as e:
            print(f"Error capturing page state: {e}")
            return None
    
    def ask_gemini_for_initial_analysis(self, page_state: Dict) -> Dict:
        """First Gemini call: Discover all models and understand the flow"""
        
        prompt = f"""
You are analyzing a product configurator to discover ALL available base models/products.

Current Page:
{page_state['visible_text'][:3000]}

Available Elements:
{json.dumps(page_state['elements'][:30], indent=2)}

TASK 1: DISCOVER ALL MODELS
Identify ALL base model/product options visible on this initial page. These are typically:
- Model names (e.g., "2026 KING AIRE", "2026 ESSEX")
- Product collections
- Base product variants
- Main categories user must choose from first

TASK 2: UNDERSTAND WORKFLOW
Analyze the page structure to understand:
- What happens after selecting a model? (e.g., floor plan selection)
- Are there "Continue" buttons? What's their class name?
- Is there a "Start Over" or restart button? What's its text/class?
- What customization steps follow? (try to identify from tabs, headers, or button text)

Return JSON:
{{
  "all_models": [
    {{
      "name": "string - exact model name",
      "image": "string - image URL from elements if available",
      "selector_hints": {{
        "text_contains": "string",
        "class_contains": "string"
      }}
    }}
  ],
  "workflow_info": {{
    "has_continue_button": boolean,
    "continue_button_class": "string - CSS class for Continue buttons",
    "has_restart_button": boolean,
    "restart_button_text": "string - text on restart button",
    "restart_button_class": "string - class for restart button",
    "customization_steps": ["string - list of step names like Floor Plan, Exterior, Interior"]
  }},
  "first_action": {{
    "action_type": "select",
    "element_text": "string - first model to select",
    "reason": "string"
  }}
}}

IMPORTANT:
- Extract ALL models visible, not just one
- Look for consistent button classes (they won't change between models)
- Identify the workflow pattern to optimize future iterations

Only return valid JSON.
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
        except Exception as e:
            print(f"Error in initial analysis: {e}")
            return {
                'all_models': [],
                'workflow_info': {},
                'first_action': None
            }
    
    def ask_gemini_for_guidance(self, page_state: Dict, context: Dict) -> Dict:
        """Ask Gemini for next action during configuration"""
        
        explored_info = ""
        if self.explored_models:
            explored_info = f"""
✅ COMPLETED MODELS: {', '.join(sorted(self.explored_models))}
"""
        
        pending_info = ""
        pending_models = set(m['name'] for m in self.all_models) - self.explored_models
        if pending_models:
            pending_info = f"""
⏳ PENDING MODELS: {', '.join(sorted(pending_models))}
"""
        
        current_info = f"🔧 CURRENT MODEL: {self.current_model}" if self.current_model else ""
        
        prompt = f"""
You are guiding extraction of customization options from a configurator.

{explored_info}{pending_info}{current_info}

Current Page:
{page_state['visible_text'][:3000]}

Discovered Options So Far: {len(self.all_options)}

Available Elements:
{json.dumps(page_state['elements'][:30], indent=2)}

Context:
- Total models to explore: {len(self.all_models)}
- Models completed: {len(self.explored_models)}
- Workflow steps we know: {', '.join(self.workflow_steps) if self.workflow_steps else 'Learning...'}

TASK:
1. Extract NEW visible customization options
2. Recommend next action to continue configuration
3. Detect if configuration is COMPLETE for current model

Return JSON:
{{
  "new_options": [
    {{
      "category": "string",
      "component": "string",
      "price": "string",
      "reference": "string",
      "image": "string"
    }}
  ],
  "current_step": "string - current customization step name (e.g., Floor Plan, Exterior)",
  "configuration_complete": boolean - true if reached end of configuration for this model,
  "next_action": {{
    "action_type": "select" | "click_next" | "click_tab" | "expand_accordion",
    "element_text": "string",
    "reason": "string",
    "selector_hints": {{
      "text_contains": "string",
      "class_contains": "string"
    }}
  }}
}}

IMPORTANT:
- Extract ALL visible options before recommending actions
- If you see a "Finish", "Complete", "Summary", or "Review" page, set configuration_complete = true
- Select first available option in each category to move forward
- Look for Continue/Next buttons with consistent class names

Only return valid JSON.
"""
        
        try:
            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
        except Exception as e:
            print(f"Error getting guidance: {e}")
            return {
                'new_options': [],
                'configuration_complete': False,
                'next_action': None
            }
    
    async def click_element(self, page, selector_hints: Dict) -> bool:
        """Click an element using selector hints"""
        try:
            text = selector_hints.get('text_contains', '')
            class_name = selector_hints.get('class_contains', '')
            
            # Try text-based selector
            if text:
                try:
                    element = page.get_by_text(text, exact=False).first
                    if await element.is_visible():
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || el.hasAttribute('disabled') || 
                                   el.getAttribute('aria-disabled') === 'true' ||
                                   el.classList.contains('disabled');
                        }""")
                        
                        if not is_disabled:
                            await element.scroll_into_view_if_needed()
                            try:
                                await element.click(timeout=3000)
                            except:
                                await element.evaluate('el => el.click()')
                            print(f"  ✓ Clicked: '{text}'")
                            return True
                except:
                    pass
            
            # Try class-based selector
            if class_name:
                try:
                    element = page.locator(f".{class_name}").first
                    if await element.is_visible():
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || el.hasAttribute('disabled');
                        }""")
                        
                        if not is_disabled:
                            await element.scroll_into_view_if_needed()
                            await element.click(timeout=3000)
                            print(f"  ✓ Clicked (class): {class_name}")
                            return True
                except:
                    pass
            
            return False
        except Exception as e:
            print(f"  ✗ Click failed: {e}")
            return False
    
    async def try_cached_continue(self, page) -> bool:
        """Try to click Continue button using cached class"""
        if not self.continue_button_class:
            return False
        
        try:
            element = page.locator(f".{self.continue_button_class}").first
            if await element.is_visible():
                is_disabled = await element.evaluate("""el => {
                    return el.disabled || el.hasAttribute('disabled') ||
                           el.classList.contains('disabled');
                }""")
                
                if not is_disabled:
                    button_text = await element.inner_text()
                    await element.scroll_into_view_if_needed()
                    await element.click(timeout=3000)
                    print(f"  ✓ Cached Continue clicked: '{button_text}'")
                    self.stats['cached_navigations'] += 1
                    return True
        except:
            pass
        
        return False
    
    async def restart_to_model_selection(self, page) -> bool:
        """Navigate back to model selection page"""
        print("\n🔄 Attempting to return to model selection...")
        
        # Try cached restart button
        if self.restart_button_cache:
            print(f"  → Using cached restart button")
            if await self.click_element(page, self.restart_button_cache):
                await page.wait_for_timeout(3000)
                self.stats['cached_navigations'] += 1
                return True
        
        # Try common restart patterns
        restart_patterns = [
            'start over', 'restart', 'begin again', 'start again',
            'clear', 'reset', 'new configuration', 'back to models'
        ]
        
        for pattern in restart_patterns:
            try:
                element = page.get_by_text(pattern, exact=False).first
                if await element.is_visible():
                    await element.scroll_into_view_if_needed()
                    await element.click(timeout=3000)
                    print(f"  ✓ Found restart button: '{pattern}'")
                    await page.wait_for_timeout(3000)
                    
                    # Cache it
                    self.restart_button_cache = {'text_contains': pattern}
                    return True
            except:
                continue
        
        print("  ⚠️ Could not find restart button, may need Gemini help")
        return False
    
    async def configure_single_model(self, page, model_name: str, max_steps: int = 20) -> List[Dict]:
        """Complete full configuration for a single model"""
        print(f"\n{'='*80}")
        print(f"CONFIGURING MODEL: {model_name}")
        print(f"{'='*80}")
        
        model_options = []
        
        for step in range(max_steps):
            self.stats['total_iterations'] += 1
            
            print(f"\n  Step {step + 1}/{max_steps}")
            
            # Capture page state
            page_state = await self.capture_page_state(page)
            if not page_state:
                break
            
            # Try cached Continue first (after step 2)
            if step > 1 and self.continue_button_class:
                if await self.try_cached_continue(page):
                    await page.wait_for_timeout(2000)
                    continue
            
            # Ask Gemini for guidance
            print("  → Consulting Gemini...")
            self.stats['gemini_consultations'] += 1
            
            guidance = self.ask_gemini_for_guidance(page_state, {
                'current_model': model_name,
                'step_number': step
            })
            
            # Extract options
            new_options = guidance.get('new_options', [])
            if new_options:
                print(f"  ✓ Found {len(new_options)} options")
                for opt in new_options:
                    opt['model'] = model_name  # Tag with model name
                    print(f"    • {opt.get('category')} → {opt.get('component')}")
                model_options.extend(new_options)
            
            # Track workflow step
            current_step = guidance.get('current_step')
            if current_step and current_step not in self.workflow_steps:
                self.workflow_steps.append(current_step)
                print(f"  📌 Workflow step learned: {current_step}")
            
            # Check if configuration complete
            if guidance.get('configuration_complete'):
                print(f"\n  ✅ Configuration complete for {model_name}")
                break
            
            # Execute next action
            next_action = guidance.get('next_action')
            if next_action:
                selector_hints = next_action.get('selector_hints', {})
                
                # Cache Continue button class if found
                if next_action.get('action_type') == 'click_next':
                    class_hint = selector_hints.get('class_contains', '')
                    if class_hint and not self.continue_button_class:
                        self.continue_button_class = class_hint
                        print(f"  📌 Continue button class cached: {class_hint}")
                
                # Click element
                clicked = await self.click_element(page, selector_hints)
                if clicked:
                    await page.wait_for_timeout(2000)
                else:
                    print(f"  ⚠️ Failed to execute action, may be stuck")
                    break
            else:
                print("  ⚠️ No action recommended, configuration may be complete")
                break
        
        return model_options
    
    async def interactive_extraction(self, url: str, max_iterations: int = 100) -> List[Dict]:
        """
        Main extraction loop: discovers models, configures each fully
        """
        print(f"\n{'='*80}")
        print(f"MULTI-MODEL CONFIGURATOR EXTRACTION")
        print(f"{'='*80}\n")
        print(f"Target URL: {url}\n")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            try:
                # Step 1: Load page and discover models
                print("→ Loading initial page...")
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(3000)
                
                print("\n📋 PHASE 1: DISCOVERING MODELS")
                print("="*80)
                
                page_state = await self.capture_page_state(page)
                
                print("→ Analyzing page structure...")
                self.stats['gemini_consultations'] += 1
                
                analysis = self.ask_gemini_for_initial_analysis(page_state)
                
                # Store discovered models
                self.all_models = analysis.get('all_models', [])
                if not self.all_models:
                    print("⚠️ No models discovered, treating as single-product configurator")
                    self.all_models = [{'name': 'Default Product', 'selector_hints': {}}]
                
                print(f"\n✓ Discovered {len(self.all_models)} model(s):")
                for i, model in enumerate(self.all_models, 1):
                    print(f"  {i}. {model['name']}")
                
                # Cache workflow info
                workflow_info = analysis.get('workflow_info', {})
                if workflow_info.get('continue_button_class'):
                    self.continue_button_class = workflow_info['continue_button_class']
                    print(f"\n📌 Cached Continue button class: {self.continue_button_class}")
                
                if workflow_info.get('restart_button_text'):
                    self.restart_button_cache = {
                        'text_contains': workflow_info['restart_button_text'],
                        'class_contains': workflow_info.get('restart_button_class', '')
                    }
                    print(f"📌 Cached Restart button: {workflow_info['restart_button_text']}")
                
                # Step 2: Configure each model
                print(f"\n\n📋 PHASE 2: CONFIGURING MODELS")
                print("="*80)
                
                for model_index, model in enumerate(self.all_models):
                    model_name = model['name']
                    
                    if model_name in self.explored_models:
                        print(f"\n⏭️ Skipping {model_name} (already explored)")
                        continue
                    
                    self.current_model = model_name
                    
                    # Select model (skip for first model if already selected)
                    if model_index > 0 or not analysis.get('first_action'):
                        print(f"\n→ Selecting model: {model_name}")
                        if await self.click_element(page, model.get('selector_hints', {})):
                            await page.wait_for_timeout(2000)
                    
                    # Configure this model fully
                    model_options = await self.configure_single_model(page, model_name)
                    
                    self.all_options.extend(model_options)
                    self.explored_models.add(model_name)
                    self.stats['models_completed'] += 1
                    
                    print(f"\n✅ Completed {model_name}: {len(model_options)} options")
                    
                    # If more models remain, restart
                    if model_index < len(self.all_models) - 1:
                        if await self.restart_to_model_selection(page):
                            await page.wait_for_timeout(2000)
                        else:
                            print("⚠️ Could not restart, may need manual intervention")
                            break
                
                # Final summary
                print(f"\n{'='*80}")
                print(f"EXTRACTION COMPLETE")
                print(f"{'='*80}")
                print(f"Total models configured: {len(self.explored_models)}/{len(self.all_models)}")
                print(f"Total options extracted: {len(self.all_options)}")
                
                print(f"\n{'='*80}")
                print("OPTIMIZATION STATISTICS")
                print(f"{'='*80}")
                print(f"Total iterations:        {self.stats['total_iterations']}")
                print(f"Gemini consultations:    {self.stats['gemini_consultations']}")
                print(f"Cached navigations:      {self.stats['cached_navigations']}")
                
                if self.stats['total_iterations'] > 0:
                    reduction = (self.stats['total_iterations'] - self.stats['gemini_consultations']) / self.stats['total_iterations']
                    print(f"API call reduction:      {reduction:.1%}")
                    
                    cost_per_call = 0.15
                    total_cost = self.stats['gemini_consultations'] * cost_per_call
                    without_cache = self.stats['total_iterations'] * cost_per_call
                    savings = without_cache - total_cost
                    print(f"Estimated cost:          ${total_cost:.2f}")
                    print(f"Estimated savings:       ${savings:.2f}")
                
                print(f"{'='*80}\n")
                
            except Exception as e:
                print(f"\n✗ Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                await browser.close()
        
        return self.all_options
    
    def save_results(self, options: List[Dict], url: str) -> Tuple[str, str]:
        """Save results to JSON and CSV"""
        import csv
        
        timestamp = int(time.time())
        
        # JSON
        json_filename = f"multi_model_extraction_{timestamp}.json"
        result = {
            'url': url,
            'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'method': 'gemini-multi-model',
            'total_models': len(self.all_models),
            'models_explored': len(self.explored_models),
            'total_options': len(options),
            'models': [m['name'] for m in self.all_models],
            'options': options
        }
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # CSV
        csv_filename = f"multi_model_extraction_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['Model', 'Category', 'Component', 'Price', 'Reference', 'Image']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for opt in options:
                writer.writerow({
                    'Model': opt.get('model', ''),
                    'Category': opt.get('category', ''),
                    'Component': opt.get('component', ''),
                    'Price': opt.get('price', 'N/A'),
                    'Reference': opt.get('reference', ''),
                    'Image': opt.get('image', '')
                })
        
        return json_filename, csv_filename


async def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python gemini_multi_model_extractor.py <url> [max_iterations]")
        print("\nExample:")
        print("  python gemini_multi_model_extractor.py https://example.com/configurator 100")
        sys.exit(1)
    
    url = sys.argv[1]
    max_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    
    try:
        extractor = GeminiMultiModelExtractor()
        options = await extractor.interactive_extraction(url, max_iterations)
        
        if options:
            json_file, csv_file = extractor.save_results(options, url)
            print(f"\n✓ Results saved:")
            print(f"  JSON: {json_file}")
            print(f"  CSV: {csv_file}")
        else:
            print("\n⚠ No options extracted")
        
    except ValueError as e:
        print(f"\n❌ Error: {e}")
        print("\nSet GEMINI_API_KEY in .env file")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())