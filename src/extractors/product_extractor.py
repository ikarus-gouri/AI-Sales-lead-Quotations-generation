"""Extract product information from markdown content."""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .color_extractor import ColorExtractor


class ProductExtractor:
    """Extract product details and customizations from scraped content."""

    def __init__(
        self,
        enable_color_extraction: bool = True,
        use_llm_naming: bool = False
    ):
        self.enable_color_extraction = enable_color_extraction

        if self.enable_color_extraction:
            self.color_extractor = ColorExtractor(
                use_llm_naming=use_llm_naming,
                cache_results=True
            )

    # ------------------------------------------------------------------
    # Core product info
    # ------------------------------------------------------------------

    def extract_product_name(self, url: str, markdown: str) -> str:
        """Extract product name from markdown or URL."""
        for line in markdown.split('\n'):
            line = line.strip()
            if line.startswith('# ') or line.startswith('## '):
                title = line.lstrip('#').strip()
                if len(title) > 3 and 'skip' not in title.lower() and 'content' not in title.lower():
                    return title

        # Fallback to URL
        path = urlparse(url).path
        return path.strip('/').split('/')[-1]

    def extract_base_price(self, markdown: str) -> Optional[str]:
        """Extract base price from markdown."""
        price_match = re.search(
            r'Base Price:\s*\$[\d,]+(?:\.\d{2})?\s*(?:CAD|USD)?',
            markdown,
            re.IGNORECASE
        )
        if price_match:
            return price_match.group(0).replace('Base Price:', '').strip()
        return None

    def extract_specifications(self, markdown: str) -> Dict[str, str]:
        """
        Extract product specifications from markdown.
        
        Looks for common specification patterns like:
        - Dimensions: X x Y x Z
        - Weight: XXX lbs
        - Material: XXX
        - Engine: XXX
        - Length: XX ft
        - Width: XX ft
        - Height: XX ft
        - Capacity: XXX
        - Power: XXX
        - etc.
        
        Returns:
            Dictionary of specification key-value pairs
        """
        specifications = {}
        
        # Common specification patterns
        spec_patterns = [
            # Dimensions
            (r'(?:Dimensions?|Size):\s*([^\n]+)', 'Dimensions'),
            (r'Length:\s*([^\n]+)', 'Length'),
            (r'Width:\s*([^\n]+)', 'Width'),
            (r'Height:\s*([^\n]+)', 'Height'),
            (r'Depth:\s*([^\n]+)', 'Depth'),
            
            # Weight and Capacity
            (r'Weight:\s*([^\n]+)', 'Weight'),
            (r'(?:Capacity|Payload):\s*([^\n]+)', 'Capacity'),
            (r'(?:GVWR|Gross Vehicle Weight Rating):\s*([^\n]+)', 'GVWR'),
            
            # Materials and Construction
            (r'Material:\s*([^\n]+)', 'Material'),
            (r'Construction:\s*([^\n]+)', 'Construction'),
            (r'Frame:\s*([^\n]+)', 'Frame'),
            (r'Body:\s*([^\n]+)', 'Body'),
            
            # Engine and Performance
            (r'Engine:\s*([^\n]+)', 'Engine'),
            (r'Motor:\s*([^\n]+)', 'Motor'),
            (r'(?:Horsepower|HP):\s*([^\n]+)', 'Horsepower'),
            (r'Torque:\s*([^\n]+)', 'Torque'),
            (r'Transmission:\s*([^\n]+)', 'Transmission'),
            (r'Fuel:\s*([^\n]+)', 'Fuel'),
            (r'(?:MPG|Fuel Economy):\s*([^\n]+)', 'Fuel Economy'),
            
            # Electrical
            (r'(?:Voltage|Power):\s*([^\n]+)', 'Power'),
            (r'Battery:\s*([^\n]+)', 'Battery'),
            (r'(?:Watts|Wattage):\s*([^\n]+)', 'Wattage'),
            
            # Other common specs
            (r'Model(?:\s+Number)?:\s*([^\n]+)', 'Model Number'),
            (r'SKU:\s*([^\n]+)', 'SKU'),
            (r'Brand:\s*([^\n]+)', 'Brand'),
            (r'Manufacturer:\s*([^\n]+)', 'Manufacturer'),
            (r'Warranty:\s*([^\n]+)', 'Warranty'),
            (r'Year:\s*([^\n]+)', 'Year'),
            (r'Color:\s*([^\n]+)', 'Color'),
            (r'Finish:\s*([^\n]+)', 'Finish'),
        ]
        
        for pattern, spec_name in spec_patterns:
            match = re.search(pattern, markdown, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                # Clean up the value
                value = re.sub(r'\s+', ' ', value)  # Normalize whitespace
                value = value.split('|')[0].strip()  # Take first part if pipe-separated
                if value and len(value) < 200:  # Reasonable length
                    specifications[spec_name] = value
        
        return specifications

    # ------------------------------------------------------------------
    # Customizations
    # ------------------------------------------------------------------

    def extract_customizations(self, markdown: str) -> Dict[str, List[Dict]]:
        """
        Extract customization categories and options.
        Optionally enrich color-related categories with HEX data.
        """
        customizations = self._extract_original_customizations(markdown)

        if not self.enable_color_extraction or not customizations:
            return customizations

        image_urls = self._extract_all_images(markdown)

        for category in list(customizations.keys()):
            if not self._is_color_category(category):
                continue

            color_result = self.color_extractor.extract(
                markdown=markdown,
                image_urls=image_urls,
                category_name=category
            )

            if color_result and color_result.success:
                # Attach color data in a deterministic key
                customizations[f"{category}_color_data"] = {
                    "method": color_result.method,
                    "confidence": color_result.confidence,
                    "source_image": color_result.source_image,
                    "colors": color_result.colors,
                }
                
                # Enrich the original options with hex codes
                colors_by_name = {c.name.lower(): c.hex for c in color_result.colors}
                
                for option in customizations.get(category, []):
                    if isinstance(option, dict):
                        option_label = option.get('label', '').lower()
                        # Try to match color by name
                        for color_name, hex_code in colors_by_name.items():
                            if color_name in option_label or option_label in color_name:
                                # Add hex code to reference field
                                current_ref = option.get('image', '') or option.get('reference', '')
                                if current_ref:
                                    option['reference'] = f"{current_ref} | {hex_code}"
                                else:
                                    option['reference'] = hex_code
                                option['hex_color'] = hex_code
                                break

        return customizations

    # ------------------------------------------------------------------
    # Internal extraction logic (your original code, unchanged)
    # ------------------------------------------------------------------

    def _extract_original_customizations(self, markdown: str) -> Dict[str, List[Dict]]:
        lines = markdown.split('\n')
        customizations = {}
        current_category = None
        current_options = []

        for line in lines:
            line_stripped = line.strip()

            category_match = re.match(r'^([A-Z][^:]+?):\s*\*?\s*$', line_stripped)

            if category_match:
                if current_category and current_options:
                    customizations[current_category] = current_options

                current_category = category_match.group(1).strip()
                current_options = []
                continue

            if current_category:
                option = self._extract_image_option(line_stripped)
                if option:
                    current_options.append(option)
                    continue

                option = self._extract_checkbox_option(line_stripped)
                if option:
                    current_options.append(option)

        if current_category and current_options:
            customizations[current_category] = current_options

        return self._clean_customizations(customizations)

    def _extract_image_option(self, line: str) -> Optional[Dict]:
        image_match = re.search(
            r'!\[(?:Image \d+:?\s*)?([^\]]+?)\s*(?:\(\+?\$[\d,]+\))?\]\(([^\)]+)\)',
            line
        )

        if not image_match:
            return None

        alt_text = image_match.group(1).strip()
        image_url = image_match.group(2).strip()

        if 'pixel.wp.com' in image_url or 'g.gif' in image_url:
            return None

        price_match = re.search(r'\(\+?\$[\d,]+\)', alt_text)
        price = price_match.group(0).strip('()') if price_match else None

        label = re.sub(r'\s*\(\+?\$[\d,]+\)\s*$', '', alt_text).strip()

        if label and len(label) > 2:
            return {
                "label": label,
                "price": price,
                "image": image_url
            }

        return None

    def _extract_checkbox_option(self, line: str) -> Optional[Dict]:
        checkbox_match = re.match(r'^-\s*\[x?\]\s*(.+?)\s*\(\+?\$[\d,]+\)', line)

        if not checkbox_match:
            return None

        full_text = checkbox_match.group(0)
        label = checkbox_match.group(1).strip()

        price_match = re.search(r'\(\+?\$[\d,]+\)', full_text)
        price = price_match.group(0).strip('()') if price_match else None

        return {
            "label": label,
            "price": price,
            "image": None
        }

    def _clean_customizations(self, customizations: Dict) -> Dict:
        cleaned = {}

        for category, options in customizations.items():
            seen = {}
            unique = []

            for opt in options:
                label = opt['label'].strip()
                key = label.lower()

                if len(label) < 3:
                    continue

                if key in seen:
                    idx = seen[key]
                    if opt['image'] and not unique[idx]['image']:
                        unique[idx]['image'] = opt['image']
                    if opt['price'] and not unique[idx]['price']:
                        unique[idx]['price'] = opt['price']
                else:
                    seen[key] = len(unique)
                    unique.append(opt)

            if unique:
                cleaned[category] = unique

        return cleaned

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_color_category(self, category: str) -> bool:
        return any(
            kw in category.lower()
            for kw in ("color", "finish", "wood", "stain", "shade")
        )

    def _extract_all_images(self, markdown: str) -> List[str]:
        return re.findall(r'!\[[^\]]*\]\(([^\)]+)\)', markdown)
