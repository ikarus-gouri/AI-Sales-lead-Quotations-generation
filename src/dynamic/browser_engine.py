"""Browser automation engine for dynamic configurators (Model-D)."""

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class BrowserConfig:
    """Configuration for browser execution."""
    headless: bool = True
    timeout: int = 30000  # ms
    wait_after_action: int = 1000  # ms
    viewport: Dict = field(default_factory=lambda: {'width': 1280, 'height': 720})
    user_agent: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


class PlaywrightEngine:
    """
    Browser automation using Playwright.
    
    Handles page loading, interaction, and cleanup.
    """
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    async def initialize(self) -> bool:
        """Initialize browser instance."""
        try:
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.headless
            )
            
            self.context = await self.browser.new_context(
                viewport=self.config.viewport,
                user_agent=self.config.user_agent
            )
            
            print("✓ Browser initialized (Model-D)")
            return True
            
        except ImportError:
            print("✗ Playwright not installed. Run: pip install playwright && playwright install chromium")
            return False
        except Exception as e:
            print(f"✗ Browser initialization failed: {e}")
            return False
    
    async def create_page(self) -> Any:
        """Create new page instance."""
        if not self.context:
            await self.initialize()
        
        self.page = await self.context.new_page()
        self.page.set_default_timeout(self.config.timeout)
        
        return self.page
    
    async def goto(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """
        Navigate to URL.
        
        Args:
            url: Target URL
            wait_until: When to consider navigation successful
                - "domcontentloaded": Fast, waits for DOM to be ready (recommended for most cases)
                - "load": Waits for page load event
                - "networkidle": Waits for no network activity (may timeout on some pages)
        """
        try:
            await self.page.goto(url, wait_until=wait_until, timeout=self.config.timeout)
            print(f"  ✓ Loaded: {url}")
            return True
        except Exception as e:
            print(f"  ✗ Failed to load {url}: {e}")
            return False
    
    async def wait_for_selector(self, selector: str, timeout: int = None) -> bool:
        """Wait for element to appear."""
        try:
            await self.page.wait_for_selector(
                selector,
                timeout=timeout or self.config.timeout
            )
            return True
        except Exception:
            return False
    
    async def screenshot(self, path: str = "screenshot.png") -> bool:
        """Take screenshot for debugging."""
        try:
            await self.page.screenshot(path=path)
            print(f"  📸 Screenshot: {path}")
            return True
        except Exception as e:
            print(f"  ✗ Screenshot failed: {e}")
            return False
    
    async def cleanup(self):
        """Close browser and cleanup."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            print("✓ Browser cleanup complete")
        except Exception as e:
            print(f"⚠ Cleanup warning: {e}")
    
    async def _prepare_page(self, page) -> None:
        """Prepare page for exploration: kill overlays, detect configurator root."""
        try:
            # Kill overlays and interception layers
            await page.evaluate("""
                () => {
                    // Kill common overlay patterns
                    const overlayIds = ['bws-calc-overlay', 'overlay', 'modal-backdrop'];
                    overlayIds.forEach(id => {
                        const el = document.getElementById(id);
                        if (el) {
                            el.style.pointerEvents = 'none';
                            el.style.display = 'none';
                        }
                    });
                    
                    // Kill aria-hidden overlays
                    document.querySelectorAll('[aria-hidden=\"true\"]').forEach(el => {
                        if (el.style.position === 'fixed' || el.style.position === 'absolute') {
                            el.style.pointerEvents = 'none';
                        }
                    });
                    
                    // Kill cookie banners
                    const cookieSelectors = ['[class*=\"cookie\"]', '[id*=\"cookie\"]', '[class*=\"gdpr\"]'];
                    cookieSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            if (el.offsetHeight > 50) {  // Only large overlays
                                el.style.display = 'none';
                            }
                        });
                    });
                }
            """)
            print("    ✓ Overlays neutralized")
            
            # Detect SPA/AEM patterns
            is_spa = await page.evaluate("""
                () => {
                    const indicators = [
                        document.querySelector('[data-react-root]'),
                        document.querySelector('[data-reactroot]'),
                        document.querySelector('#root'),
                        document.querySelector('[ng-app]'),
                        document.querySelector('[data-vue-app]'),
                        window.__NEXT_DATA__,
                        window.__NUXT__
                    ];
                    return indicators.some(x => x);
                }
            """)
            
            if is_spa:
                print("    ⚠ SPA detected - UI exploration may be limited")
            
        except Exception as e:
            print(f"    ⚠ Page preparation warning: {e}")


class BrowserRunner:
    """
    High-level orchestrator for dynamic extraction.
    
    Coordinates: loading → discovery → capture → learning
    """
    
    def __init__(self, config: BrowserConfig = None):
        self.config = config or BrowserConfig()
        self.engine = PlaywrightEngine(config)
        self.network_responses = []
    
    async def _prepare_page(self, page) -> None:
        """Prepare page for exploration: kill overlays, detect configurator root."""
        try:
            # Kill overlays and interception layers
            await page.evaluate("""
                () => {
                    // Kill common overlay patterns
                    const overlayIds = ['bws-calc-overlay', 'overlay', 'modal-backdrop'];
                    overlayIds.forEach(id => {
                        const el = document.getElementById(id);
                        if (el) {
                            el.style.pointerEvents = 'none';
                            el.style.display = 'none';
                        }
                    });
                    
                    // Kill aria-hidden overlays
                    document.querySelectorAll('[aria-hidden="true"]').forEach(el => {
                        if (el.style.position === 'fixed' || el.style.position === 'absolute') {
                            el.style.pointerEvents = 'none';
                        }
                    });
                    
                    // Kill cookie banners
                    const cookieSelectors = ['[class*="cookie"]', '[id*="cookie"]', '[class*="gdpr"]'];
                    cookieSelectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            if (el.offsetHeight > 50) {  // Only large overlays
                                el.style.display = 'none';
                            }
                        });
                    });
                }
            """)
            print("    ✓ Overlays neutralized")
            
            # Detect SPA/AEM patterns
            is_spa = await page.evaluate("""
                () => {
                    const indicators = [
                        document.querySelector('[data-react-root]'),
                        document.querySelector('[data-reactroot]'),
                        document.querySelector('#root'),
                        document.querySelector('[ng-app]'),
                        document.querySelector('[data-vue-app]'),
                        window.__NEXT_DATA__,
                        window.__NUXT__
                    ];
                    return indicators.some(x => x);
                }
            """)
            
            if is_spa:
                print("    ⚠ SPA detected - UI exploration may be limited")
            
        except Exception as e:
            print(f"    ⚠ Page preparation warning: {e}")
    
    async def extract_dynamic_configurator(
        self,
        url: str,
        save_screenshot: bool = False
    ) -> Dict:
        """
        Main extraction for dynamic configurators using state exploration.
        
        Returns pricing model and discovered options.
        """
        result = {
            'success': False,
            'url': url,
            'extraction_method': 'dynamic_browser',
            'model': 'D',
            'pricing_model': {'base_price': None, 'option_deltas': {}, 'confidence': 0.0},
            'options_discovered': [],
            'states_discovered': [],
            'network_activity': [],
            'error': None
        }
        
        try:
            # Initialize browser
            if not await self.engine.initialize():
                result['error'] = 'Browser initialization failed'
                return result
            
            # Create page
            page = await self.engine.create_page()
            
            # Attach network listener
            self._attach_network_listener(page)
            
            # Load page
            if not await self.engine.goto(url):
                result['error'] = 'Page load failed'
                return result
            
            # Wait for dynamic content + JS listeners to attach
            await asyncio.sleep(1.5)
            
            if save_screenshot:
                await self.engine.screenshot(f"debug_dynamic_{url.split('/')[-1]}.png")
            
            print(f"  [MODEL-D] Starting UI state exploration")
            
            # Step 0: Prepare page (kill overlays, find configurator root)
            print(f"  [PREP] Preparing page for exploration...")
            await self._prepare_page(page)
            
            # Step 1: Discover interactive controls (scoped to configurator)
            print(f"  [CONTROLS] Finding interactive elements...")
            from .option_discovery import OptionDiscovery
            discovery = OptionDiscovery(page)
            controls = await discovery.find_interactive_controls()
            
            print(f"  [CONTROLS] Found {len(controls)} interactive elements")
            
            # Step 2: Explore UI states
            from .interaction_explorer import InteractionExplorer
            explorer = InteractionExplorer(page, self.config)
            states = await explorer.explore(controls)
            
            print(f"  [STATES] Discovered {len(states)} distinct states")
            
            # Step 3: Aggregate options from all states
            all_options = []
            for state in states:
                for option in state.options_discovered:
                    all_options.append({
                        'type': state.control_type,
                        'label': option['name'],
                        'category': state.control_label,
                        'price_text': option.get('price_text'),
                        'price_delta': state.price_change,
                        'available': option.get('available', True)
                    })
            
            result['options_discovered'] = all_options
            result['states_discovered'] = [
                {
                    'control': state.control_label,
                    'options_count': len(state.options_discovered),
                    'price_change': state.price_change
                }
                for state in states
            ]
            
            # Step 4: Build pricing model (from states)
            pricing_model = {
                'base_price': None,
                'price_type': 'dynamic_exploration',
                'option_deltas': {},
                'confidence': len(states) / max(len(controls), 1)
            }
            
            # Extract base price (first state or from DOM)
            if states and states[0].price_change is not None:
                # Attempt to calculate base from first delta
                pass
            
            # Map option → price delta
            for state in states:
                if state.price_change:
                    pricing_model['option_deltas'][state.control_label] = state.price_change
            
            result['pricing_model'] = pricing_model
            result['success'] = True
            
            # Capture network activity summary
            result['network_activity'] = [
                {
                    'url': r['url'],
                    'method': r['method'],
                    'status': r['status']
                }
                for r in self.network_responses[:10]
            ]
            
            print(f"  ✓ Model-D state exploration complete")
            print(f"    States explored: {len(states)}")
            print(f"    Options discovered: {len(all_options)}")
            print(f"    Price deltas learned: {len(pricing_model['option_deltas'])}")
            
        except Exception as e:
            result['error'] = str(e)
            print(f"  ✗ Model-D extraction failed: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await self.engine.cleanup()
        
        return result
    
    def _attach_network_listener(self, page):
        """Attach network response listener."""
        async def handle_response(response):
            try:
                self.network_responses.append({
                    'url': response.url,
                    'method': response.request.method,
                    'status': response.status,
                    'content_type': response.headers.get('content-type', '')
                })
            except Exception:
                pass
        
        page.on("response", handle_response)