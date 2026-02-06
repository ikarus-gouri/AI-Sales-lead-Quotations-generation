"""External configurator scraper using Jina."""

import time
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse
from .price_extractor import PriceExtractor


class ExternalConfiguratorScraper:
    """Scrapes external configurator pages using Jina and extracts customization options."""
    
    def __init__(self, http_client, product_extractor):
        """
        Initialize the external configurator scraper.
        
        Args:
            http_client: HTTPClient instance with scrape_with_jina method
            product_extractor: ProductExtractor instance with extract_customizations method
        """
        self.http_client = http_client
        self.product_extractor = product_extractor
        self.price_extractor = PriceExtractor()
    
    def scrape_external_configurator(
        self, 
        url: str, 
        product_name: str = None,
        delay: float = 1.0
    ) -> Dict:
        """
        Scrape an external configurator page and extract customizations.
        
        Args:
            url: The configurator URL to scrape
            product_name: Optional product name for logging
            delay: Delay in seconds before scraping (default: 1.0)
            
        Returns:
            Dictionary containing:
            {
                'success': bool,           # Whether scraping succeeded
                'customizations': dict,    # Extracted customization options (same format as ProductExtractor)
                'source': str,             # Always 'external_configurator'
                'platform': str,           # Detected platform name
                'error': str or None       # Error message if failed
            }
        """
        # Initialize result structure
        result = {
            'success': False,
            'customizations': {},
            'source': 'external_configurator',
            'platform': 'unknown',
            'error': None
        }
        
        try:
            # Detect platform from URL
            result['platform'] = self._detect_platform(url)
            
            print(f"  → Scraping external configurator ({result['platform']})...")
            print(f"     URL: {url}")
            
            # Respect crawl delay
            if delay > 0:
                time.sleep(delay)
            
            # Scrape the configurator page using Jina
            time.sleep(10)
            markdown = self.http_client.scrape_with_jina(url)
            
            if not markdown:
                result['error'] = "Failed to fetch configurator page"
                print(f"     ✗ Failed to fetch page")
                return result
            
            # Check if page is JavaScript-heavy
            is_js_heavy = self._is_javascript_heavy(markdown)
            
            # Try custom extraction first (for Jina markdown format)
            customizations = self._extract_customizations_from_markdown(markdown)
            
            # Extract base price if present
            base_price = self.price_extractor.extract_base_price(markdown)
            if base_price:
                print(f"     💰 Base price detected: {base_price}")
            
            # If custom extraction didn't work, fallback to product_extractor
            if not customizations:
                print(f"     → Trying product extractor fallback...")
                customizations = self.product_extractor.extract_customizations(markdown)
            
            # If still no results and page is JS-heavy, provide helpful error
            if not customizations and is_js_heavy:
                result['error'] = "JavaScript-heavy configurator detected. Jina cannot render dynamic content. Consider using Playwright/Selenium for this type of configurator."
                print(f"     ⚠ {result['error']}")
                return result
            
            # Check if we found any customizations
            if customizations:
                result['success'] = True
                result['customizations'] = customizations
                
                # Validate and clean up prices in customizations
                customizations = self._validate_and_clean_prices(customizations)
                result['customizations'] = customizations
                
                total_options = sum(len(opts) for opts in customizations.values())
                print(f"     ✓ Found {len(customizations)} categories, {total_options} total options")
            else:
                result['error'] = "No customizations found on configurator page"
                print(f"     ✗ No customizations extracted")
            
            return result
            
        except Exception as e:
            result['error'] = str(e)
            print(f"     ✗ Error: {e}")
            return result
    
    def _extract_customizations_from_markdown(self, markdown: str) -> Dict[str, List[Dict]]:
        """
        Extract customizations directly from Jina markdown output.
        Returns data in the same format as ProductExtractor:
        {
            "Category": [
                {"label": "Option", "price": "+$100", "image": "url"},
                ...
            ]
        }
        
        This method handles multiple markdown formats:
        1. Category headers with ### followed by options
        2. Bullet lists with options
        3. Image markdown with alt text
        4. Key-value pairs
        
        Args:
            markdown: The markdown content from Jina
            
        Returns:
            Dictionary mapping category names to lists of option dictionaries
        """
        customizations = {}
        current_category = None
        
        lines = markdown.split('\n')
        i = 0
        
        # Skip common noise patterns
        noise_keywords = [
            'you might also like', 'recommended', 'related products',
            'recently viewed', 'suggested', 'popular', 'trending',
            'total price', 'quote request', 'sample', 'cookie', 'privacy',
            'terms', 'shipping', 'returns', 'size guide', 'bat.bing',
            'tracking', 'analytics', 'social', 'newsletter', 'warning'
        ]
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Skip noise lines
            if any(keyword in line.lower() for keyword in noise_keywords):
                i += 1
                continue
            
            # Method 1: Category headers (### CATEGORY NAME)
            if line.startswith('###'):
                category_name = line.replace('###', '').strip()
                if category_name and len(category_name) < 100:
                    if not any(keyword in category_name.lower() for keyword in noise_keywords):
                        current_category = category_name
                        customizations[current_category] = []
                i += 1
                continue
            
            # Method 2: Category headers (## CATEGORY NAME)
            if line.startswith('##') and not line.startswith('###'):
                category_name = line.replace('##', '').strip()
                if category_name and len(category_name) < 100:
                    if not any(keyword in category_name.lower() for keyword in noise_keywords):
                        current_category = category_name
                        customizations[current_category] = []
                i += 1
                continue
            
            # Method 3: Bold category headers (**CATEGORY**)
            if line.startswith('**') and line.endswith('**'):
                category_name = line.replace('**', '').strip()
                if category_name and len(category_name) < 100:
                    if not any(keyword in category_name.lower() for keyword in noise_keywords):
                        current_category = category_name
                        customizations[current_category] = []
                i += 1
                continue
            
            # Method 4: Extract options from image markdown with alt text
            if current_category and line.startswith('![Image'):
                option_dict = self._extract_option_from_image_line(line, lines, i)
                if option_dict:
                    customizations[current_category].append(option_dict)
            
            # Method 5: Bullet point options (-, *, or •)
            elif current_category and (line.startswith('-') or line.startswith('*') or line.startswith('•')):
                option_dict = self._extract_option_from_bullet(line)
                if option_dict:
                    customizations[current_category].append(option_dict)
            
            # Method 6: Detect category from patterns like "Color:" or "Size:"
            elif ':' in line and len(line.split(':')[0]) < 50:
                category_dict = self._extract_category_from_colon(line)
                if category_dict:
                    current_category = category_dict['category']
                    customizations[current_category] = []
                    if category_dict.get('option'):
                        customizations[current_category].append(category_dict['option'])
            
            i += 1
        
        # Remove empty categories
        customizations = {k: v for k, v in customizations.items() if v}
        
        # If we found very few options, it might be a JS-heavy page
        total_options = sum(len(opts) for opts in customizations.values())
        if total_options < 3:
            print(f"     ⚠ Warning: Very few options found ({total_options}). This might be a JavaScript-heavy configurator.")
        
        return customizations
    
    def _extract_option_from_image_line(self, line: str, lines: List[str], index: int) -> Optional[Dict]:
        """
        Extract option from image markdown line.
        Returns format: {"label": "Name", "price": "+$100", "image": "url"}
        """
        # Extract from image alt text and URL
        match = re.search(r'!\[Image[^:]*:\s*([^\]]+)\]\(([^\)]+)\)', line)
        if not match:
            return None
        
        alt_text = match.group(1).strip()
        image_url = match.group(2).strip()
        
        # Skip tracking pixels
        if 'pixel' in image_url.lower() or 'g.gif' in image_url:
            return None
        
        option_label = alt_text
        price = None
        
        # Try to extract option name and price together using PriceExtractor
        option_info = self.price_extractor.extract_option_with_price(alt_text)
        if option_info:
            option_label = option_info.option_name
            price = option_info.price_modifier
        else:
            # Look ahead for price modifier on next line
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()
                price = self.price_extractor.extract_option_price(next_line)
            
            # Look ahead for standalone option text (more descriptive than alt text)
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip()
                if next_line and not next_line.startswith(('![Image', '#', '**', '-', '*', '|')):
                    if len(next_line) < 200:  # Reasonable option name length
                        # Try to extract from combined text
                        combined_info = self.price_extractor.extract_option_with_price(next_line)
                        if combined_info:
                            option_label = combined_info.option_name
                            price = combined_info.price_modifier
                        else:
                            option_label = next_line
                            # Check for price after standalone text
                            if index + 2 < len(lines):
                                price_line = lines[index + 2].strip()
                                extracted_price = self.price_extractor.extract_option_price(price_line)
                                if extracted_price:
                                    price = extracted_price
        
        if len(option_label) < 200:  # Validate length
            return {
                "label": option_label,
                "price": price,
                "image": image_url
            }
        
        return None
    
    def _extract_option_from_bullet(self, line: str) -> Optional[Dict]:
        """Extract option from bullet point line."""
        option_text = re.sub(r'^[-*•]\s*', '', line).strip()
        
        if not option_text or len(option_text) > 200:
            return None
        
        # Use PriceExtractor to parse option name and price
        option_name, price_modifier = self.price_extractor.parse_option_text(option_text)
        
        if option_name and len(option_name) > 2:
            return {
                "label": option_name,
                "price": price_modifier,
                "image": None
            }
        
        return None
    
    def _extract_category_from_colon(self, line: str) -> Optional[Dict]:
        """Extract category and optional option from 'Category: Option' format."""
        parts = line.split(':', 1)
        potential_category = parts[0].strip()
        
        # Validate category
        if not potential_category or any(char in potential_category for char in ['/', '\\', '(', ')', 'http']):
            return None
        
        noise_keywords = ['you might also like', 'recommended', 'cookie', 'privacy', 'terms']
        if any(keyword in potential_category.lower() for keyword in noise_keywords):
            return None
        
        result = {'category': potential_category}
        
        # Check if option is on same line
        if len(parts) > 1 and parts[1].strip():
            option_text = parts[1].strip()
            if len(option_text) < 200:
                # Use PriceExtractor to parse option name and price
                option_name, price_modifier = self.price_extractor.parse_option_text(option_text)
                
                result['option'] = {
                    "label": option_name,
                    "price": price_modifier,
                    "image": None
                }
        
        return result
    
    def _validate_and_clean_prices(self, customizations: Dict[str, List[Dict]]) -> Dict[str, List[Dict]]:
        """
        Validate and clean prices in customization options.
        
        Args:
            customizations: Dictionary of categories and their options
            
        Returns:
            Cleaned customizations with validated prices
        """
        cleaned = {}
        
        for category, options in customizations.items():
            cleaned_options = []
            
            for option in options:
                # Validate price if present
                if option.get('price'):
                    price_str = option['price']
                    
                    # Validate price is reasonable (between $0 and $100,000)
                    if self.price_extractor.validate_price(price_str, min_value=0, max_value=100000):
                        cleaned_options.append(option)
                    else:
                        # Keep option but remove invalid price
                        print(f"     ⚠ Invalid price '{price_str}' for option '{option.get('label')}' - removing price")
                        option_copy = option.copy()
                        option_copy['price'] = None
                        cleaned_options.append(option_copy)
                else:
                    # No price, keep as is
                    cleaned_options.append(option)
            
            if cleaned_options:
                cleaned[category] = cleaned_options
        
        return cleaned
    
    def _is_javascript_heavy(self, markdown: str) -> bool:
        """
        Detect if the page is JavaScript-heavy (SPA/React/Vue app).
        
        Args:
            markdown: The markdown content from Jina
            
        Returns:
            True if page appears to be JS-heavy
        """
        js_indicators = [
            'react', 'vue', 'angular', 'next.js', 'gatsby',
            'javascript required', 'js required', 'enable javascript',
            'noscript', '__next', '_app', 'webpack', 'bundle.js',
            'app.js', 'main.js', 'vendor.js'
        ]
        
        markdown_lower = markdown.lower()
        
        # Check for JS framework indicators
        js_count = sum(1 for indicator in js_indicators if indicator in markdown_lower)
        
        # Check for very short content (usually means JS didn't load)
        content_length = len(markdown.strip())
        
        # If we have multiple JS indicators or very little content, it's likely JS-heavy
        return js_count >= 2 or content_length < 500
    
    def _detect_platform(self, url: str) -> str:
        """
        Detect the external platform/service from the URL.
        
        Args:
            url: The configurator URL
            
        Returns:
            Platform name as string
        """
        domain = urlparse(url).netloc.lower()
        
        # Detect known configurator platforms
        platform_mapping = {
            'threekit': 'threekit',
            'zakeke': 'zakeke',
            'customily': 'customily',
            'productimize': 'productimize',
            'inksoft': 'inksoft',
            'printful': 'printful',
            'shopify': 'shopify',
            'woocommerce': 'woocommerce',
            'bigcommerce': 'bigcommerce',
            'nike': 'nike_by_you',  # JavaScript-heavy configurator
            'adidas': 'adidas_miadidas',  # JavaScript-heavy configurator
        }
        
        for keyword, platform_name in platform_mapping.items():
            if keyword in domain:
                return platform_name
        
        return 'generic_external'