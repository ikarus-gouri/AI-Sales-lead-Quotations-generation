"""
Gemini + Playwright Interactive Configurator Extractor - IMPROVED
Handles multiple UI patterns: tabs, forms with dynamic reveals, and multi-step wizards
Better model tracking to avoid re-exploring the same models
"""

import os
import json
import sys
import google.generativeai as genai
from playwright.async_api import async_playwright
from typing import Dict, List, Optional, Tuple, Set
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
        
        # Pattern detection for optimization
        self.detected_pattern = None
        self.ui_pattern_type = None  # 'tabs', 'form_reveal', 'multi_step'
        
        # Track model selection page for multi-model configurators
        self.model_selection_page_url = None
        self.model_selection_detected = False
        
        # Track explored models in multimodel configurators
        self.explored_models: Set[str] = set()
        self.available_models: List[str] = []
        self.current_model: Optional[str] = None
        
        # Track completion state
        self.customization_complete = False
        
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
                    '[role="tab"]',
                    'a[href]',
                    '.card',
                    '[class*="option"]',
                    '[class*="choice"]',
                    '[class*="model"]',
                    '[class*="selector"]',
                    '[class*="tab"]',
                    'input[type="radio"]',
                    'input[type="checkbox"]',
                    'select',
                    '[class*="next"]',
                    '[class*="continue"]',
                    '[class*="submit"]',
                    '[class*="finish"]',
                    '[class*="complete"]',
                    '[class*="download"]'
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
                            
                            // Check if this is a tab element
                            const isTab = el.getAttribute('role') === 'tab' || 
                                         el.classList.contains('tab') ||
                                         selector.includes('tab');
                            
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
                                isTab: isTab,
                                image: imageUrl,
                                position: {
                                    x: Math.round(rect.left + rect.width / 2),
                                    y: Math.round(rect.top + rect.height / 2)
                                },
                                attributes: {
                                    href: el.href,
                                    type: el.type,
                                    name: el.name,
                                    value: el.value,
                                    role: el.getAttribute('role')
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
        
        # Build explored models section
        explored_models_info = ""
        if self.explored_models:
            explored_models_info = f"""

⚠️ ALREADY EXPLORED MODELS (DO NOT SELECT THESE AGAIN):
{', '.join(sorted(self.explored_models))}

🎯 CRITICAL: When at model selection page, you MUST select a DIFFERENT model that is NOT in the above list!
If ALL models have been explored, set exploration_complete = true.
"""
        
        # Build UI pattern hint
        ui_pattern_hint = ""
        if self.ui_pattern_type:
            ui_pattern_hint = f"""

🔍 DETECTED UI PATTERN: {self.ui_pattern_type.upper()}
- If 'form_reveal': Options appear dynamically when selections are made. NO "Next" button needed.
- If 'tabs': Use tab navigation to explore different sections.
- If 'multi_step': Traditional wizard with Next/Continue buttons between steps.
"""
        
        prompt = f"""
You are guiding an automated browser to extract ALL customization options from a product configurator.

Current Page URL: {page_state['url']}{explored_models_info}{ui_pattern_hint}

Discovered Options So Far ({len(discovered_so_far)} items):
{json.dumps(discovered_so_far[-10:], indent=2) if discovered_so_far else 'None yet'}

Current Page Visible Text:
{page_state['visible_text'][:3000]}

Available Interactive Elements (with positions and states):
{json.dumps(page_state['elements'][:30], indent=2)}

TASK: Analyze the page and tell me:
1. What NEW options are visible on the current page that we haven't captured yet?
2. What UI PATTERN does this page use?
3. What should I do next to reveal MORE customization options?

UI PATTERN DETECTION:
Identify which pattern this configurator uses:

A) **FORM WITH DYNAMIC REVEAL** (no next button needed):
   - Selecting an option reveals related customizations BELOW it on the SAME page
   - NO explicit "Next" or "Continue" buttons between sections
   - Content updates dynamically without navigation
   - Example: Click "Model A" → Interior options appear below → Click "Red Interior" → Accessories appear below
   → Action: Select options one at a time, extract revealed content, continue selecting

B) **TAB-BASED NAVIGATION**:
   - Multiple tabs visible (Models, Colors, Options, Summary, etc.)
   - Each tab shows different customization categories
   - Tabs have role="tab" or similar attributes
   → Action: Click through each tab, extract options from each

C) **MULTI-STEP WIZARD** (traditional flow):
   - Clear step indicators (Step 1, Step 2, etc.)
   - Explicit "Next" or "Continue" buttons to advance
   - Each step is a separate page/view
   → Action: Select options on current step, then click Next

CRITICAL: DISTINGUISH BETWEEN PRODUCTS vs CUSTOMIZATIONS:
- **PRODUCTS/MODELS**: Different items like "2026 King Aire", "2026 Essex" - these are SEPARATE products
  → Category: Use descriptive names like "Model Selection", "Available Products", "Choose Model"
  → Each model should be extracted as a separate option under this category
  
- **CUSTOMIZATIONS**: Options for the SAME product like "Red", "Blue", "Leather Seats", "Sunroof"
  → Category: Use specific names like "Exterior Color", "Interior Fabric", "Optional Features"
  → These are variations/add-ons for one product

COMPLETION DETECTION:
Watch for phrases indicating customization is COMPLETE:
- "Customization Complete"
- "Configuration Created"
- "Download Configuration"
- "Review Your Selections"
- "Order Summary"
- "Finish" or "Complete" buttons (not just "Next")
- Summary/review pages showing all selected options

If you detect completion:
1. Set at_final_step = true
2. Set customization_complete = true
3. If this is a multi-model configurator AND there are unexplored models, set should_return_to_models = true

IMPORTANT RULES FOR CLICKING:
- NEVER click disabled buttons (disabled: true)
- "Next", "Continue", "Submit" buttons are often disabled until required selections are made
- FIRST select/click option cards or radio buttons on the current page
- For FORM_REVEAL pattern: Don't look for Next buttons - content reveals dynamically
- For TABS pattern: Click tabs to navigate, no Next button needed
- Only recommend clicking ENABLED elements (disabled: false)

Return JSON with this structure:
{{
  "new_options_visible": [
    {{
      "category": "string - IMPORTANT: Use 'Model Selection' or similar for product choices, specific names for customizations",
      "component": "string - option name (e.g., 2026 KING AIRE, ANTRIM color, Leather seats)",
      "price": "string - price if visible, else N/A",
      "reference": "string - any additional reference info"
    }}
  ],
  "ui_pattern": {{
    "detected": boolean,
    "pattern_type": "form_reveal" | "tabs" | "multi_step" | "unknown",
    "description": "string - describe the pattern",
    "has_tabs": boolean,
    "has_next_button": boolean,
    "requires_next_click": boolean - true only if multi_step wizard needs Next to advance
  }},
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
  "customization_complete": boolean - true if configuration is finished/complete,
  "at_final_step": boolean - true if at summary/finish page,
  "final_step_info": {{
    "completion_message": "string - what text indicates completion",
    "should_return_to_models": boolean - true if multi-model AND models remaining,
    "how_to_return": "describe how to return to model selection",
    "first_tab_selector": "string - selector for first tab if applicable"
  }},
  "exploration_complete": boolean - true if ALL models explored OR single model complete
}}

CRITICAL NOTES:
- For form_reveal pattern: Don't recommend "Next" clicks - just select options
- For tabs pattern: Navigate tabs, no Next needed
- For multi_step: Select options AND click Next
- Always check if customization is COMPLETE before continuing
- If complete AND multi-model, prepare to return to model selection

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
            
            # Update UI pattern if detected
            ui_pattern = result.get('ui_pattern', {})
            if ui_pattern.get('detected') and ui_pattern.get('pattern_type') != 'unknown':
                detected_type = ui_pattern['pattern_type']
                if self.ui_pattern_type != detected_type:
                    self.ui_pattern_type = detected_type
                    print(f"\n🔍 UI Pattern Detected: {detected_type.upper()}")
                    print(f"   {ui_pattern.get('description', '')}")
            
            return result
            
        except Exception as e:
            print(f"Error asking Gemini: {e}")
            return {
                'new_options_visible': [],
                'actions_sequence': [],
                'ui_pattern': {'detected': False},
                'exploration_complete': True
            }
    
    def match_options_with_images(self, options: List[Dict], elements: List[Dict]) -> List[Dict]:
        """Match extracted options with their images from Playwright element data"""
        enriched_options = []
        
        for option in options:
            component_text = option.get('component', '').lower()
            
            # Find matching element by text similarity
            best_match = None
            best_score = 0
            
            for element in elements:
                element_text = element.get('text', '').lower()
                
                # Simple text matching - check if option name is in element text
                if component_text and element_text:
                    if component_text in element_text or element_text in component_text:
                        # Calculate match score (higher is better)
                        score = len(component_text) / (len(element_text) + 1)
                        if score > best_score and element.get('image'):
                            best_score = score
                            best_match = element
            
            # Add image URL if found
            option['image'] = best_match.get('image', '') if best_match else ''
            enriched_options.append(option)
        
        return enriched_options
    
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
            
            # Determine wait strategy based on action type and UI pattern
            is_next_button = action_type.lower() == 'click_next'
            is_tab_click = action_type.lower() == 'click_tab'
            is_select_action = action_type.lower() == 'select'
            
            clicked = await self.find_and_click_element(page, action)
            
            if clicked:
                successful += 1
                
                if is_next_button and self.ui_pattern_type == 'multi_step':
                    # Multi-step wizard: wait for navigation
                    print("  → Waiting for page transition...")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        await page.wait_for_timeout(3000)
                        
                elif is_tab_click or (is_select_action and self.ui_pattern_type == 'tabs'):
                    # Tab navigation: wait for content change
                    print("  → Waiting for tab content...")
                    await page.wait_for_timeout(2000)
                    
                elif is_select_action and self.ui_pattern_type == 'form_reveal':
                    # Form reveal: wait for dynamic content
                    print("  → Waiting for dynamic content reveal...")
                    try:
                        await page.wait_for_load_state('networkidle', timeout=3000)
                    except:
                        await page.wait_for_timeout(2000)
                else:
                    # Default wait
                    await page.wait_for_timeout(1500)
            else:
                print(f"  ⚠️ Failed to execute action, continuing...")
        
        return successful
    
    def detect_model_selection(self, new_options: List[Dict]) -> bool:
        """Detect if we're on a model selection page and extract available models"""
        model_keywords = ['model selection', 'choose model', 'select model', 
                         'available products', 'choose coach', 'select coach',
                         'available models', 'select a coach']
        
        for opt in new_options:
            category = opt.get('category', '').lower()
            if any(keyword in category for keyword in model_keywords):
                model_name = opt.get('component', '')
                if model_name and model_name not in self.available_models:
                    self.available_models.append(model_name)
                    
        if self.available_models and not self.model_selection_detected:
            self.model_selection_detected = True
            print(f"\n🎯 Multi-Model Configurator Detected!")
            print(f"   Available Models: {', '.join(self.available_models)}")
            return True
            
        return False
    
    async def return_to_model_selection(self, page, final_step_info: Dict) -> bool:
        """Return to model selection page to explore another model"""
        print("\n→ Returning to model selection...")
        
        first_tab_selector = final_step_info.get('first_tab_selector', '')
        how_to_return = final_step_info.get('how_to_return', '')
        
        try:
            # Strategy 1: Look for restart/start over buttons
            restart_keywords = [
                'START OVER', 'Start Over', 'start over',
                'RESTART', 'Restart', 'restart',
                'RETRY', 'Retry', 'retry',
                'BUILD ANOTHER', 'Build Another', 'build another',
                'CONFIGURE ANOTHER', 'Configure Another', 'configure another',
                'NEW CONFIGURATION', 'New Configuration',
                'BACK TO MODELS', 'Back to Models'
            ]
            
            print("  → Strategy 1: Looking for restart button...")
            for keyword in restart_keywords:
                try:
                    element = page.get_by_text(keyword, exact=False).first
                    if await element.is_visible():
                        is_disabled = await element.evaluate("""el => {
                            return el.disabled || el.hasAttribute('disabled') || 
                                   el.getAttribute('aria-disabled') === 'true';
                        }""")
                        
                        if not is_disabled:
                            await element.scroll_into_view_if_needed()
                            await element.click(timeout=3000)
                            await page.wait_for_timeout(3000)
                            print(f"  ✓ Clicked restart button: '{keyword}'")
                            return True
                except:
                    continue
            
            # Strategy 2: Try first tab
            if first_tab_selector:
                print(f"  → Strategy 2: Clicking first tab: {first_tab_selector}")
                try:
                    element = page.get_by_text(first_tab_selector, exact=False).first
                    await element.click(timeout=3000)
                    await page.wait_for_timeout(2000)
                    print("  ✓ Clicked first tab")
                    return True
                except:
                    pass
            
            # Strategy 3: Navigate to URL
            if self.model_selection_page_url:
                print(f"  → Strategy 3: Navigating to: {self.model_selection_page_url}")
                await page.goto(self.model_selection_page_url, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_timeout(3000)
                print("  ✓ Returned via URL navigation")
                return True
                
        except Exception as e:
            print(f"  ✗ Failed to return to model selection: {e}")
            
        return False
    
    async def interactive_extraction(self, url: str, max_iterations: int = 20) -> List[Dict]:
        """
        Interactively explore configurator using Gemini's guidance
        
        Args:
            url: The configurator URL
            max_iterations: Maximum number of iterations
            
        Returns:
            List of all discovered options
        """
        print(f"\n{'='*80}")
        print(f"GEMINI + PLAYWRIGHT INTERACTIVE EXTRACTION (IMPROVED)")
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
                
                # Store initial URL
                self.model_selection_page_url = url
                
                # Iterative exploration
                for iteration in range(max_iterations):
                    print(f"\n{'─'*80}")
                    print(f"ITERATION {iteration + 1}/{max_iterations}")
                    if self.current_model:
                        print(f"Current Model: {self.current_model}")
                    if self.explored_models:
                        print(f"Explored Models: {', '.join(sorted(self.explored_models))}")
                    print(f"{'─'*80}")
                    
                    # Capture current state
                    print("→ Capturing page state...")
                    page_state = await self.capture_page_state(page)
                    
                    if not page_state:
                        print("✗ Failed to capture page state")
                        break
                    
                    # Check if page has changed
                    current_url = page.url
                    current_content = str(page_state.get('elements', []))
                    current_content_hash = hash(current_content)
                    
                    page_changed = (current_url != previous_url or 
                                  current_content_hash != previous_content_hash)
                    
                    if not page_changed and iteration > 0:
                        no_change_count += 1
                        print(f"⚠️ Page hasn't changed (attempt {no_change_count})")
                        
                        if no_change_count >= 3:
                            print("⚠️ Page stuck, moving on...")
                            # Don't break, let Gemini decide if exploration is complete
                    else:
                        no_change_count = 0
                    
                    # Ask Gemini for guidance
                    print("→ Consulting Gemini for guidance...")
                    guidance = self.ask_gemini_what_to_click(page_state, all_options)
                    
                    # Extract new options
                    new_options = guidance.get('new_options_visible', [])
                    if new_options:
                        new_options = self.match_options_with_images(new_options, page_state.get('elements', []))
                        
                        print(f"✓ Found {len(new_options)} new options:")
                        for opt in new_options:
                            img_status = "🖼️" if opt.get('image') else "  "
                            print(f"  {img_status} {opt.get('category')} → {opt.get('component')}")
                        
                        # Detect model selection
                        self.detect_model_selection(new_options)
                        
                        all_options.extend(new_options)
                        no_change_count = 0
                    
                    # Check for completion
                    customization_complete = guidance.get('customization_complete', False)
                    at_final_step = guidance.get('at_final_step', False)
                    
                    if customization_complete or at_final_step:
                        print("\n✓ Customization complete for current model!")
                        
                        # Track completed model
                        if self.current_model and self.current_model not in self.explored_models:
                            self.explored_models.add(self.current_model)
                            print(f"  ✓ Marked '{self.current_model}' as explored")
                        
                        final_step_info = guidance.get('final_step_info', {})
                        should_return = final_step_info.get('should_return_to_models', False)
                        
                        # Check if there are more models to explore
                        remaining_models = set(self.available_models) - self.explored_models
                        
                        if should_return and remaining_models:
                            print(f"\n→ Remaining models to explore: {', '.join(sorted(remaining_models))}")
                            
                            if await self.return_to_model_selection(page, final_step_info):
                                # Reset for next model
                                self.current_model = None
                                self.customization_complete = False
                                previous_url = None
                                previous_content_hash = None
                                no_change_count = 0
                                await page.wait_for_timeout(2000)
                                continue
                            else:
                                print("  ✗ Could not return to model selection")
                                break
                        else:
                            if not remaining_models and self.available_models:
                                print(f"\n✓ All models explored! ({len(self.explored_models)} total)")
                            print("✓ Extraction complete!")
                            break
                    
                    # Check if exploration is complete
                    if guidance.get('exploration_complete'):
                        print("\n✓ Gemini says exploration is complete!")
                        break
                    
                    # Execute actions
                    actions_sequence = guidance.get('actions_sequence', [])
                    if actions_sequence:
                        print(f"\n→ Executing {len(actions_sequence)} action(s)...")
                        
                        # Track model selection
                        for action in actions_sequence:
                            if action.get('action_type') == 'select' and not self.current_model:
                                element_text = action.get('element_text', '')
                                if element_text and element_text in self.available_models:
                                    if element_text not in self.explored_models:
                                        self.current_model = element_text
                                        print(f"  🎯 Selecting model: '{self.current_model}'")
                        
                        successful = await self.execute_action_sequence(page, actions_sequence)
                        print(f"\n  ✓ Completed {successful}/{len(actions_sequence)} actions")
                        
                        if successful > 0:
                            await page.wait_for_timeout(1000)
                    else:
                        print("\n→ No actions recommended")
                        if no_change_count >= 2:
                            break
                    
                    # Update tracking
                    previous_url = page.url
                    previous_content_hash = current_content_hash
                
                print(f"\n{'='*80}")
                print(f"EXTRACTION COMPLETE")
                print(f"{'='*80}")
                print(f"Total options discovered: {len(all_options)}")
                if self.explored_models:
                    print(f"Models explored: {', '.join(sorted(self.explored_models))}")
                
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
            'method': 'gemini-interactive-improved',
            'ui_pattern': self.ui_pattern_type,
            'total_options': len(options),
            'explored_models': list(self.explored_models),
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
        
        if self.ui_pattern_type:
            print(f"UI Pattern: {self.ui_pattern_type.upper()}")
        if self.explored_models:
            print(f"Models Explored: {', '.join(sorted(self.explored_models))}\n")
        
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
        print("Usage: python gemini_interactive_extractor_improved.py <url> [max_iterations]")
        print("\nExample:")
        print("  python gemini_interactive_extractor_improved.py https://www.newmarcorp.com/configure-customization/build-your-coach 25")
        sys.exit(1)
    
    url = sys.argv[1]
    max_iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    
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