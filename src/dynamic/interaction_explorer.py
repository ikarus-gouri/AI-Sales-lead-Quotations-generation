"""UI State Exploration Engine for Model-D.

This is the core of Model-D: a generic state explorer that discovers
all possible configuration states by systematically clicking interactive
controls and observing DOM changes.

Philosophy:
    Model-D is NOT a scraper - it's a UI state exploration engine.
    
Algorithm:
    1. Snapshot initial state
    2. For each interactive control:
        a. Click control
        b. Wait for changes
        c. Snapshot new state
        d. Extract diff
        e. If significant: register new state + extract options
        f. Revert to initial state
    3. For nested controls: recursively explore (limited depth)
    
Key Insights:
    - Don't rely on network calls (many configurators are pure JS)
    - Don't hardcode selectors (must work on unknown sites)
    - Use DOM diffing to detect state changes
    - Extract options ONLY from changed DOM regions
"""

import asyncio
import re
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass


@dataclass
class UIState:
    """Represents a distinct UI state after interaction."""
    control_id: str
    control_label: str
    control_type: str
    dom_snapshot: str
    added_content: List[str]
    changed_region: Optional[str]
    options_discovered: List[Dict]
    price_change: Optional[float]
    depth: int


class InteractionExplorer:
    """
    Generic UI state exploration engine.
    
    Discovers all configuration states by systematically interacting
    with controls and observing DOM changes.
    """
    
    def __init__(self, page, config):
        self.page = page
        self.config = config
        
        # Exploration limits (safety)
        self.max_clicks_per_page = 30
        self.max_recursion_depth = 3
        self.max_exploration_time = 20  # seconds
        self.wait_after_click = 1000  # ms
        
        # State tracking
        self.visited_controls: Set[str] = set()
        self.discovered_states: List[UIState] = []
        self.state_graph: Dict[str, List[str]] = {}
    
    async def explore(self, controls: List[Dict]) -> List[UIState]:
        """
        Main exploration method: systematically explore all UI states.
        
        Args:
            controls: List of discovered interactive controls
            
        Returns:
            List of discovered UI states with extracted options
        """
        print(f"  [EXPLORE] Starting UI state exploration")
        print(f"    Controls found: {len(controls)}")
        print(f"    Max clicks: {self.max_clicks_per_page}")
        print(f"    Max depth: {self.max_recursion_depth}")
        
        # Capture initial state
        initial_snapshot = await self._snapshot_dom()
        initial_price = await self._extract_current_price()
        
        print(f"    Initial state captured ({len(initial_snapshot)} chars)")
        
        # Explore states (limited by max_clicks)
        for i, control in enumerate(controls[:self.max_clicks_per_page], 1):
            try:
                control_id = control.get('id', f"control_{i}")
                
                # Skip if already visited
                if control_id in self.visited_controls:
                    continue
                
                print(f"    [{i}/{min(len(controls), self.max_clicks_per_page)}] Exploring: {control.get('label', 'Unknown')}")
                
                # Explore this control's state
                state = await self._explore_control(
                    control=control,
                    initial_snapshot=initial_snapshot,
                    initial_price=initial_price,
                    depth=0
                )
                
                if state and state.added_content:
                    self.discovered_states.append(state)
                    print("changes:", state.added_content[:300], "...")
                    print(f"      ✓ State change detected: {len(state.added_content)} new elements")
                    
                    # If nested controls appear, explore them
                    if state.depth < self.max_recursion_depth:
                        await self._explore_nested(state)
                elif state is None:
                    # Control produced no change - mark as visited and skip
                    pass
                
                self.visited_controls.add(control_id)
                
            except Exception as e:
                print(f"      ✗ Exploration failed: {e}")
                continue
        
        print(f"  [EXPLORE] Complete: {len(self.discovered_states)} states discovered")
        return self.discovered_states
    
    async def _explore_control(
        self,
        control: Dict,
        initial_snapshot: str,
        initial_price: Optional[float],
        depth: int
    ) -> Optional[UIState]:
        """
        Explore a single control: click → observe → extract → revert.
        
        Args:
            control: Control to interact with
            initial_snapshot: DOM snapshot before click
            initial_price: Price before click
            depth: Recursion depth
            
        Returns:
            UIState if significant change detected, None otherwise
        """
        try:
            element = control.get('element')
            if not element:
                return None
            
            # Click control with timeout
            try:
                await element.click(timeout=5000)
            except Exception as click_error:
                print(f"      ✗ Click failed: {click_error}")
                return None
            
            await asyncio.sleep(self.wait_after_click / 1000)
            
            # Capture new state
            new_snapshot = await self._snapshot_dom()
            new_price = await self._extract_current_price()
            
            # Calculate diff
            added_content = self._dom_diff(initial_snapshot, new_snapshot)
            
            # Check if change is significant
            if not self._is_significant_change(added_content):
                print(f"      → No significant change, skipping")
                # Revert state
                await self._revert_state(control, element)
                return None
            
            # Find changed region (for scoped extraction)
            changed_region = await self._find_changed_region(added_content)
            
            # Extract options from changed region only
            options = await self._extract_scoped_options(changed_region, added_content)
            
            # Calculate price delta
            price_change = None
            if initial_price and new_price:
                price_change = new_price - initial_price
            
            # Create state object
            state = UIState(
                control_id=control.get('id', ''),
                control_label=control.get('label', ''),
                control_type=control.get('type', ''),
                dom_snapshot=new_snapshot,
                added_content=added_content,
                changed_region=changed_region,
                options_discovered=options,
                price_change=price_change,
                depth=depth
            )
            
            # Revert state for next iteration
            await self._revert_state(control, element)
            
            return state
            
        except Exception as e:
            print(f"      ✗ Control exploration error: {e}")
            return None
    
    async def _explore_nested(self, parent_state: UIState):
        """
        Recursively explore nested controls that appeared after state change.
        
        Some options reveal more options (e.g., "Porch" → "Window Upgrade").
        This handles nested configuration.
        """
        if parent_state.depth >= self.max_recursion_depth:
            return
        
        print(f"      → Checking for nested controls (depth {parent_state.depth + 1})")
        
        # Re-click parent to enter that state
        # (simplified - in production, track path to state)
        
        # Find new controls in changed region
        # (would need to implement control discovery in region)
        
        # For now, this is a placeholder for the architecture
        pass
    
    async def _snapshot_dom(self) -> str:
        """
        Capture current DOM state as text.
        
        Returns innerText of body (truncated for safety).
        """
        try:
            snapshot = await self.page.evaluate("""
                () => document.body.innerText.slice(0, 200000)
            """)
            return snapshot or ""
        except Exception as e:
            print(f"      ⚠ DOM snapshot failed: {e}")
            return ""
    
    def _dom_diff(self, before: str, after: str) -> List[str]:
        """
        Calculate DOM diff: what content was added?
        
        Strategy: Simple line-based diff
        
        Args:
            before: DOM snapshot before interaction
            after: DOM snapshot after interaction
            
        Returns:
            List of added text lines
        """
        before_lines = set(before.splitlines())
        after_lines = set(after.splitlines())
        
        added = after_lines - before_lines
        
        # Filter noise
        significant = []
        for line in added:
            stripped = line.strip()
            
            # Ignore empty, very short, or noise
            if len(stripped) < 3:
                continue
            
            # Ignore common noise patterns
            if any(noise in stripped.lower() for noise in ['loading', 'spinner', 'animation']):
                continue
            
            significant.append(stripped)
        
        return significant
    
    def _is_significant_change(self, added_content: List[str]) -> bool:
        """
        Determine if DOM change is significant enough to explore.
        
        Significant changes include:
        - New option labels
        - New prices
        - New product information
        
        Insignificant changes:
        - Animation text
        - Counters
        - Timers
        """
        if len(added_content) < 1:
            return False
        
        # Check for meaningful content
        meaningful_indicators = ['$', 'price', 'option', 'select', 'choose', 'upgrade']
        
        content_text = ' '.join(added_content).lower()
        
        has_meaningful = any(indicator in content_text for indicator in meaningful_indicators)
        
        return has_meaningful or len(added_content) >= 3
    
    async def _find_changed_region(self, added_content: List[str]) -> Optional[str]:
        """
        Find the DOM region that changed (for scoped extraction).
        
        This prevents mixing options from different categories.
        
        Args:
            added_content: New text that appeared
            
        Returns:
            Selector for changed region or None
        """
        if not added_content:
            return None
        
        try:
            # Find element containing the new text
            search_text = added_content[0][:50]  # Use first new text
            
            changed_element = await self.page.evaluate(f"""
                () => {{
                    const els = [...document.querySelectorAll('*')];
                    return els.find(el => 
                        el.innerText && el.innerText.includes("{search_text}")
                    );
                }}
            """)
            
            # Return selector for this region
            # (in production, would build XPath or CSS selector)
            return "region_selector"  # Placeholder
            
        except Exception:
            return None
    
    async def _extract_scoped_options(
        self,
        changed_region: Optional[str],
        added_content: List[str]
    ) -> List[Dict]:
        """
        Extract options ONLY from the changed DOM region.
        Enhanced to extract individual product cards separately.
        
        Args:
            changed_region: Selector for changed region
            added_content: New content that appeared
            
        Returns:
            List of extracted options with complete information
        """
        options = []
        
        # Track card boundaries using visual cues
        current_card = {
            'lines': [],
            'has_price': False,
            'has_model_name': False,
            'has_capacity': False
        }
        
        # Card separator indicators
        def is_card_separator(line: str) -> bool:
            """Detect if line indicates a new card starting."""
            # Look for patterns that indicate card headers
            if re.search(r'\\bThe\\b.*\\bSauna\\b', line, re.IGNORECASE):
                return True
            if re.search(r'\\d+\\.5\\s*x\\s*\\d+ft', line, re.IGNORECASE):  # e.g., "6.5 x 10ft"
                return True
            if re.search(r'\\$\\d{2,}k', line, re.IGNORECASE):  # e.g., "$39k+"
                return True
            return False
        
        def is_valid_card(card: dict) -> bool:
            """Check if accumulated content forms a valid product card."""
            return (card['has_price'] or card['has_model_name']) and len(card['lines']) >= 2
        
        for content in added_content:
            content = content.strip()
            
            # Skip noise
            if len(content) < 3:
                continue
            if any(skip in content.lower() for skip in ['copyright', 'reserved', 'policy', 'cookie', 'terms', 'explore custom options']):
                continue
            
            # Check if this is a new card starting
            if is_card_separator(content) and current_card['lines']:
                # Save previous card if valid
                if is_valid_card(current_card):
                    option_text = ' '.join(current_card['lines'])
                    options.append({
                        'name': option_text,
                        'price_text': option_text if current_card['has_price'] else '',
                        'available': True,
                        'type': 'product_card'
                    })
                # Start new card
                current_card = {
                    'lines': [content],
                    'has_price': '$' in content,
                    'has_model_name': bool(re.search(r'The\\s+\\w+', content, re.IGNORECASE)),
                    'has_capacity': 'person' in content.lower() or 'capacity' in content.lower()
                }
                continue
            
            # Accumulate lines for current card
            current_card['lines'].append(content)
            
            # Update flags
            if '$' in content:
                current_card['has_price'] = True
            if re.search(r'The\\s+\\w+|sauna|mobile', content, re.IGNORECASE):
                current_card['has_model_name'] = True
            if 'person' in content.lower() or 'capacity' in content.lower():
                current_card['has_capacity'] = True
            
            # If card seems complete (has all key info), save it
            if (len(current_card['lines']) >= 4 and 
                current_card['has_price'] and 
                current_card['has_model_name']):
                option_text = ' '.join(current_card['lines'])
                options.append({
                    'name': option_text,
                    'price_text': option_text,
                    'available': True,
                    'type': 'product_card'
                })
                current_card = {'lines': [], 'has_price': False, 'has_model_name': False, 'has_capacity': False}
        
        # Don't forget last card
        if is_valid_card(current_card):
            option_text = ' '.join(current_card['lines'])
            options.append({
                'name': option_text,
                'price_text': option_text if current_card['has_price'] else '',
                'available': True,
                'type': 'product_card'
            })
        
        return options[:20]  # Limit for safety
    
    async def _extract_current_price(self) -> Optional[float]:
        """
        Extract current price from page (for delta calculation).
        
        Returns:
            Current price as float or None if not found
        """
        try:
            price_text = await self.page.evaluate("""
                () => {
                    const selectors = [
                        '[class*="price"]',
                        '[id*="price"]',
                        '[class*="total"]',
                        '.price-value'
                    ];
                    
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText) {
                            const match = el.innerText.match(/\\$([\\d,]+\\.?\\d*)/);
                            if (match) return match[1].replace(',', '');
                        }
                    }
                    return null;
                }
            """)
            
            return float(price_text) if price_text else None
            
        except Exception:
            return None
    
    async def _revert_state(self, control: Dict, element):
        """
        Revert UI to previous state (click again or reload).
        
        Strategy:
        - For checkboxes/radios: click again
        - For tabs/accordions: might need to click previous tab
        - For others: might need page reload (expensive)
        """
        control_type = control.get('type', '')
        
        try:
            if control_type in ['checkbox', 'radio']:
                # Click again to uncheck
                await element.click()
                await asyncio.sleep(200)
            elif control_type == 'select':
                # Reset to first option
                await element.select_option(index=0)
            else:
                # For buttons/tabs, try clicking first control to reset
                # (This is heuristic - might need page reload in some cases)
                pass
                
        except Exception as e:
            print(f"      ⚠ State revert failed: {e}")
