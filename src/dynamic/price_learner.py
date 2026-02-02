"""Learn pricing model by toggling options and observing price changes."""

import asyncio
import re
from typing import List, Dict, Optional


class PriceLearner:
    """
    Learn pricing model for dynamic configurators.
    
    Algorithm:
    1. Capture base price
    2. For each option:
       - Reset to base state
       - Toggle option
       - Wait for price update
       - Calculate delta
    3. Build pricing model
    """
    
    def __init__(self, page, config):
        self.page = page
        self.config = config
        self.price_selectors = [
            '[class*="price"]',
            '[id*="price"]',
            '[class*="total"]',
            '[id*="total"]',
            '[data-price]',
            '.product-price',
            '#product-price',
            '.price-value',
            '.total-price'
        ]
    
    async def learn_pricing_model(self, controls: List[Dict]) -> Dict:
        """
        Learn pricing model from interactive controls.
        
        Returns:
        {
            'base_price': float,
            'price_type': 'computed',
            'option_deltas': {
                'option_name': delta_value
            },
            'dependencies': []  # For future
        }
        """
        model = {
            'base_price': None,
            'price_type': 'computed',
            'option_deltas': {},
            'dependencies': [],
            'confidence': 0.0
        }
        
        try:
            # Step 1: Get base price
            base_price = await self._get_current_price()
            if base_price is None:
                print("    ⚠ Could not detect base price")
                model['confidence'] = 0.0
                return model
            
            model['base_price'] = base_price
            print(f"    Base price: ${base_price:,.2f}")
            
            # Step 2: Learn deltas for each control
            successful_learns = 0
            
            for control in controls[:15]:  # Limit to 15 to avoid explosion
                try:
                    delta = await self._learn_option_delta(control, base_price)
                    
                    if delta is not None:
                        option_name = f"{control.get('group', 'option')}.{control['label']}"
                        model['option_deltas'][option_name] = delta
                        successful_learns += 1
                        
                        if delta != 0:
                            print(f"      • {control['label']}: ${delta:+,.2f}")
                
                except Exception as e:
                    print(f"      ⚠ Failed to learn delta for {control['label']}: {e}")
                    continue
            
            # Calculate confidence
            if successful_learns > 0:
                model['confidence'] = min(successful_learns / len(controls), 1.0)
            
            print(f"    ✓ Learned {successful_learns}/{len(controls)} option deltas")
        
        except Exception as e:
            print(f"    ✗ Price learning failed: {e}")
            model['confidence'] = 0.0
        
        return model
    
    async def _learn_option_delta(self, control: Dict, base_price: float) -> Optional[float]:
        """
        Learn price delta for a single option.
        
        Strategy:
        1. Ensure option is deselected (base state)
        2. Get current price (should be base)
        3. Toggle option
        4. Wait for price update
        5. Get new price
        6. Calculate delta
        """
        try:
            element = control.get('element')
            if not element:
                return None
            
            # Reset to unchecked state (if applicable)
            control_type = control['type']
            
            if control_type in ['checkbox', 'radio']:
                is_checked = await element.is_checked()
                
                # If already checked, uncheck first to reset
                if is_checked:
                    await element.click()
                    await asyncio.sleep(self.config.wait_after_action / 1000)
            
            # Get price before toggle
            price_before = await self._get_current_price()
            if price_before is None:
                price_before = base_price
            
            # Toggle option
            await element.click()
            
            # Wait for price update
            await asyncio.sleep(self.config.wait_after_action / 1000)
            
            # Get price after toggle
            price_after = await self._get_current_price()
            
            if price_after is None:
                return None
            
            # Calculate delta
            delta = price_after - price_before
            
            # Reset state (unclick if clicked)
            if control_type in ['checkbox', 'radio']:
                await element.click()
                await asyncio.sleep(self.config.wait_after_action / 1000)
            
            return delta
        
        except Exception as e:
            print(f"      ⚠ Delta learning error: {e}")
            return None
    
    async def _get_current_price(self) -> Optional[float]:
        """
        Find and extract current price from page.
        
        Returns price as float or None if not found.
        """
        try:
            # Try each selector
            for selector in self.price_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    
                    for element in elements:
                        text = await element.inner_text()
                        price = self._extract_price_from_text(text)
                        
                        if price is not None:
                            return price
                except Exception:
                    continue
            
            # Fallback: search entire page for price patterns
            page_text = await self.page.inner_text('body')
            price = self._extract_price_from_text(page_text)
            
            return price
        
        except Exception as e:
            print(f"      ⚠ Price extraction error: {e}")
            return None
    
    def _extract_price_from_text(self, text: str) -> Optional[float]:
        """
        Extract price value from text.
        
        Handles formats like:
        - $1,234.56
        - 1234.56
        - $1234
        - Total: $1,234.56
        """
        if not text:
            return None
        
        # Pattern for price with $ and commas
        patterns = [
            r'\$\s*([\d,]+\.?\d*)',  # $1,234.56
            r'Total[:\s]+\$\s*([\d,]+\.?\d*)',  # Total: $1,234
            r'Price[:\s]+\$\s*([\d,]+\.?\d*)',  # Price: $1,234
            r'([\d,]+\.\d{2})',  # 1,234.56 (with cents)
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            
            for match in matches:
                try:
                    # Remove commas and convert to float
                    price_str = match.replace(',', '')
                    price = float(price_str)
                    
                    # Sanity check (prices between $1 and $1M)
                    if 1.0 <= price <= 1_000_000:
                        return price
                except ValueError:
                    continue
        
        return None