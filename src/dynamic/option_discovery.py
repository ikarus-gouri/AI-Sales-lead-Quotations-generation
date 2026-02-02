"""Discover interactive controls on dynamic configurator pages.

Refactored for state-aware exploration:
- Generic behavioral detection (not selector-based)
- Filters interactive elements by visibility and interactivity
- Ignores navigation/submission buttons
- Returns element handles for state exploration
"""

from typing import List, Dict, Any


# Negative keywords to exclude from control discovery (aggressive filtering)
IGNORE_KEYWORDS = [
    # Purchase/Cart
    'add to cart', 'buy now', 'checkout', 'submit', 'purchase',
    'add to bag', 'add to wishlist', 'share', 'print',
    # Navigation
    'next', 'previous', 'back', 'home', 'menu', 'search',
    'models', 'lifestyle', 'why newmar', 'owners', 'dealers',
    'navigation', 'toggle', 'hamburger',
    # Account
    'login', 'signup', 'sign in', 'sign up', 'register',
    'account', 'profile', 'my account',
    # Generic pages
    'about', 'contact', 'blog', 'news', 'resources', 'projects',
    'gallery', 'videos', 'photos',
    # Social
    'facebook', 'twitter', 'instagram', 'linkedin', 'youtube',
    'share', 'follow',
    # Legal
    'privacy', 'terms', 'cookie', 'gdpr', 'accept cookies',
    'skip to content', 'accessibility',
    # Misc site chrome
    'store', 'shop all', 'view all', 'learn more', 'read more',
    'health benefits', 'stories', 'testimonials',
    'open mobile sauna', 'open resources', 'open projects',
    'cart', 'specifications', 'warranty', 'support',
    # Header/Footer indicators
    'header', 'footer', 'nav', 'sidebar'
]

# Configurator-specific patterns (prioritize these)
CONFIGURATOR_PATTERNS = [
    'option', 'select', 'choose', 'add', 'remove', 'customize',
    'size', 'color', 'material', 'upgrade', 'feature',
    'price', 'quote', 'configure', 'build', 'design',
    'card', 'product', 'variant'
]


