"""
Gemini + Playwright Interactive Configurator Extractor
Uses Gemini to guide Playwright on what to click to discover all options
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
    """Interactive extraction using Gemini to guide Playwright"""
    
    def __init__(self, api_key: Optional[str] = None, headless: bool = True):
        """Initialize Gemini Flash with API key
        
        Args:
            api_key: Gemini API key (uses env var if not provided)
            headless: Run browser in headless mode (default True for server environments)
        """
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        # Configure Gemini
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Store headless preference
        self.headless = headless
        
        # Store discovered options
        self.discovered_options = []
        self.visited_states = set()
        self.max_depth = 10
        
        # Pattern detection for optimization
        self.detected_pattern = None
        self.pattern_confidence = 0
        self.actions_history = []
        
    async def capture_page_state(self, page) -> Dict:
        """Capture current page state with screenshot and elements"""
        try:
            # Take screenshot
            screenshot_bytes = await page.screenshot(type='png')
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # Extract interactive elements with their positions
            elements = await page.evaluate("""() => {
                const elements = [];
                
                // Find ALL interactive elements (including disabled ones)
                const selectors = [
                    'button',
                    '[role="button"]',
                    'a[href]',
                    '.card',
                    '[class*="option"]',
                    '[class*="choice"]',
                    '[class*="model"]',
                    '[class*="selector"]',
                    'input[type="radio"]',
                    'input[type="checkbox"]',
                    'select',
                    '[class*="next"]',
                    '[class*="continue"]',
                    '[class*="submit"]'
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
                            
                            const isSelected = el.checked || 
                                             el.selected ||
                                             el.classList.contains('selected') ||
                                             el.classList.contains('active') ||
                                             el.getAttribute('aria-checked') === 'true' ||
                                             el.getAttribute('aria-selected') === 'true';
                            
                            // Try to find an image within this element
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
            visible_text = await page.inner_text('body')
            
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

Available Interactive Elements (with positions and states):
{json.dumps(page_state['elements'][:30], indent=2)}

TASK: Analyze the page and tell me:
1. What NEW options are visible on the current page that we haven't captured yet?
2. For EACH option found, look through the 'Available Interactive Elements' list above and find matching elements
3. Extract the 'image' field value from matching elements - this contains the image URL for that option
4. Are there any ENABLED (not disabled) option buttons/cards that need to be selected?
5. What should I click next to reveal MORE customization options?

IMPORTANT RULES FOR IMAGE EXTRACTION:
- Look at the 'Available Interactive Elements' JSON data above
- Each element has an 'image' field - extract this URL for each option you find
- Match option text to element 'text' field to find the corresponding image URL
- If an element has a non-empty 'image' field, include it in the new_options_visible

IMPORTANT RULES FOR CLICKING:
- NEVER click disabled buttons (disabled: true)
- "Next", "Continue", "Submit" buttons are often disabled until required selections are made
- FIRST select/click option cards or radio buttons on the current page
- THEN once selections are made, disabled buttons may become enabled
- Check the 'disabled' field - if true, DO NOT recommend clicking it
- Only recommend clicking ENABLED elements (disabled: false)
- Extract image URLs from the 'image' field in element data and include them in new_options_visible

CONDITIONAL/DEPENDENT OPTIONS:
- Some configurators reveal new options ONLY after selecting a previous option
- Example: Selecting a model might reveal model-specific customization options
- These pages may NOT have explicit "Next" buttons - content just updates dynamically
- If you see unselected options but no new categories, SELECT an option to see what it reveals
- After selecting, new options for that selection may appear on the same page
- Pattern: select option → wait → new options appear → extract them → select next option
- Don't assume you need a "Next" button - selection alone might reveal content

Return JSON with this structure:
{{
  "new_options_visible": [
    {{
      "category": "string - category name (e.g., Model, Floor Plan, Exterior Paint)",
      "component": "string - option name (e.g., 2026 KING AIRE, 4521, ANTRIM)",
      "price": "string - price if visible, else N/A",
      "reference": "string - any additional reference info",
      "image": "string - REQUIRED: Extract from 'image' field in matching element, empty string if not found"
    }}
  ],
  "actions_sequence": [
    {{
      "action_type": "select" | "click_next" | "click_tab",
      "element_description": "string",
      "element_text": "string",
      "reason": "string",
      "selector_hints": {{
        "text_contains": "string",
        "class_contains": "string",
        "position_x": number,
        "position_y": number
      }}
    }}
  ],
  "workflow_pattern": {{
    "detected": boolean,
    "pattern_type": "select_then_next" | "tabs" | "accordion" | "conditional_reveal" | "none",
    "description": "string - describe the pattern"
  }},
  "at_final_step": boolean,
  "final_step_info": {{
    "is_finish_button": boolean,
    "finish_button_text": "string - text like FINISH, COMPLETE, SUMMARY, REVIEW, SUBMIT ORDER",
    "is_last_tab": boolean,
    "should_return_to_models": boolean,
    "how_to_return": "describe how to return to first tab/model selection (e.g., 'click first tab', 'click Models tab', 'navigate back to model selection URL')",
    "first_tab_selector": "CSS selector or text to click first tab (e.g., '[data-step=\"1\"]', 'Models', 'Choose Model')"
  }},
  "exploration_complete": boolean
}}

IMPORTANT:
- NEVER recommend clicking disabled elements (disabled: true)
- You can recommend MULTIPLE actions in sequence (e.g., select option THEN click next)
- OR you can recommend SINGLE action (just select) if it will reveal new content dynamically
- Look for patterns: if this is a multi-step form, describe the workflow pattern
- For "select_then_next" pattern: recommend selecting an option AND clicking next in one sequence
- For "conditional_reveal" pattern: recommend selecting options one at a time to reveal dependent options
- If you detect a repeating pattern (like tabs or multi-step wizard), set workflow_pattern.detected = true
- Extract ALL visible options in new_options_visible before recommending actions
- Priority: Select options → Click Next → Move to next tab/section
- Group related actions together to minimize iterations
- **CRITICAL**: Detect final/last step with text like FINISH, COMPLETE, SUMMARY, REVIEW ORDER
- **CRITICAL**: If at final step AND this is a multi-model configurator, set should_return_to_models=true
- **CRITICAL**: Describe how to return to first tab/model selection (click tab, back button, navigate URL)

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
                'actions_sequence': [],
                'workflow_pattern': {'detected': False},
                'exploration_complete': True
            }
    
    async def find_and_click_element(self, page, recommendation: Dict) -> bool:
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
                    if await element.is_visible():
                        # Check if disabled before clicking
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || 
                                   el.hasAttribute('disabled') || 
                                   el.getAttribute('aria-disabled') === 'true' ||
                                   el.classList.contains('disabled') ||
                                   el.style.pointerEvents === 'none';
                        }""")
                        
                        if is_disabled:
                            print(f"  ⚠️ Element is disabled, skipping: '{text_contains}'")
                            return False
                        
                        await element.scroll_into_view_if_needed()
                        
                        # Try regular click first, then JavaScript click as fallback
                        try:
                            await element.click(timeout=3000)
                            print(f"  ✓ Clicked element by text: '{text_contains}'")
                        except:
                            # Fallback to JavaScript click
                            await element.evaluate('el => el.click()')
                            print(f"  ✓ Clicked element via JavaScript: '{text_contains}'")
                        
                        return True
                except Exception as e:
                    pass
            
            # Strategy 2: Try by role and text
            if text_contains:
                try:
                    element = page.get_by_role('button', name=text_contains).first
                    if await element.is_visible():
                        # Check if disabled
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || 
                                   el.hasAttribute('disabled') || 
                                   el.getAttribute('aria-disabled') === 'true' ||
                                   el.classList.contains('disabled');
                        }""")
                        
                        if is_disabled:
                            print(f"  ⚠️ Button is disabled, skipping: '{text_contains}'")
                            return False
                        
                        await element.scroll_into_view_if_needed()
                        await element.click(timeout=3000)
                        print(f"  ✓ Clicked button: '{text_contains}'")
                        return True
                except Exception as e:
                    pass
            
            # Strategy 3: Try finding by class
            if class_contains:
                try:
                    element = page.locator(f'[class*="{class_contains}"]').first
                    if await element.is_visible():
                        # Check if disabled
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || 
                                   el.hasAttribute('disabled') || 
                                   el.getAttribute('aria-disabled') === 'true' ||
                                   el.classList.contains('disabled');
                        }""")
                        
                        if is_disabled:
                            print(f"  ⚠️ Element is disabled, skipping class: '{class_contains}'")
                            return False
                        
                        await element.scroll_into_view_if_needed()
                        await element.click(timeout=3000)
                        print(f"  ✓ Clicked element by class: '{class_contains}'")
                        return True
                except Exception as e:
                    pass
            
            # Strategy 4: Try clicking at position
            if position[0] and position[1]:
                try:
                    await page.mouse.click(position[0], position[1])
                    print(f"  ✓ Clicked at position: {position}")
                    return True
                except Exception as e:
                    pass
            
            print(f"  ✗ Could not find element to click")
            return False
            
        except Exception as e:
            print(f"  ✗ Error clicking: {e}")
            return False
    
    async def execute_action_sequence(self, page, actions: List[Dict]) -> int:
        """Execute a sequence of actions and return count of successful actions"""
        successful = 0
        
        for i, action in enumerate(actions, 1):
            action_type = action.get('action_type', 'click')
            print(f"\n  [{i}/{len(actions)}] {action_type.upper()}: {action.get('element_description')}")
            
            # Check if this is a next/continue button (last action in sequence)
            is_next_button = (i == len(actions) and 
                            action_type.lower() == 'click_next')
            
            # Check if this is a select action that might reveal content
            is_select_action = action_type.lower() == 'select'
            
            clicked = await self.find_and_click_element(page, action)
            
            if clicked:
                successful += 1
                
                if is_next_button:
                    # For next/continue buttons, wait longer for navigation/content change
                    print("  → Waiting for page transition...")
                    try:
                        # Wait for either URL change or network to be idle
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        # Fallback to regular timeout
                        await page.wait_for_timeout(3000)
                elif is_select_action:
                    # For select actions, wait for potential dynamic content reveal
                    print("  → Waiting for content reveal...")
                    try:
                        # Wait for network activity to settle (content might load)
                        await page.wait_for_load_state('networkidle', timeout=3000)
                    except:
                        # Fallback to regular timeout
                        await page.wait_for_timeout(2000)
                else:
                    # Regular action, shorter wait
                    await page.wait_for_timeout(1500)
            else:
                print(f"  ⚠️ Failed to execute action, continuing...")
        
        return successful
    
    def detect_and_apply_pattern(self, workflow_pattern: Dict) -> Optional[List[Dict]]:
        """Detect workflow patterns and generate actions automatically"""
        if not workflow_pattern.get('detected'):
            return None
        
        pattern_type = workflow_pattern.get('pattern_type')
        
        if pattern_type == 'select_then_next':
            # Store the pattern for future iterations
            if not self.detected_pattern:
                self.detected_pattern = pattern_type
                print(f"\n🔍 Pattern detected: {workflow_pattern.get('description')}")
                print("   Future iterations will use this pattern automatically")
            return None  # Let Gemini guide the first few times
        
        elif pattern_type == 'conditional_reveal':
            # Store the pattern for conditional options
            if not self.detected_pattern:
                self.detected_pattern = pattern_type
                print(f"\n🔍 Pattern detected: {workflow_pattern.get('description')}")
                print("   Options reveal dynamically after selections")
                print("   Will select options one at a time to reveal dependent options")
            return None  # Let Gemini guide each selection
        
        return None
    
    async def interactive_extraction(self, url: str, max_iterations: int = 15) -> List[Dict]:
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
        previous_url = None
        previous_content_hash = None
        no_change_count = 0
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            page = await browser.new_page()
            
            try:
                # Initial page load
                print("→ Loading initial page...")
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(3000)
                
                # Iterative exploration
                for iteration in range(max_iterations):
                    print(f"\n{'─'*80}")
                    print(f"ITERATION {iteration + 1}/{max_iterations}")
                    print(f"{'─'*80}")
                    
                    # Capture current state
                    print("→ Capturing page state...")
                    page_state = await self.capture_page_state(page)
                    
                    if not page_state:
                        print("✗ Failed to capture page state")
                        break
                    
                    # Check if page has changed (URL, content, or visible text)
                    current_url = page.url
                    current_content = str(page_state.get('interactive_elements', []))
                    current_content_hash = hash(current_content)
                    
                    # Also check main heading/step text to detect SPA changes
                    try:
                        current_main_text = await page.inner_text('body')
                        current_main_text = current_main_text[:1000]  # First 1000 chars
                    except:
                        current_main_text = ""
                    
                    page_changed = (current_url != previous_url or 
                                  current_content_hash != previous_content_hash or
                                  (previous_url is not None and current_main_text != getattr(self, '_prev_main_text', '')))
                    
                    if not page_changed and iteration > 0:
                        no_change_count += 1
                        print(f"⚠️ Page hasn't changed (attempt {no_change_count})")
                        
                        # If page hasn't changed after actions, try clicking next without Gemini
                        if no_change_count <= 2:
                            print("→ Retrying next button without consulting Gemini...")
                            # Try to find and click common "next" buttons
                            next_button_found = False
                            for next_text in ['CONTINUE', 'NEXT', 'Next', 'Continue', 'PROCEED']:
                                try:
                                    element = page.get_by_text(next_text, exact=False).first
                                    if await element.is_visible():
                                        is_disabled = await element.evaluate("""el => {
                                            return el.disabled || 
                                                   el.hasAttribute('disabled') || 
                                                   el.getAttribute('aria-disabled') === 'true' ||
                                                   el.classList.contains('disabled') ||
                                                   el.style.pointerEvents === 'none';
                                        }""")
                                        
                                        if not is_disabled:
                                            await element.scroll_into_view_if_needed()
                                            await element.click(timeout=3000)
                                            print(f"  ✓ Clicked: '{next_text}'")
                                            
                                            # Wait for navigation/content change
                                            print("  → Waiting for page transition...")
                                            try:
                                                await page.wait_for_load_state('networkidle', timeout=5000)
                                            except:
                                                await page.wait_for_timeout(3000)
                                            
                                            next_button_found = True
                                            break
                                except:
                                    continue
                            
                            if not next_button_found:
                                print("  ⚠️ No enabled next button found")
                            
                            # Continue to next iteration to check if page changed
                            continue
                        else:
                            print("⚠️ Page still hasn't changed after retries")
                            # Fall through to consult Gemini
                    else:
                        no_change_count = 0  # Reset counter when page changes
                    
                    # Ask Gemini what to do (only when page changed or after retries failed)
                    print("→ Consulting Gemini for guidance...")
                    guidance = self.ask_gemini_what_to_click(page_state, all_options)
                    
                    # Extract newly visible options
                    new_options = guidance.get('new_options_visible', [])
                    if new_options:
                        print(f"✓ Found {len(new_options)} new options:")
                        for opt in new_options:
                            print(f"  • {opt.get('category')} → {opt.get('component')}")
                        all_options.extend(new_options)
                        
                        # If we found new options, the page definitely changed - reset counter
                        no_change_count = 0
                    
                    # Check for workflow patterns
                    workflow_pattern = guidance.get('workflow_pattern', {})
                    self.detect_and_apply_pattern(workflow_pattern)
                    
                    # Check if exploration is complete
                    if guidance.get('exploration_complete'):
                        print("\n✓ Gemini says exploration is complete!")
                        break
                    
                    # Check if we're at the final step
                    at_final_step = guidance.get('at_final_step', False)
                    final_step_info = guidance.get('final_step_info', {})
                    
                    if at_final_step:
                        print("\n✓ Reached final step of customization!")
                        
                        # Check if we should return to model selection
                        should_return = final_step_info.get('should_return_to_models', False)
                        
                        if should_return and self.model_selection_page_url:
                            print("→ This is a multi-model configurator, returning to model selection...")
                            how_to_return = final_step_info.get('how_to_return', '')
                            first_tab_selector = final_step_info.get('first_tab_selector', '')
                            
                            try:
                                # Try to click first tab if selector provided
                                if first_tab_selector:
                                    print(f"  → Trying to click first tab: {first_tab_selector}")
                                    try:
                                        element = page.get_by_text(first_tab_selector, exact=False).first
                                        await element.click(timeout=3000)
                                        await page.wait_for_timeout(2000)
                                        print("  ✓ Clicked first tab")
                                    except:
                                        # Fallback to URL navigation
                                        print(f"  → Tab click failed, navigating to: {self.model_selection_page_url}")
                                        await page.goto(self.model_selection_page_url, wait_until='domcontentloaded', timeout=30000)
                                        await page.wait_for_timeout(3000)
                                else:
                                    # Navigate back to model selection URL
                                    print(f"  → Navigating back to: {self.model_selection_page_url}")
                                    await page.goto(self.model_selection_page_url, wait_until='domcontentloaded', timeout=30000)
                                    await page.wait_for_timeout(3000)
                                
                                print("  ✓ Returned to model selection page")
                                
                                # Reset tracking for next model
                                previous_url = None
                                previous_content_hash = None
                                no_change_count = 0
                                continue  # Continue to next iteration to select another model
                                
                            except Exception as e:
                                print(f"  ✗ Failed to return to model selection: {e}")
                                break
                        else:
                            # Final step reached and no more models to explore
                            print("✓ Customization complete!")
                            break
                    
                    # Execute action sequence (multiple actions in one iteration)
                    actions_sequence = guidance.get('actions_sequence', [])
                    if actions_sequence:
                        print(f"\n→ Executing {len(actions_sequence)} action(s)...")
                        for i, action in enumerate(actions_sequence, 1):
                            print(f"  Action {i}: {action.get('reason')}")
                        
                        successful = await self.execute_action_sequence(page, actions_sequence)
                        print(f"\n  ✓ Completed {successful}/{len(actions_sequence)} actions")
                        
                        # Additional wait for any animations/transitions
                        if successful > 0:
                            await page.wait_for_timeout(1000)
                    else:
                        # Fallback to old single-click recommendation
                        click_rec = guidance.get('click_recommendation', {})
                        if click_rec and click_rec.get('should_click'):
                            print(f"\n→ Single action: {click_rec.get('reason')}")
                            clicked = await self.find_and_click_element(page, click_rec)
                            if clicked:
                                await page.wait_for_timeout(2000)
                        else:
                            print("\n→ No more actions recommended")
                            break
                    
                    # Update tracking at END of iteration (after actions executed)
                    # This allows next iteration to detect if actions caused page change
                    previous_url = page.url
                    try:
                        current_body = await page.inner_text('body')
                        previous_content_hash = hash(str(await self.capture_page_state(page)))
                        self._prev_main_text = current_body[:1000]
                    except:
                        pass
                
                print(f"\n{'='*80}")
                print(f"EXTRACTION COMPLETE")
                print(f"{'='*80}")
                print(f"Total options discovered: {len(all_options)}")
                
            except Exception as e:
                print(f"\n✗ Error during extraction: {e}")
                import traceback
                traceback.print_exc()
            finally:
                await browser.close()
        
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
            writer = csv.DictWriter(f, fieldnames=['Categories', 'Component', 'Price', 'References', 'Image'])
            writer.writeheader()
            
            for opt in options:
                writer.writerow({
                    'Categories': opt.get('category', ''),
                    'Component': opt.get('component', ''),
                    'Price': opt.get('price', 'N/A'),
                    'References': opt.get('reference', ''),
                    'Image': opt.get('image', '')
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


async def main():
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
        options = await extractor.interactive_extraction(url, max_iterations)
        
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
    asyncio.run(main())
