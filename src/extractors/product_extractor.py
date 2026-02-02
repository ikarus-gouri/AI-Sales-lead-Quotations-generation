"""Extract product information from markdown content."""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from .color_extractor import ColorExtractor


class ProductExtractor:
    """Extract product details and customizations from scraped content."""

    def __init__(
        self,
        enable_color_extraction: bool = False,
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
