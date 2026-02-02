"""Network capture for intercepting pricing API responses."""

import json
import re
from typing import List, Dict, Optional


class NetworkCapture:
    """
    Capture and analyze network responses for pricing data.
    
    Useful for:
    - GraphQL pricing queries
    - REST API price calculations
    - AJAX total updates
    """
    
    def __init__(self):
        self.responses = []
        self.pricing_responses = []
    
    def attach_to_page(self, page):
        """Attach network listener to Playwright page."""
        page.on("response", self._handle_response)
    
    async def _handle_response(self, response):
        """Handle network response."""
        try:
            url = response.url
            status = response.status
            content_type = response.headers.get('content-type', '')
            
            # Store all responses
            self.responses.append({
                'url': url,
                'status': status,
                'content_type': content_type
            })
            
            # Check if this might be a pricing response
            if self._is_pricing_response(url, content_type):
                try:
                    body = await response.text()
                    parsed = self._parse_pricing_data(url, body)
                    
                    if parsed:
                        self.pricing_responses.append(parsed)
                except Exception:
                    pass
        
        except Exception as e:
            print(f"    ⚠ Network capture error: {e}")
    
    def _is_pricing_response(self, url: str, content_type: str) -> bool:
        """Check if response likely contains pricing data."""
        url_lower = url.lower()
        
        # URL patterns
        pricing_patterns = [
            '/price', '/total', '/calculate', '/cart',
            '/quote', '/estimate', 'graphql', '/api'
        ]
        
        if any(pattern in url_lower for pattern in pricing_patterns):
            return True
        
        # Content type check
        if 'json' in content_type:
            return True
        
        return False
    
    def _parse_pricing_data(self, url: str, body: str) -> Optional[Dict]:
        """Parse pricing data from response body."""
        try:
            # Try JSON parsing
            data = json.loads(body)
            
            # Look for price fields
            price_fields = self._find_price_fields(data)
            
            if price_fields:
                return {
                    'url': url,
                    'type': 'json',
                    'prices': price_fields
                }
        
        except json.JSONDecodeError:
            # Try text parsing
            prices = self._extract_prices_from_text(body)
            
            if prices:
                return {
                    'url': url,
                    'type': 'text',
                    'prices': prices
                }
        
        return None
    
    def _find_price_fields(self, data, prefix='') -> Dict:
        """Recursively find price-related fields in JSON."""
        prices = {}
        
        if isinstance(data, dict):
            for key, value in data.items():
                key_lower = key.lower()
                
                # Direct price fields
                if any(kw in key_lower for kw in ['price', 'total', 'cost', 'amount']):
                    if isinstance(value, (int, float)):
                        prices[f"{prefix}{key}"] = value
                    elif isinstance(value, str):
                        extracted = self._extract_price_from_string(value)
                        if extracted:
                            prices[f"{prefix}{key}"] = extracted
                
                # Recurse into nested objects
                elif isinstance(value, (dict, list)):
                    nested = self._find_price_fields(value, f"{prefix}{key}.")
                    prices.update(nested)
        
        elif isinstance(data, list):
            for i, item in enumerate(data[:5]):  # Limit to 5 items
                nested = self._find_price_fields(item, f"{prefix}[{i}].")
                prices.update(nested)
        
        return prices
    
    def _extract_prices_from_text(self, text: str) -> List[float]:
        """Extract price values from plain text."""
        prices = []
        
        # Price patterns
        pattern = r'\$\s*([\d,]+\.?\d*)'
        matches = re.findall(pattern, text)
        
        for match in matches:
            try:
                price = float(match.replace(',', ''))
                if 1.0 <= price <= 1_000_000:
                    prices.append(price)
            except ValueError:
                pass
        
        return prices
    
    def _extract_price_from_string(self, text: str) -> Optional[float]:
        """Extract single price from string."""
        if not isinstance(text, str):
            return None
        
        # Remove currency symbols and parse
        cleaned = text.replace('$', '').replace(',', '').strip()
        
        try:
            price = float(cleaned)
            if 1.0 <= price <= 1_000_000:
                return price
        except ValueError:
            pass
        
        return None
    
    def get_pricing_summary(self) -> Dict:
        """Get summary of captured pricing data."""
        return {
            'total_responses': len(self.responses),
            'pricing_responses': len(self.pricing_responses),
            'prices_found': [
                {
                    'url': resp['url'],
                    'prices': resp['prices']
                }
                for resp in self.pricing_responses
            ]
        }