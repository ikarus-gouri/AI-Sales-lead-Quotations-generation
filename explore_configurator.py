"""
Generalized configurator explorer that:
1. Identifies all cards/options on the page
2. Clicks each one and detects changes
3. Discovers new cards, buttons, or navigation elements
4. Recursively explores all paths
5. Builds a graph of option relationships
"""

import asyncio
import json
import hashlib
from datetime import datetime
from playwright.async_api import async_playwright
from collections import defaultdict

class ConfiguratorExplorer:
    def __init__(self, url, headless=False):
        self.url = url
        self.headless = headless
        self.visited_states = set()
        self.option_graph = {
            'nodes': [],  # Each option/card
            'edges': [],  # Connections: option A -> leads to -> option B
            'states': []  # UI states discovered
        }
        self.state_history = []
        
    def _hash_state(self, elements):
        """Create unique hash for a UI state"""
        state_str = json.dumps(sorted(elements), sort_keys=True)
        return hashlib.md5(state_str.encode()).hexdigest()[:8]
    
    async def _kill_overlays(self, page):
        """Remove overlays and popups that block interaction"""
        await page.evaluate("""
            () => {
                // Kill by common ID patterns
                const overlayPatterns = ['overlay', 'modal', 'popup', 'backdrop', 'calc-overlay'];
                overlayPatterns.forEach(pattern => {
                    document.querySelectorAll(`[id*="${pattern}"], [class*="${pattern}"]`).forEach(el => {
                        const style = window.getComputedStyle(el);
                        if (style.position === 'fixed' || style.position === 'absolute') {
                            if (style.zIndex > 100 || el.offsetHeight > window.innerHeight * 0.5) {
                                el.remove();
                            }
                        }
                    });
                });
                
                // Kill high z-index fixed/absolute elements
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    if ((style.position === 'fixed' || style.position === 'absolute') && 
                        parseInt(style.zIndex) > 999) {
                        el.remove();
                    }
                });
                
                // Kill common banner patterns
                ['cookie', 'gdpr', 'consent', 'privacy', 'notice'].forEach(pattern => {
                    document.querySelectorAll(`[class*="${pattern}"], [id*="${pattern}"]`).forEach(el => {
                        if (el.offsetParent !== null) el.remove();
                    });
                });
            }
        """)
    
    async def _find_configurator_root(self, page):
        """Find the main configurator container"""
        root = await page.evaluate("""
            () => {
                const patterns = [
                    'main', '#main', '[role="main"]',
                    '#configurator', '#builder', '#calculator', '#customizer',
                    '[class*="configurator"]', '[class*="builder"]', '[class*="calculator"]',
                    '[data-app]', '[data-component*="config"]'
                ];
                
                for (const pattern of patterns) {
                    const el = document.querySelector(pattern);
                    if (el && el.offsetParent !== null) {
                        return pattern;
                    }
                }
                return 'body';
            }
        """)
        return root
    
    async def _capture_options(self, page, container_selector='body'):
        """Capture all interactive options/cards on current page"""
        options = await page.evaluate(f"""
            () => {{
                const options = [];
                const container = document.querySelector('{container_selector}');
                if (!container) return options;
                
                // Auto-detect clickable cards/items
                const clickableElements = [];
                
                // Strategy 1: Find elements with data attributes (common in configurators)
                container.querySelectorAll('[data-id], [data-option], [data-product], [data-item], [data-value]').forEach(el => {{
                    if (el.offsetParent !== null && el.innerText.trim()) {{
                        clickableElements.push({{
                            element: el,
                            type: 'data-card',
                            score: 10
                        }});
                    }}
                }});
                
                // Strategy 2: Find clickable divs with meaningful content
                container.querySelectorAll('div[class], article[class], li[class]').forEach(el => {{
                    if (el.offsetParent === null || !el.innerText.trim()) return;
                    
                    const classes = el.className.toLowerCase();
                    const score = 
                        (classes.includes('card') ? 5 : 0) +
                        (classes.includes('option') ? 5 : 0) +
                        (classes.includes('product') ? 5 : 0) +
                        (classes.includes('item') ? 3 : 0) +
                        (classes.includes('choice') ? 4 : 0) +
                        (el.onclick || el.getAttribute('onclick') ? 3 : 0) +
                        (el.style.cursor === 'pointer' ? 2 : 0);
                    
                    if (score > 3) {{
                        clickableElements.push({{
                            element: el,
                            type: 'inferred-card',
                            score: score
                        }});
                    }}
                }});
                
                // Strategy 3: Find buttons and links
                container.querySelectorAll('button, a[role="button"], [role="tab"]').forEach(el => {{
                    if (el.offsetParent !== null && el.innerText.trim()) {{
                        clickableElements.push({{
                            element: el,
                            type: 'button',
                            score: 8
                        }});
                    }}
                }});
                
                // Strategy 4: Find select dropdowns
                container.querySelectorAll('select').forEach(select => {{
                    if (select.offsetParent !== null) {{
                        Array.from(select.options).forEach((option, idx) => {{
                            if (option.value && option.text.trim()) {{
                                clickableElements.push({{
                                    element: option,
                                    parentElement: select,
                                    type: 'select-option',
                                    score: 7
                                }});
                            }}
                        }});
                    }}
                }});
                
                // Strategy 5: Find radio buttons and checkboxes
                container.querySelectorAll('input[type="radio"], input[type="checkbox"]').forEach(input => {{
                    if (input.offsetParent !== null || (input.parentElement && input.parentElement.offsetParent !== null)) {{
                        clickableElements.push({{
                            element: input,
                            type: input.type === 'radio' ? 'radio' : 'checkbox',
                            score: 6
                        }});
                    }}
                }});
                
                // Deduplicate and sort by score
                const seen = new Set();
                clickableElements
                    .sort((a, b) => b.score - a.score)
                    .forEach((item, idx) => {{
                        const el = item.element;
                        const text = el.innerText.trim().substring(0, 100);
                        const key = text + el.tagName;
                        
                        if (!seen.has(key)) {{
                            seen.add(key);
                            const optionData = {{
                                type: item.type,
                                selector: el.tagName.toLowerCase(),
                                index: idx,
                                text: text,
                                id: el.id || el.getAttribute('data-id') || el.getAttribute('data-option') || el.getAttribute('data-product'),
                                className: el.className,
                                tagName: el.tagName,
                                attributes: {{
                                    dataId: el.getAttribute('data-id'),
                                    dataOption: el.getAttribute('data-option'),
                                    dataProduct: el.getAttribute('data-product'),
                                    dataValue: el.getAttribute('data-value'),
                                    role: el.getAttribute('role'),
                                    value: el.value,
                                    name: el.name,
                                    checked: el.checked
                                }}
                            }};
                            
                            // For select options, store parent info
                            if (item.type === 'select-option' && item.parentElement) {{
                                optionData.parentId = item.parentElement.id;
                                optionData.parentName = item.parentElement.name;
                            }}
                            
                            options.push(optionData);
                        }}
                    }});
                
                return options;
            }}
        """)
        
        return options
    
    async def _click_option(self, page, option):
        """Click an option and wait for changes"""
        try:
            # Handle select options
            if option['type'] == 'select-option':
                if option.get('parentId'):
                    select_selector = f"select#{option['parentId']}"
                elif option.get('parentName'):
                    select_selector = f"select[name='{option['parentName']}']"
                else:
                    return False
                
                select = await page.query_selector(select_selector)
                if select:
                    await select.select_option(value=option['attributes'].get('value'))
                    return True
                return False
            
            # Handle radio buttons and checkboxes
            if option['type'] in ['radio', 'checkbox']:
                if option['id']:
                    selector = f"input#{option['id']}"
                elif option['attributes'].get('name'):
                    selector = f"input[name='{option['attributes']['name']}'][value='{option['attributes'].get('value', '')}']"
                else:
                    return False
                
                element = await page.query_selector(selector)
                if element:
                    is_checked = await element.is_checked()
                    if not is_checked:  # Only click if not already checked/selected
                        await element.check()
                        return True
                    return False
                return False
            
            # Build selector for this specific option
            selector = None
            
            # Try ID first
            if option['id']:
                if option['attributes'].get('dataId'):
                    selector = f"[data-id='{option['attributes']['dataId']}']"  
                elif option['attributes'].get('dataOption'):
                    selector = f"[data-option='{option['attributes']['dataOption']}']"  
                elif option['attributes'].get('dataProduct'):
                    selector = f"[data-product='{option['attributes']['dataProduct']}']"  
                else:
                    selector = f"#{option['id']}"
            
            # Try by class and text
            if not selector and option.get('className'):
                selector = f"{option['tagName'].lower()}.{option['className'].split()[0]}"
            
            # Try to find by selector
            if selector:
                elements = await page.query_selector_all(selector)
                if elements:
                    # Find matching by text
                    for el in elements:
                        text = await el.inner_text()
                        if text.strip().startswith(option['text'][:30]):
                            await el.scroll_into_view_if_needed()
                            await el.click(timeout=5000)
                            return True
            
            # Fallback: find by text content
            all_elements = await page.query_selector_all(f"{option['tagName'].lower()}")
            for el in all_elements:
                text = await el.inner_text()
                if text.strip().startswith(option['text'][:30]):
                    is_visible = await el.is_visible()
                    if is_visible:
                        await el.scroll_into_view_if_needed()
                        await el.click(timeout=5000)
                        return True
            
            return False
            
        except Exception as e:
            print(f"    ✗ Click failed: {e}")
            return False
    
    async def _detect_changes(self, before_options, after_options):
        """Detect what changed after clicking"""
        before_texts = set(opt['text'] for opt in before_options)
        after_texts = set(opt['text'] for opt in after_options)
        
        new_options = [opt for opt in after_options if opt['text'] not in before_texts]
        removed_options = [opt for opt in before_options if opt['text'] not in after_texts]
        
        return {
            'new_options': new_options,
            'removed_options': removed_options,
            'new_count': len(new_options),
            'removed_count': len(removed_options)
        }
    
    async def explore_state(self, page, depth=0, max_depth=5, parent_state=None, container='body'):
        """Recursively explore configurator by clicking options"""
        
        if depth > max_depth:
            print(f"{'  ' * depth}⚠ Max depth reached")
            return
        
        # Capture current state
        current_options = await self._capture_options(page, container)
        state_hash = self._hash_state([opt['text'] for opt in current_options])
        
        # Check if we've seen this state
        if state_hash in self.visited_states:
            print(f"{'  ' * depth}↻ Already visited state {state_hash}")
            return
        
        self.visited_states.add(state_hash)
        
        # Record this state
        state_record = {
            'id': state_hash,
            'depth': depth,
            'parent': parent_state,
            'options_count': len(current_options),
            'timestamp': datetime.now().isoformat()
        }
        self.option_graph['states'].append(state_record)
        
        print(f"{'  ' * depth}📍 State {state_hash} | Depth {depth} | Options: {len(current_options)}")
        
        # Explore each option
        for i, option in enumerate(current_options):
            print(f"{'  ' * depth}  [{i+1}/{len(current_options)}] Exploring: {option['text'][:60]}")
            
            # Record this option as a node
            node_id = f"{state_hash}_{i}"
            self.option_graph['nodes'].append({
                'id': node_id,
                'state': state_hash,
                'type': option['type'],
                'text': option['text'],
                'option_id': option.get('id'),
                'attributes': option.get('attributes', {})
            })
            
            # Capture state before click
            before_options = await self._capture_options(page)
            
            # Click the option
            click_success = await self._click_option(page, option)
            
            if not click_success:
                print(f"{'  ' * depth}    ✗ Could not click")
                continue
            
            # Wait for changes
            await asyncio.sleep(2)
            
            # Capture state after click
            after_options = await self._capture_options(page)
            
            # Detect changes
            changes = await self._detect_changes(before_options, after_options)
            
            if changes['new_count'] > 0:
                print(f"{'  ' * depth}    ✓ {changes['new_count']} new options appeared")
                
                # Record edge
                new_state_hash = self._hash_state([opt['text'] for opt in after_options])
                self.option_graph['edges'].append({
                    'from': node_id,
                    'from_state': state_hash,
                    'to_state': new_state_hash,
                    'new_options': changes['new_count'],
                    'removed_options': changes['removed_count']
                })
                
                # Recursively explore new state
                await self.explore_state(page, depth + 1, max_depth, state_hash, container)
                
                # Navigate back if possible
                try:
                    await page.go_back(wait_until='domcontentloaded', timeout=5000)
                    await asyncio.sleep(1)
                    await self._kill_overlays(page)
                except:
                    # If can't go back, reload from start
                    print(f"{'  ' * depth}    ↶ Reloading from start")
                    await page.goto(self.url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(2)
                    await self._kill_overlays(page)
                    return  # Exit this exploration branch
            else:
                print(f"{'  ' * depth}    → No significant changes")
    
    async def run(self, max_depth=5):
        """Run the exploration"""
        print("=" * 80)
        print("CONFIGURATOR EXPLORER")
        print("=" * 80)
        print(f"URL: {self.url}")
        print(f"Max depth: {max_depth}")
        print()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = await context.new_page()
            
            try:
                # Navigate to page
                print("✓ Loading page...")
                await page.goto(self.url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(3)
                
                # Kill overlays
                print("✓ Removing overlays...")
                await self._kill_overlays(page)
                await asyncio.sleep(1)
                
                # Find configurator container
                print("✓ Finding configurator container...")
                container = await self._find_configurator_root(page)
                print(f"  Using container: {container}")
                
                # Start exploration
                print("\n" + "=" * 80)
                print("STARTING EXPLORATION")
                print("=" * 80 + "\n")
                
                await self.explore_state(page, depth=0, max_depth=max_depth, container=container)
                
                # Keep browser open briefly to observe
                print("\n✓ Exploration complete. Keeping browser open for 3 seconds...")
                await asyncio.sleep(3)
                
            except Exception as e:
                print(f"\n✗ Error during exploration: {e}")
                import traceback
                traceback.print_exc()
            
            finally:
                await browser.close()
        
        # Generate report
        self._generate_report()
    
    def _generate_report(self):
        """Generate exploration report"""
        print("\n" + "=" * 80)
        print("EXPLORATION REPORT")
        print("=" * 80)
        
        print(f"\n📊 STATISTICS:")
        print(f"  States discovered: {len(self.option_graph['states'])}")
        print(f"  Options found: {len(self.option_graph['nodes'])}")
        print(f"  Connections: {len(self.option_graph['edges'])}")
        
        print(f"\n📍 STATES:")
        for state in self.option_graph['states']:
            parent_str = f" (parent: {state['parent']})" if state['parent'] else " (root)"
            print(f"  {state['id']}: Depth {state['depth']}, {state['options_count']} options{parent_str}")
        
        print(f"\n🔗 CONNECTIONS:")
        for edge in self.option_graph['edges']:
            print(f"  {edge['from_state']} → {edge['to_state']}: +{edge['new_options']} options")
        
        print(f"\n🎯 UNIQUE OPTIONS:")
        unique_texts = set()
        for node in self.option_graph['nodes']:
            unique_texts.add(node['text'][:60])
        
        for i, text in enumerate(sorted(unique_texts)[:20], 1):
            print(f"  {i}. {text}")
        
        if len(unique_texts) > 20:
            print(f"  ... and {len(unique_texts) - 20} more")
        
        # Save graph to file
        output_file = f"configurator_graph_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.option_graph, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Graph saved to: {output_file}")
        print("\n" + "=" * 80)


async def main():
    """Main entry point"""
    import sys
    
    # Parse arguments
    url = None
    headless = False
    max_depth = 3
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--headless':
            headless = True
        elif args[i] == '--depth':
            max_depth = int(args[i + 1])
            i += 1
        elif not url:
            url = args[i]
        i += 1
    
    # Prompt for URL if not provided
    if not url:
        url = input("Enter configurator URL: ").strip()
        if not url:
            url = "https://bwsaunaco.com/custom-sauna-quote-tool/"
            print(f"Using default: {url}")
    
    # Run explorer
    explorer = ConfiguratorExplorer(url, headless=headless)
    await explorer.run(max_depth=max_depth)


if __name__ == "__main__":
    asyncio.run(main())
