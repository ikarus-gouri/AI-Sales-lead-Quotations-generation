"""
Gemini + Playwright Multi-Model Interactive Configurator Extractor
REALLY FIXED VERSION - Saves page patterns, not option text. Combines select+continue.
WITH SUPABASE MEMORY LAYER - Learning and replay system.
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
import re

# Supabase memory layer
from ..storage.supabase_memory import (
    SupabaseMemory, 
    compute_page_signature, 
    extract_site_domain,
    create_selector_pattern
)

load_dotenv()


class GeminiInteractiveExtractor:
    """Interactive extraction with workflow pattern reuse + Supabase memory"""
    
    def __init__(self, api_key: Optional[str] = None, enable_memory: bool = True):
        """Initialize Gemini Flash with API key and Supabase memory"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY') or os.getenv('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # ========================================
        # SUPABASE MEMORY LAYER
        # ========================================
        self.memory = SupabaseMemory(enabled=enable_memory)
        self.site_domain = None  # Set during extraction
        self.current_state_id = None  # Track current state
        self.previous_state_id = None  # Track previous state for transitions
        
        # MODEL DISCOVERY & TRACKING
        self.all_models = []
        self.explored_models = set()
        self.current_model = None
        
        # NAVIGATION CACHE
        self.restart_button_cache = None
        
        # ========================================
        # WORKFLOW EXECUTION ENGINE - REALLY FIXED
        # ========================================
        # Save PAGE STRUCTURE, not option text!
        self.learned_workflow = []  # List of {step_name, page_structure, action_pattern}
        self.current_step_index = 0
        self.workflow_locked = False
        
        # Continue button patterns (multiple, not just one!)
        self.continue_patterns = []
        
        # OPTIONS STORAGE
        self.all_options = []
        
        # Stats
        self.stats = {
            'total_iterations': 0,
            'gemini_consultations': 0,
            'cached_navigations': 0,
            'models_completed': 0,
            'workflow_executions': 0,
            'gemini_skipped': 0,
            'memory_replays': 0,
            'memory_hits': 0,
            'memory_misses': 0
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
                            
                            const text = el.innerText || el.value || '';
                            const hasPricePattern = /[+\\-]?\\$[\\d,]+|standard|included/i.test(text);
                            let priceData = '';
                            if (hasPricePattern) {
                                const priceMatch = text.match(/[+\\-]?\\$[\\d,]+|standard|included/i);
                                if (priceMatch) priceData = priceMatch[0];
                            }
                            
                            elements.push({
                                selector: selector,
                                text: text.substring(0, 100),
                                tag: el.tagName,
                                id: el.id,
                                classes: el.className,
                                disabled: isDisabled,
                                selected: isSelected,
                                image: imageUrl,
                                hasPricePattern: hasPricePattern,
                                priceData: priceData,
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
    
    # ========================================
    # SUPABASE MEMORY REPLAY
    # ========================================
    
    async def replay_action(self, page, action_type: str, selector_pattern: Dict) -> bool:
        """
        Replay a learned action from Supabase memory.
        
        Args:
            page: Playwright page
            action_type: Type of action ('click', 'select', etc.)
            selector_pattern: Element selector pattern
            
        Returns:
            True if action executed successfully
        """
        try:
            # Build selector from pattern
            tag = selector_pattern.get('tag', '').lower()
            classes = selector_pattern.get('classes', '')
            text = selector_pattern.get('text', '')
            
            # Try multiple selector strategies
            selectors = []
            
            if classes:
                class_parts = classes.split()[:2]  # First 2 class names
                for cls in class_parts:
                    if cls:
                        selectors.append(f'{tag}[class*="{cls}"]')
            
            if tag:
                selectors.append(tag)
            
            # Try each selector
            for selector in selectors:
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    
                    if count > 0:
                        elem = elements.first
                        if await elem.is_visible():
                            await elem.scroll_into_view_if_needed()
                            
                            if action_type == 'click':
                                await elem.click(timeout=2000)
                            elif action_type == 'select':
                                await elem.click(timeout=2000)
                            
                            return True
                except:
                    continue
            
            return False
            
        except Exception as e:
            print(f"  ⚠️ Replay action failed: {e}")
            return False
    
    def set_site_domain(self, url: str):
        """Set site domain for memory tracking."""
        self.site_domain = extract_site_domain(url)
        print(f"  🌐 Site domain set to: {self.site_domain}")
    
    # ========================================
    # WORKFLOW LEARNING - SAVES STRUCTURE, NOT TEXT
    # ========================================
    
    def learn_workflow_step(self, step_name: str, page_state: Dict, guidance: Dict):
        """Learn PAGE STRUCTURE for this configuration step"""
        if self.workflow_locked:
            return
        
        # Analyze page structure, not option text
        page_structure = {
            'option_element_patterns': [],
            'continue_button_patterns': []
        }
        
        for elem in page_state.get('elements', []):
            text_lower = elem.get('text', '').lower()
            classes = elem.get('classes', '')
            tag = elem.get('tag', '')
            
            # Identify Continue/Next button patterns
            if any(word in text_lower for word in ['continue', 'next']) and not elem.get('disabled'):
                pattern = {
                    'tag': tag,
                    'class_signature': self._extract_class_signature(classes),
                    'text_pattern': elem.get('text', '')[:20]
                }
                if pattern not in page_structure['continue_button_patterns']:
                    page_structure['continue_button_patterns'].append(pattern)
            
            # Identify option element patterns (NOT the text!)
            elif not elem.get('disabled') and tag in ['INPUT', 'BUTTON', 'A']:
                if 'continue' not in text_lower and 'next' not in text_lower and 'back' not in text_lower:
                    pattern = {
                        'tag': tag,
                        'class_signature': self._extract_class_signature(classes),
                        'has_price': elem.get('hasPricePattern', False),
                        'input_type': 'radio' if 'radio' in classes.lower() else 'button'
                    }
                    # Only save unique patterns
                    if pattern not in page_structure['option_element_patterns']:
                        page_structure['option_element_patterns'].append(pattern)
        
        # Save workflow step with structure
        workflow_step = {
            'step_name': step_name,
            'page_structure': page_structure,
            'step_index': len(self.learned_workflow)
        }
        
        self.learned_workflow.append(workflow_step)
        
        # Add continue patterns to global cache
        for pattern in page_structure['continue_button_patterns']:
            if pattern not in self.continue_patterns:
                self.continue_patterns.append(pattern)
        
        print(f"  📌 Learned workflow step {len(self.learned_workflow)}: {step_name}")
        print(f"     Option patterns: {len(page_structure['option_element_patterns'])}")
        print(f"     Continue patterns: {len(page_structure['continue_button_patterns'])}")
    
    def _extract_class_signature(self, classes: str) -> str:
        """Extract meaningful class signature (first 2-3 class words)"""
        if not classes:
            return ""
        class_list = classes.split()
        # Take first 2 meaningful classes (ignore utility classes like 'px-4')
        meaningful = [c for c in class_list if len(c) > 3 and not c.startswith('px-') and not c.startswith('py-')]
        return ' '.join(meaningful[:2])
    
    # ========================================
    # WORKFLOW EXECUTION - USES STRUCTURE, NOT TEXT
    # ========================================
    
    async def execute_learned_step(self, page, workflow_step: Dict) -> Tuple[List[Dict], bool]:
        """Execute step using learned page structure"""
        step_name = workflow_step['step_name']
        print(f"  → Executing '{step_name}' from memory (NO GEMINI)")
        self.stats['workflow_executions'] += 1
        self.stats['gemini_skipped'] += 1
        
        page_state = await self.capture_page_state(page)
        if not page_state:
            return [], False
        
        # Extract options using learned patterns
        extracted_options = await self.extract_options_by_pattern(
            page_state, 
            workflow_step['page_structure'],
            step_name
        )
        
        # COMBINED ACTION: Select first option AND click Continue
        success = await self.select_and_continue(page, workflow_step['page_structure'])
        
        return extracted_options, success
    
    async def extract_options_by_pattern(self, page_state: Dict, page_structure: Dict, category: str) -> List[Dict]:
        """Extract options using learned element patterns"""
        options = []
        learned_patterns = page_structure.get('option_element_patterns', [])
        
        if not learned_patterns:
            # Fallback to generic extraction
            return await self.extract_options_generic(page_state, category)
        
        for elem in page_state.get('elements', []):
            if elem.get('disabled'):
                continue
            
            text = elem.get('text', '').strip()
            if not text or any(nav in text.lower() for nav in ['continue', 'next', 'back']):
                continue
            
            # Check if element matches any learned pattern
            elem_signature = self._extract_class_signature(elem.get('classes', ''))
            elem_tag = elem.get('tag', '')
            
            for pattern in learned_patterns:
                if elem_tag == pattern['tag']:
                    # Match by class signature
                    pattern_sig = pattern['class_signature']
                    if pattern_sig and pattern_sig in elem_signature:
                        # Extract price
                        price = "N/A"
                        component = text
                        
                        if elem.get('priceData'):
                            price = elem['priceData']
                            component = text.replace(elem['priceData'], '').strip()
                        elif pattern.get('has_price'):
                            price_match = re.search(r'[+\-]?\$[\d,]+|standard|included', text, re.I)
                            if price_match:
                                price = price_match.group(0)
                                component = text.replace(price, '').strip()
                        
                        options.append({
                            'category': category,
                            'component': component,
                            'price': price,
                            'model': self.current_model,
                            'image': elem.get('image', '')
                        })
                        break  # Match found, move to next element
        
        if options:
            print(f"  ✓ Extracted {len(options)} options by pattern")
        
        return options
    
    async def extract_options_generic(self, page_state: Dict, category: str) -> List[Dict]:
        """Fallback generic extraction"""
        options = []
        
        for elem in page_state.get('elements', []):
            text = elem.get('text', '').strip()
            if not text or elem.get('disabled'):
                continue
            if any(nav in text.lower() for nav in ['continue', 'next', 'back']):
                continue
            
            if elem.get('tag') in ['INPUT', 'BUTTON'] and 2 < len(text) < 200:
                price = "N/A"
                component = text
                
                if elem.get('priceData'):
                    price = elem['priceData']
                    component = text.replace(elem['priceData'], '').strip()
                
                options.append({
                    'category': category,
                    'component': component,
                    'price': price,
                    'model': self.current_model,
                    'image': elem.get('image', '')
                })
        
        return options
    
    async def select_and_continue(self, page, page_structure: Dict) -> bool:
        """COMBINED: Select first option AND click Continue (saves one Gemini call!)"""
        
        # Step 1: Select first option
        option_patterns = page_structure.get('option_element_patterns', [])
        selected = False
        
        if option_patterns:
            # Try to select using learned patterns
            for pattern in option_patterns:
                tag = pattern['tag']
                class_sig = pattern['class_signature']
                
                if tag == 'INPUT':
                    selector = 'input[type="radio"]:not([disabled])'
                elif class_sig:
                    selector = f'{tag.lower()}[class*="{class_sig.split()[0]}"]:not([disabled])'
                else:
                    selector = f'{tag.lower()}:not([disabled])'
                
                try:
                    elements = page.locator(selector)
                    count = await elements.count()
                    
                    for i in range(min(count, 3)):
                        elem = elements.nth(i)
                        if await elem.is_visible():
                            text = await elem.text_content() or ""
                            if any(nav in text.lower() for nav in ['continue', 'next', 'back']):
                                continue
                            
                            await elem.scroll_into_view_if_needed()
                            await elem.click(timeout=2000)
                            print(f"  ✓ Auto-selected option")
                            selected = True
                            await page.wait_for_timeout(500)
                            break
                    
                    if selected:
                        break
                except:
                    continue
        
        # Fallback selection
        if not selected:
            selected = await self.auto_select_generic(page)
        
        if not selected:
            print(f"  ⚠️ Could not auto-select option")
            return False
        
        # Step 2: Click Continue using ALL learned patterns
        continue_clicked = await self.click_continue_multi_pattern(page, page_structure)
        
        return continue_clicked
    
    async def auto_select_generic(self, page) -> bool:
        """Generic option selection fallback"""
        selectors = [
            'input[type="radio"]:not([disabled])',
            'button:not([disabled])',
            '.card:not(.disabled)'
        ]
        
        for selector in selectors:
            try:
                elements = page.locator(selector)
                count = await elements.count()
                
                for i in range(min(count, 3)):
                    elem = elements.nth(i)
                    if await elem.is_visible():
                        text = await elem.text_content() or ""
                        if any(nav in text.lower() for nav in ['continue', 'next', 'back', 'submit']):
                            continue
                        
                        await elem.scroll_into_view_if_needed()
                        await elem.click(timeout=2000)
                        print(f"  ✓ Auto-selected (generic)")
                        await page.wait_for_timeout(500)
                        return True
            except:
                continue
        
        return False
    
    async def click_continue_multi_pattern(self, page, page_structure: Dict) -> bool:
        """Click Continue using ALL learned patterns (not just one!)"""
        
        # Try patterns from this specific page
        continue_patterns = page_structure.get('continue_button_patterns', [])
        
        # Also try all global continue patterns
        for pattern in self.continue_patterns + continue_patterns:
            tag = pattern.get('tag', 'button')
            class_sig = pattern.get('class_signature', '')
            text_pattern = pattern.get('text_pattern', '')
            
            selectors = []
            
            if class_sig:
                # Try class-based selectors
                for class_part in class_sig.split():
                    if class_part:
                        selectors.append(f'{tag.lower()}[class*="{class_part}"]')
            
            if text_pattern:
                # Try text-based selectors
                selectors.append(f'{tag.lower()}:has-text("{text_pattern[:15]}")')
            
            # Generic continue selectors
            selectors.extend([
                'button:has-text("Continue")',
                'button:has-text("CONTINUE")',
                'button:has-text("Next")',
                '[class*="continue"]',
                '[class*="next-step"]'
            ])
            
            for selector in selectors:
                try:
                    elem = page.locator(selector).first
                    if await elem.is_visible():
                        await elem.scroll_into_view_if_needed()
                        await elem.click(timeout=2000)
                        print(f"  ✓ Auto-clicked Continue")
                        self.stats['cached_navigations'] += 1
                        return True
                except:
                    continue
        
        print(f"  ⚠️ Could not click Continue")
        return False
    
    # ========================================
    # GEMINI FUNCTIONS
    # ========================================
    
    def ask_gemini_for_initial_analysis(self, page_state: Dict) -> Dict:
        """First Gemini call: Discover all models"""
        
        prompt = f"""
Analyze this product configurator page.

Current Page:
{page_state['visible_text'][:3000]}

Elements:
{json.dumps(page_state['elements'][:30], indent=2)}

Return JSON:
{{
  "all_models": [
    {{
      "name": "exact model name",
      "selector_hints": {{
        "text_contains": "string",
        "class_contains": "string"
      }}
    }}
  ],
  "workflow_info": {{
    "has_restart_button": boolean,
    "restart_button_text": "string",
    "restart_button_class": "string"
  }}
}}

IMPORTANT: Return ONLY valid JSON, discover ALL models.
"""
        
        try:
            response = self.model.generate_content([
                {'mime_type': 'image/png', 'data': base64.b64decode(page_state['screenshot'])},
                prompt
            ])
            
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
            
        except Exception as e:
            print(f"Error asking Gemini: {e}")
            return {
                'all_models': [{'name': 'Default Product', 'selector_hints': {}}],
                'workflow_info': {}
            }
    
    def ask_gemini_for_guidance(self, page_state: Dict, context: Dict) -> Dict:
        """Ask Gemini: What's this step? Extract options. Select first option AND click Continue."""
        
        prompt = f"""
Configure product: {context['current_model']}, step {context['step_number']}.

Page:
{page_state['visible_text'][:2000]}

Elements:
{json.dumps(page_state['elements'][:30], indent=2)}

Return JSON:
{{
  "current_step": "step category name (e.g., Floor Plan, Exterior)",
  "new_options": [
    {{
      "category": "current_step value",
      "component": "option name",
      "price": "price or N/A",
      "reference": "reference code",
      "image": "image URL"
    }}
  ],
  "next_action": {{
    "action_type": "select_and_continue",
    "select_first": true,
    "reason": "string",
    "selector_hints": {{
      "text_contains": "string for first option to select",
      "class_contains": "string"
    }}
  }},
  "configuration_complete": boolean
}}

CRITICAL:
- Extract ALL visible options
- action_type should be "select_and_continue" to select first option AND click Continue in ONE action
- Set configuration_complete: true when seeing Summary/Review/Complete
- Return ONLY valid JSON
"""
        
        try:
            response = self.model.generate_content([
                {'mime_type': 'image/png', 'data': base64.b64decode(page_state['screenshot'])},
                prompt
            ])
            
            response_text = response.text.strip()
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            
            return json.loads(response_text.strip())
            
        except Exception as e:
            print(f"Error asking Gemini: {e}")
            raise
    
    async def click_element(self, page, selector_hints: Dict) -> bool:
        """Click element using hints"""
        if not selector_hints:
            return False
        
        selectors_to_try = []
        
        if selector_hints.get('text_contains'):
            text = selector_hints['text_contains']
            selectors_to_try.extend([
                f'button:has-text("{text}")',
                f':text("{text}")'
            ])
        
        if selector_hints.get('class_contains'):
            cls = selector_hints['class_contains']
            selectors_to_try.append(f'[class*="{cls}"]')
        
        for selector in selectors_to_try:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible():
                    await elem.scroll_into_view_if_needed()
                    await elem.click(timeout=3000)
                    print(f"  ✓ Clicked: {selector}")
                    return True
            except:
                continue
        
        return False
    
    async def restart_to_model_selection(self, page) -> bool:
        """Restart configurator"""
        if not self.restart_button_cache:
            return False
        
        print("\n  → Restarting...")
        clicked = await self.click_element(page, self.restart_button_cache)
        
        if clicked:
            print("  ✓ Restarted")
            return True
        return False
    
    # ========================================
    # MAIN LOOP - REALLY FIXED
    # ========================================
    
    async def configure_single_model(self, page, model_name: str, max_steps: int = 20) -> List[Dict]:
        """Configure a single model"""
        print(f"\n{'='*80}")
        print(f"CONFIGURING MODEL: {model_name}")
        print(f"{'='*80}")
        
        self.current_step_index = 0
        model_options = []
        gemini_unavailable = False
        
        for step in range(max_steps):
            self.stats['total_iterations'] += 1
            print(f"\n  Step {step + 1}/{max_steps}")
            
            # ========================================
            # WORKFLOW DRIVER
            # ========================================
            if self.workflow_locked and self.current_step_index < len(self.learned_workflow):
                workflow_step = self.learned_workflow[self.current_step_index]
                step_name = workflow_step['step_name']
                print(f"  📋 WORKFLOW MODE: '{step_name}' (using page structure)")
                
                # Execute using learned structure
                extracted_options, success = await self.execute_learned_step(page, workflow_step)
                model_options.extend(extracted_options)
                
                if success:
                    self.current_step_index += 1
                    await page.wait_for_timeout(2000)
                    continue  # Skip Gemini!
                else:
                    print(f"  ⚠️ Pattern execution failed, fallback to Gemini")
            
            # Capture page
            page_state = await self.capture_page_state(page)
            if not page_state:
                break
            
            # ========================================
            # SUPABASE STATE TRACKING
            # ========================================
            if self.memory.is_enabled() and self.site_domain:
                # Compute page signature
                page_sig = compute_page_signature(page_state)
                
                # Upsert state
                state_record = self.memory.upsert_state(
                    site_domain=self.site_domain,
                    url_path=page.url,
                    page_signature=page_sig,
                    model_name=model_name or "unknown",
                    step_index=step,
                    is_terminal=False
                )
                
                # Track state IDs for transition recording
                self.previous_state_id = self.current_state_id
                self.current_state_id = state_record['id'] if state_record else None
                
                # Check for confident transition (AVOID GEMINI!)
                if self.previous_state_id and self.current_state_id:
                    confident_transition = self.memory.get_confident_transition(
                        from_state_id=self.previous_state_id,
                        min_success_rate=0.8,
                        min_seen_count=3
                    )
                    
                    if confident_transition:
                        print(f"  🧠 MEMORY REPLAY: High-confidence transition found (skip Gemini)")
                        self.stats['gemini_skipped'] += 1
                        self.stats['memory_replays'] += 1
                        
                        # Execute replayed action
                        selector_pattern = json.loads(confident_transition['selector_pattern'])
                        success = await self.replay_action(page, confident_transition['action_type'], selector_pattern)
                        
                        if success:
                            self.stats['memory_hits'] += 1
                            # Record success
                            self.memory.record_transition(
                                from_state_id=self.previous_state_id,
                                to_state_id=self.current_state_id,
                                action_type=confident_transition['action_type'],
                                selector_pattern=selector_pattern,
                                success=True
                            )
                            await page.wait_for_timeout(2000)
                            continue  # Skip Gemini consultation!
                        else:
                            self.stats['memory_misses'] += 1
                            # Record failure and fall through to Gemini
                            self.memory.record_transition(
                                from_state_id=self.previous_state_id,
                                to_state_id=self.current_state_id,
                                action_type=confident_transition['action_type'],
                                selector_pattern=selector_pattern,
                                success=False
                            )
                            print(f"  ⚠️ Memory replay failed, falling back to Gemini")
            
            # ========================================
            # GEMINI FALLBACK
            # ========================================
            if gemini_unavailable:
                print("  ⚠️ Gemini 429 - using patterns only")
                # Try to continue anyway
                if self.continue_patterns:
                    await self.click_continue_multi_pattern(page, {})
                    await page.wait_for_timeout(2000)
                    continue
                else:
                    break
            
            print("  → Consulting Gemini...")
            self.stats['gemini_consultations'] += 1
            
            try:
                guidance = self.ask_gemini_for_guidance(page_state, {
                    'current_model': model_name,
                    'step_number': step
                })
            except Exception as e:
                if '429' in str(e) or 'quota' in str(e).lower():
                    print(f"  ⚠️ Gemini 429 - SWITCHING TO PATTERN MODE")
                    gemini_unavailable = True
                    self.workflow_locked = True
                    continue
                else:
                    print(f"  ✗ Gemini error: {e}")
                    break
            
            # Extract options
            new_options = guidance.get('new_options', [])
            if new_options:
                for opt in new_options:
                    opt['model'] = model_name
                model_options.extend(new_options)
            
            # LEARN page structure (not option text!)
            current_step = guidance.get('current_step')
            if current_step and not self.workflow_locked:
                self.learn_workflow_step(current_step, page_state, guidance)
            
            # Check complete
            if guidance.get('configuration_complete'):
                print(f"\n  ✅ Complete for {model_name}")
                if not self.workflow_locked and len(self.learned_workflow) > 0:
                    self.workflow_locked = True
                    print(f"  🔒 WORKFLOW LOCKED: {len(self.learned_workflow)} steps, {len(self.continue_patterns)} continue patterns")
                break
            
            # Execute action - COMBINED select and continue
            next_action = guidance.get('next_action', {})
            if next_action.get('action_type') == 'select_and_continue':
                # Gemini told us to select first option AND continue
                # But we'll do it using the same select_and_continue method
                if not self.workflow_locked and current_step:
                    # We just learned this step, use it immediately!
                    last_step = self.learned_workflow[-1] if self.learned_workflow else None
                    if last_step:
                        success = await self.select_and_continue(page, last_step['page_structure'])
                        if success:
                            # Record successful transition in Supabase
                            if self.memory.is_enabled() and self.previous_state_id:
                                # Capture new state after action
                                new_page_state = await self.capture_page_state(page)
                                if new_page_state:
                                    new_page_sig = compute_page_signature(new_page_state)
                                    new_state_record = self.memory.upsert_state(
                                        site_domain=self.site_domain,
                                        url_path=page.url,
                                        page_signature=new_page_sig,
                                        model_name=model_name or "unknown",
                                        step_index=step + 1,
                                        is_terminal=False
                                    )
                                    
                                    if new_state_record:
                                        # Record the transition
                                        selector_pattern = create_selector_pattern(
                                            last_step['page_structure'].get('option_element_patterns', [{}])[0]
                                        ) if last_step.get('page_structure') else {}
                                        
                                        self.memory.record_transition(
                                            from_state_id=self.previous_state_id,
                                            to_state_id=new_state_record['id'],
                                            action_type='select_and_continue',
                                            selector_pattern=selector_pattern,
                                            success=True
                                        )
                                        
                                        # Also record continue pattern
                                        if self.continue_patterns:
                                            self.memory.upsert_continue_pattern(
                                                site_domain=self.site_domain,
                                                pattern=self.continue_patterns[0],
                                                success=True
                                            )
                            
                            await page.wait_for_timeout(2000)
                            continue
                
                # Fallback: try generic select and continue
                selected = await self.auto_select_generic(page)
                if selected:
                    await page.wait_for_timeout(500)
                    await self.click_continue_multi_pattern(page, {})
                    await page.wait_for_timeout(2000)
                    continue
                else:
                    break
            else:
                # Old style action
                selector_hints = next_action.get('selector_hints', {})
                clicked = await self.click_element(page, selector_hints)
                if clicked:
                    await page.wait_for_timeout(2000)
                else:
                    break
        
        return model_options
    
    async def interactive_extraction(self, url: str, max_iterations: int = 100) -> List[Dict]:
        """Main extraction workflow with Supabase memory"""
        # Initialize site domain for memory tracking
        self.set_site_domain(url)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            page = await browser.new_page()
            
            try:
                print(f"Navigating to {url}")
                await page.goto(url, wait_until='domcontentloaded', timeout=60000)
                await page.wait_for_timeout(3000)
                
                print("\n📋 PHASE 1: DISCOVERING MODELS")
                print("="*80)
                
                page_state = await self.capture_page_state(page)
                
                print("→ Analyzing page structure...")
                self.stats['gemini_consultations'] += 1
                
                analysis = self.ask_gemini_for_initial_analysis(page_state)
                
                # Store models
                self.all_models = analysis.get('all_models', [])
                if not self.all_models:
                    self.all_models = [{'name': 'Default Product', 'selector_hints': {}}]
                
                print(f"\n✓ Discovered {len(self.all_models)} model(s):")
                for i, model in enumerate(self.all_models, 1):
                    print(f"  {i}. {model['name']}")
                
                # Cache restart
                workflow_info = analysis.get('workflow_info', {})
                if workflow_info.get('restart_button_text'):
                    self.restart_button_cache = {
                        'text_contains': workflow_info['restart_button_text'],
                        'class_contains': workflow_info.get('restart_button_class', '')
                    }
                    print(f"📌 Cached Restart: {workflow_info['restart_button_text']}")
                
                # Configure each model
                print(f"\n\n📋 PHASE 2: CONFIGURING MODELS")
                print("="*80)
                
                for model_index, model in enumerate(self.all_models):
                    model_name = model['name']
                    
                    if model_name in self.explored_models:
                        continue
                    
                    self.current_model = model_name
                    
                    # Select model
                    if model_index > 0:
                        print(f"\n→ Selecting model: {model_name}")
                        if await self.click_element(page, model.get('selector_hints', {})):
                            await page.wait_for_timeout(2000)
                    
                    # Configure
                    model_options = await self.configure_single_model(page, model_name)
                    
                    self.all_options.extend(model_options)
                    self.explored_models.add(model_name)
                    self.stats['models_completed'] += 1
                    
                    print(f"\n✅ Completed {model_name}: {len(model_options)} options")
                    
                    # Restart
                    if model_index < len(self.all_models) - 1:
                        if await self.restart_to_model_selection(page):
                            await page.wait_for_timeout(2000)
                        else:
                            break
                
                # Summary
                print(f"\n{'='*80}")
                print(f"EXTRACTION COMPLETE")
                print(f"{'='*80}")
                print(f"Models configured: {len(self.explored_models)}/{len(self.all_models)}")
                print(f"Total options: {len(self.all_options)}")
                
                print(f"\n{'='*80}")
                print("OPTIMIZATION STATISTICS")
                print(f"{'='*80}")
                print(f"Total iterations:        {self.stats['total_iterations']}")
                print(f"Gemini consultations:    {self.stats['gemini_consultations']}")
                print(f"Workflow executions:     {self.stats['workflow_executions']}")
                print(f"Gemini calls skipped:    {self.stats['gemini_skipped']}")
                
                # Memory stats
                if self.memory.is_enabled():
                    print(f"\n🧠 Memory Layer:")
                    print(f"   Memory replays:       {self.stats.get('memory_replays', 0)}")
                    print(f"   Replay successes:     {self.stats.get('memory_hits', 0)}")
                    print(f"   Replay failures:      {self.stats.get('memory_misses', 0)}")
                    
                    # Get overall memory stats
                    memory_stats = self.memory.get_stats(site_domain=self.site_domain)
                    if 'states' in memory_stats:
                        print(f"   States recorded:      {memory_stats['states']}")
                        print(f"   Transitions learned:  {memory_stats['transitions']}")
                        print(f"   Patterns cached:      {memory_stats['patterns']}")
                
                if self.workflow_locked:
                    print(f"\n🔒 Workflow Reuse: ENABLED")
                    print(f"   Learned {len(self.learned_workflow)} page structures")
                    print(f"   Cached {len(self.continue_patterns)} continue button patterns")
                
                if self.stats['total_iterations'] > 0:
                    reduction = self.stats['gemini_skipped'] / self.stats['total_iterations']
                    print(f"\nAPI call reduction:      {reduction:.1%}")
                
                print(f"{'='*80}\n")
                
            except Exception as e:
                print(f"\n✗ Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                await browser.close()
        
        return self.all_options
    
    def save_results(self, options: List[Dict], url: str) -> Tuple[str, str]:
        """Save results"""
        import csv
        
        timestamp = int(time.time())
        
        # JSON
        json_filename = f"extraction_{timestamp}.json"
        result = {
            'url': url,
            'extracted_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_models': len(self.all_models),
            'models_explored': len(self.explored_models),
            'total_options': len(options),
            'workflow_locked': self.workflow_locked,
            'learned_workflow': self.learned_workflow,
            'stats': self.stats,
            'options': options
        }
        
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # CSV
        csv_filename = f"extraction_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Model', 'Category', 'Component', 'Price', 'Image'])
            writer.writeheader()
            
            for opt in options:
                writer.writerow({
                    'Model': opt.get('model', ''),
                    'Category': opt.get('category', ''),
                    'Component': opt.get('component', ''),
                    'Price': opt.get('price', 'N/A'),
                    'Image': opt.get('image', '')
                })
        
        return json_filename, csv_filename


async def main():
    if len(sys.argv) < 2:
        print("Usage: python script.py <url>")
        sys.exit(1)
    
    url = sys.argv[1]
    
    try:
        extractor = GeminiInteractiveExtractor()
        options = await extractor.interactive_extraction(url)
        
        if options:
            json_file, csv_file = extractor.save_results(options, url)
            print(f"\n✓ Results saved:")
            print(f"  JSON: {json_file}")
            print(f"  CSV: {csv_file}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Fix for Windows: Set event loop policy for subprocess support (Playwright)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())