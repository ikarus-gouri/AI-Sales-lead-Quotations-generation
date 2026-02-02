"""Discover interactive controls on dynamic configurator pages."""

from typing import List, Dict, Any


class OptionDiscovery:
    """
    Find and classify interactive controls on configurator pages.
    
    Discovers:
    - Radio buttons
    - Checkboxes
    - Select dropdowns
    - Custom controls (divs with click handlers)
    """
    
    def __init__(self, page: Any):
        self.page = page
    
    async def find_interactive_controls(self) -> List[Dict]:
        """
        Discover all interactive controls on the page.
        
        Returns list of control dictionaries with:
        - type: 'radio', 'checkbox', 'select', 'button', 'custom'
        - label: User-visible text
        - selector: CSS selector
        - value: Current value (if applicable)
        - group: Group name (for related controls)
        """
        controls = []
        
        # Find standard HTML controls
        controls.extend(await self._find_radio_buttons())
        controls.extend(await self._find_checkboxes())
        controls.extend(await self._find_selects())
        controls.extend(await self._find_buttons())
        
        # Find custom controls (React/Vue components)
        controls.extend(await self._find_custom_controls())
        
        # Deduplicate and group
        controls = self._deduplicate_controls(controls)
        controls = self._group_related_controls(controls)
        
        return controls
    
    async def _find_radio_buttons(self) -> List[Dict]:
        """Find radio button inputs."""
        controls = []
        
        try:
            radios = await self.page.query_selector_all('input[type="radio"]')
            
            for radio in radios:
                try:
                    name = await radio.get_attribute('name') or ''
                    value = await radio.get_attribute('value') or ''
                    is_checked = await radio.is_checked()
                    
                    # Get label
                    label = await self._get_label_for_input(radio)
                    
                    if label or name:
                        controls.append({
                            'type': 'radio',
                            'label': label or f"Option {value}",
                            'selector': f'input[type="radio"][name="{name}"][value="{value}"]',
                            'value': value,
                            'group': name,
                            'checked': is_checked,
                            'element': radio
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"    ⚠ Radio button discovery error: {e}")
        
        return controls
    
    async def _find_checkboxes(self) -> List[Dict]:
        """Find checkbox inputs."""
        controls = []
        
        try:
            checkboxes = await self.page.query_selector_all('input[type="checkbox"]')
            
            for checkbox in checkboxes:
                try:
                    name = await checkbox.get_attribute('name') or ''
                    value = await checkbox.get_attribute('value') or ''
                    is_checked = await checkbox.is_checked()
                    
                    label = await self._get_label_for_input(checkbox)
                    
                    if label or name:
                        controls.append({
                            'type': 'checkbox',
                            'label': label or f"Checkbox {name}",
                            'selector': f'input[type="checkbox"][name="{name}"]',
                            'value': value,
                            'group': name,
                            'checked': is_checked,
                            'element': checkbox
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"    ⚠ Checkbox discovery error: {e}")
        
        return controls
    
    async def _find_selects(self) -> List[Dict]:
        """Find select dropdowns."""
        controls = []
        
        try:
            selects = await self.page.query_selector_all('select')
            
            for select in selects:
                try:
                    name = await select.get_attribute('name') or ''
                    
                    # Get all options
                    options = await select.query_selector_all('option')
                    option_values = []
                    
                    for option in options:
                        opt_value = await option.get_attribute('value') or ''
                        opt_text = await option.inner_text()
                        option_values.append({
                            'value': opt_value,
                            'text': opt_text.strip()
                        })
                    
                    label = await self._get_label_for_input(select)
                    
                    if option_values:
                        controls.append({
                            'type': 'select',
                            'label': label or f"Dropdown {name}",
                            'selector': f'select[name="{name}"]',
                            'options': option_values,
                            'group': name,
                            'element': select
                        })
                except Exception:
                    continue
        except Exception as e:
            print(f"    ⚠ Select discovery error: {e}")
        
        return controls
    
    async def _find_buttons(self) -> List[Dict]:
        """Find buttons that might trigger options."""
        controls = []
        
        try:
            # Look for buttons with data attributes or classes suggesting options
            button_selectors = [
                'button[data-option]',
                'button[data-value]',
                'button.option',
                'button.variant'
            ]
            
            for selector in button_selectors:
                buttons = await self.page.query_selector_all(selector)
                
                for button in buttons:
                    try:
                        text = await button.inner_text()
                        data_option = await button.get_attribute('data-option') or ''
                        data_value = await button.get_attribute('data-value') or ''
                        
                        if text.strip():
                            controls.append({
                                'type': 'button',
                                'label': text.strip(),
                                'selector': selector,
                                'value': data_value or data_option,
                                'group': data_option,
                                'element': button
                            })
                    except Exception:
                        continue
        except Exception as e:
            print(f"    ⚠ Button discovery error: {e}")
        
        return controls
    
    async def _find_custom_controls(self) -> List[Dict]:
        """Find custom controls (React/Vue components)."""
        controls = []
        
        try:
            # Look for divs/spans with click handlers and option-like classes
            custom_selectors = [
                'div[data-option]',
                'div.option-item',
                'div.variant-selector',
                'span[data-value]',
                '[class*="option"][role="button"]',
                '[class*="swatch"]'
            ]
            
            for selector in custom_selectors:
                elements = await self.page.query_selector_all(selector)
                
                for element in elements[:20]:  # Limit to avoid explosion
                    try:
                        text = await element.inner_text()
                        data_option = await element.get_attribute('data-option') or ''
                        data_value = await element.get_attribute('data-value') or ''
                        
                        if text.strip():
                            controls.append({
                                'type': 'custom',
                                'label': text.strip()[:50],  # Limit length
                                'selector': selector,
                                'value': data_value or data_option,
                                'group': data_option,
                                'element': element
                            })
                    except Exception:
                        continue
        except Exception as e:
            print(f"    ⚠ Custom control discovery error: {e}")
        
        return controls
    
    async def _get_label_for_input(self, input_element) -> str:
        """Get associated label text for an input."""
        try:
            # Try 1: Associated <label> element
            input_id = await input_element.get_attribute('id')
            if input_id:
                label = await self.page.query_selector(f'label[for="{input_id}"]')
                if label:
                    return (await label.inner_text()).strip()
            
            # Try 2: Parent <label>
            parent = await input_element.evaluate_handle('el => el.parentElement')
            if parent:
                tag_name = await parent.evaluate('el => el.tagName')
                if tag_name.lower() == 'label':
                    return (await parent.inner_text()).strip()
            
            # Try 3: Nearby text
            nearby_text = await input_element.evaluate('''
                el => {
                    const next = el.nextSibling;
                    if (next && next.nodeType === 3) return next.textContent.trim();
                    const nextEl = el.nextElementSibling;
                    if (nextEl) return nextEl.textContent.trim();
                    return '';
                }
            ''')
            if nearby_text:
                return nearby_text[:50]
        
        except Exception:
            pass
        
        return ''
    
    def _deduplicate_controls(self, controls: List[Dict]) -> List[Dict]:
        """Remove duplicate controls."""
        seen = set()
        unique = []
        
        for control in controls:
            # Create unique key from type, group, and value
            key = (control['type'], control.get('group', ''), control.get('value', ''))
            
            if key not in seen:
                seen.add(key)
                unique.append(control)
        
        return unique
    
    def _group_related_controls(self, controls: List[Dict]) -> List[Dict]:
        """Add grouping metadata to related controls."""
        # Group by 'group' field (e.g., radio button names)
        groups = {}
        
        for control in controls:
            group_name = control.get('group', 'ungrouped')
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append(control)
        
        # Add group size metadata
        for control in controls:
            group_name = control.get('group', 'ungrouped')
            control['group_size'] = len(groups[group_name])
        
        return controls