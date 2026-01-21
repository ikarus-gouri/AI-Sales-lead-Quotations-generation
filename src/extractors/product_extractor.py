"""Extract product information from markdown content."""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


class ProductExtractor:
    """Extract product details from scraped content."""
    
    def extract_product_name(self, url: str, markdown: str) -> str:
        """
        Extract product name from markdown or URL.
        
        Args:
            url: The product page URL
            markdown: The markdown content
            
        Returns:
            Product name
        """
        # Try to find title in markdown
        for line in markdown.split('\n'):
            line = line.strip()
            if line.startswith('# ') or line.startswith('## '):
                title = line.lstrip('#').strip()
                # Skip generic titles
                if len(title) > 3 and 'skip' not in title.lower() and 'content' not in title.lower():
                    return title
        
        # Fallback to URL
        path = urlparse(url).path
        name = path.strip('/').split('/')[-1]
        return name
    
    def extract_base_price(self, markdown: str) -> Optional[str]:
        """
        Extract base price from markdown.
        
        Args:
            markdown: The markdown content
            
        Returns:
            Base price string or None
        """
        price_match = re.search(
            r'Base Price:\s*\$[\d,]+(?:\.\d{2})?\s*(?:CAD|USD)?',
            markdown,
            re.IGNORECASE
        )
        if price_match:
            return price_match.group(0).replace('Base Price:', '').strip()
        return None
    
    def extract_customizations(self, markdown: str) -> Dict[str, List[Dict]]:
        """
        Extract all customization categories and their options.
        
        Args:
            markdown: The markdown content
            
        Returns:
            Dictionary of customization categories and options
        """
        lines = markdown.split('\n')
        customizations = {}
        current_category = None
        current_options = []
        
        for line in lines:
            line_stripped = line.strip()
            
            # Detect category headers
            category_match = re.match(r'^([A-Z][^:]+?):\s*\*?\s*$', line_stripped)
            
            if category_match:
                # Save previous category
                if current_category and current_options:
                    customizations[current_category] = current_options
                
                current_category = category_match.group(1).strip()
                current_options = []
                continue
            
            # Extract options from images
            if current_category:
                option = self._extract_image_option(line_stripped)
                if option:
                    current_options.append(option)
                    continue
                
                # Extract from checkboxes
                option = self._extract_checkbox_option(line_stripped)
                if option:
                    current_options.append(option)
        
        # Save last category
        if current_category and current_options:
            customizations[current_category] = current_options
        
        return self._clean_customizations(customizations)
    
    def _extract_image_option(self, line: str) -> Optional[Dict]:
        """Extract option from image markdown."""
        image_match = re.search(
            r'!\[(?:Image \d+:?\s*)?([^\]]+?)\s*(?:\(\+?\$[\d,]+\))?\]\(([^\)]+)\)',
            line
        )
        
        if not image_match:
            return None
        
        alt_text = image_match.group(1).strip()
        image_url = image_match.group(2).strip()
        
        # Skip tracking pixels
        if 'pixel.wp.com' in image_url or 'g.gif' in image_url:
            return None
        
        # Extract price
        price_match = re.search(r'\(\+?\$[\d,]+\)', alt_text)
        price = price_match.group(0).strip('()') if price_match else None
        
        # Clean label
        label = re.sub(r'\s*\(\+?\$[\d,]+\)\s*$', '', alt_text).strip()
        
        if label and len(label) > 2:
            return {
                "label": label,
                "price": price,
                "image": image_url
            }
        
        return None
    
    def _extract_checkbox_option(self, line: str) -> Optional[Dict]:
        """Extract option from checkbox markdown."""
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
        """Remove duplicates from customizations."""
        cleaned = {}
        
        for category, options in customizations.items():
            seen = {}
            unique = []
            
            for opt in options:
                label = opt['label'].strip()
                key = label.lower()
                
                # Skip very short labels
                if len(label) < 3:
                    continue
                
                if key in seen:
                    # Merge with existing option
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