class OptionDiscovery:
    """
    Find and classify interactive controls using behavioral signals.
    
    Strategy: Detect controls by behavior, not hardcoded selectors.
    Scoped to configurator container to avoid navigation elements.
    
    Discovers:
    - Standard inputs (radio, checkbox, select)
    - Buttons with click handlers
    - Custom controls (React/Vue components)
    - ARIA-controlled elements
    """
    
    def __init__(self, page: Any):
        self.page = page
        self.configurator_root = None
    
    async def _find_configurator_root(self):
        """Find the configurator container to scope control discovery."""
        # Try common configurator root patterns
        root_selectors = [
            'main',
            '[id*="configurator"]',
            '[class*="configurator"]',
            '[data-component*="config"]',
            '[id*="builder"]',
            '[class*="builder"]',
            '[id*="calculator"]',
            '[class*="calculator"]',
            'iframe',
            '#root',  # SPA apps
            '[data-app]'
        ]
        
        for selector in root_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    is_visible = await element.is_visible()
                    if is_visible:
                        print(f"    ✓ Configurator root: {selector}")
                        return element
            except Exception:
                continue
        
        print("    ⚠ No configurator root found, using full page")
        return None
    
    async def find_interactive_controls(self) -> List[Dict]:
        """
        Discover all interactive controls using behavioral signals.
        Prioritizes configurator-specific elements over navigation.
        Scoped to configurator container when possible.
        
        Returns list of control dictionaries with:
        - id: Unique identifier
        - type: Control type
        - label: User-visible text
        - element: Playwright element handle (for clicking)
        - group: Optional grouping
        - priority: Lower is higher priority
        """
        # Find configurator root first
        self.configurator_root = await self._find_configurator_root()
        
        controls = []
        
        # PRIORITY 1: Configurator-specific cards/buttons
        controls.extend(await self._find_configurator_elements())
        
        # PRIORITY 2: Generic behavioral signals
        controls.extend(await self._find_by_selectors())
        controls.extend(await self._find_clickable_elements())
        
        # Filter by interactivity
        controls = await self._filter_interactive(controls)
        
        # Remove ignored controls
        controls = self._filter_ignored(controls)
        
        # Deduplicate
        controls = self._deduplicate_controls(controls)
        
        # Sort by priority
        controls.sort(key=lambda c: c.get('priority', 50))
        
        print(f"    [DISCOVERY] Found {len(controls)} interactive controls")
        
        return controls
    
    async def _find_configurator_elements(self) -> List[Dict]:
        """Find configurator-specific elements (highest priority)."""
        CONFIGURATOR_SELECTORS = [
            # Product/option cards
            '.product-card', '.option-card', '.configurator-option',
            '[class*="product"][class*="card"]', '[class*="option"][class*="card"]',
            '[data-product]', '[data-option]', '[data-variant]',
            # Interactive options
            '.swatch', '.variant-option', '.product-option',
            '[role="radio"]', '[role="checkbox"]',
            # Buttons with configurator keywords
            'button[class*="add"]', 'button[class*="select"]',
            'button[class*="choose"]', 'button[class*="option"]',
            # Card-like structures
            '.customize-option', '.build-option', '.selection-card',
            'div[onclick][class*="card"]', 'div[onclick][class*="option"]'
        ]
        
        controls = []
        
        # Use scoped search if configurator root found
        search_context = self.configurator_root if self.configurator_root else self.page
        
        for selector in CONFIGURATOR_SELECTORS:
            try:
                elements = await search_context.query_selector_all(selector)
                for idx, elem in enumerate(elements):
                    label = await self._get_element_text(elem)
                    elem_type = await self._determine_type(elem)
                    
                    controls.append({
                        'id': f'{elem_type}_{idx}_{hash(label) % 10000}',
                        'type': elem_type,
                        'label': label or f'{elem_type} {idx}',
                        'element': elem,
                        'group': None,
                        'priority': 10  # Highest priority
                    })
            except Exception:
                continue
        
        return controls
    
    async def _find_by_selectors(self) -> List[Dict]:
        """Find controls using generic behavioral selectors."""
        CONTROL_SELECTORS = [
            "button:not([disabled])",
            "[role='button']:not([disabled])",
            "input[type=radio]:not([disabled])",
            "input[type=checkbox]:not([disabled])",
            "select:not([disabled])",
            "[onclick]:not([disabled])",
            "[aria-expanded]",
            "[tabindex='0']"
        ]
        
        controls = []
        
        # Use scoped search if configurator root found
        search_context = self.configurator_root if self.configurator_root else self.page
        
        for selector in CONTROL_SELECTORS:
            try:
                elements = await search_context.query_selector_all(selector)
                
                for idx, element in enumerate(elements):
                    try:
                        # Get label/text
                        text = await self._get_element_text(element)
                        
                        # Determine type
                        tag = await element.evaluate("el => el.tagName.toLowerCase()")
                        input_type = await element.get_attribute("type") or ""
                        
                        control_type = self._determine_type(tag, input_type)
                        
                        controls.append({
                            'id': f"{control_type}_{idx}_{hash(text) % 10000}",
                            'type': control_type,
                            'label': text[:100],
                            'element': element,
                            'group': None,
                            'priority': 30  # Medium priority
                        })
                    except Exception:
                        continue
                        
            except Exception:
                continue
        
        return controls
    
    async def _find_clickable_elements(self) -> List[Dict]:
        """Find custom clickable elements (React/Vue components)."""
        controls = []
        
        try:
            # Find elements with pointer cursor (behavioral signal)
            elements = await self.page.evaluate("""
                () => {
                    const all = [...document.querySelectorAll('*')];
                    return all
                        .filter(el => {
                            const style = getComputedStyle(el);
                            return style.cursor === 'pointer' && 
                                   el.offsetWidth > 0 && 
                                   el.offsetHeight > 0;
                        })
                        .slice(0, 50)  // Limit for performance
                        .map((el, idx) => ({
                            index: idx,
                            text: el.innerText?.slice(0, 100) || '',
                            tagName: el.tagName
                        }));
                }
            """)
            
            for item in elements:
                if item['text'].strip():
                    # Get actual element handle
                    element = await self.page.evaluate_handle(
                        f"() => [...document.querySelectorAll('*')].filter(el => getComputedStyle(el).cursor === 'pointer')[{item['index']}]"
                    )
                    
                    controls.append({
                        'id': f"clickable_{item['index']}",
                        'type': 'custom',
                        'label': item['text'][:100],
                        'element': element.as_element(),
                        'group': None,
                        'priority': 50  # Lower priority
                    })
                    
        except Exception as e:
            print(f"    ⚠ Clickable element discovery error: {e}")
        
        return controls
    
    async def _filter_interactive(self, controls: List[Dict]) -> List[Dict]:
        """Filter controls by interactivity (visible, enabled, interactive)."""
        filtered = []
        
        for control in controls:
            try:
                element = control['element']
                
                # Check if visible
                is_visible = await element.is_visible()
                if not is_visible:
                    continue
                
                # Check if has bounding box (rendered)
                bbox = await element.bounding_box()
                if not bbox:
                    continue
                
                # Check if actually interactive (cursor: pointer or is input)
                is_interactive = await element.evaluate("""
                    el => {
                        const style = getComputedStyle(el);
                        const tag = el.tagName.toLowerCase();
                        return style.cursor === 'pointer' || 
                               ['button', 'input', 'select'].includes(tag) ||
                               el.onclick !== null;
                    }
                """)
                
                if is_interactive:
                    filtered.append(control)
                    
            except Exception:
                continue
        
        return filtered
    
    def _filter_ignored(self, controls: List[Dict]) -> List[Dict]:
        """Remove navigation/submission buttons using negative keywords."""
        filtered = []
        
        for control in controls:
            label_lower = control['label'].lower()
            
            # Check against ignore keywords
            if any(keyword in label_lower for keyword in IGNORE_KEYWORDS):
                continue
            
            filtered.append(control)
        
        return filtered
    
    async def _get_element_text(self, element) -> str:
        """Extract meaningful text from element."""
        try:
            # Try aria-label first
            aria_label = await element.get_attribute("aria-label")
            if aria_label:
                return aria_label.strip()
            
            # Try innerText
            text = await element.inner_text()
            if text:
                return text.strip()
            
            # Try value attribute
            value = await element.get_attribute("value")
            if value:
                return value.strip()
            
            return "Unknown"
            
        except Exception:
            return "Unknown"
    
    def _determine_type(self, tag: str, input_type: str) -> str:
        """Determine control type from tag and attributes."""
        if tag == "input":
            if input_type == "radio":
                return "radio"
            elif input_type == "checkbox":
                return "checkbox"
            else:
                return "input"
        elif tag == "select":
            return "select"
        elif tag == "button":
            return "button"
        else:
            return "custom"
    
    def _deduplicate_controls(self, controls: List[Dict]) -> List[Dict]:
        """Remove duplicate controls based on label similarity."""
        seen_labels = set()
        unique = []
        
        for control in controls:
            label_key = control['label'].lower().strip()[:50]
            
            if label_key not in seen_labels:
                seen_labels.add(label_key)
                unique.append(control)
        
        return unique
