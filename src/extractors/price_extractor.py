"""Extract price information from markdown content for Model S (Static scraping)."""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PriceInfo:
    """Container for extracted price information."""
    raw_price: str
    numeric_value: Optional[float]
    currency: str
    is_range: bool = False
    min_price: Optional[float] = None
    max_price: Optional[float] = None


@dataclass
class OptionPriceInfo:
    """Container for option name and price information."""
    option_name: str
    price_modifier: str
    numeric_value: float


class PriceExtractor:
    """Extract and normalize prices from scraped content."""

    # Currency symbols and codes
    CURRENCY_SYMBOLS = {
        '$': 'USD',
        '€': 'EUR',
        '£': 'GBP',
        '¥': 'JPY',
        '₹': 'INR',
        'CAD': 'CAD',
        'USD': 'USD',
        'EUR': 'EUR',
        'GBP': 'GBP',
    }

    # Price patterns (ordered by specificity)
    # Updated to handle prices with or without decimals
    PRICE_PATTERNS = [
        # Price with explicit label and currency code
        r'(?:price|cost|from|starting\s+at):\s*\$?([\d,]+(?:\.\d{2})?)\s*(CAD|USD|EUR|GBP)',
        
        # Price range with symbols
        r'([$€£¥₹])\s*([\d,]+(?:\.\d{2})?)\s*(?:-|to|–)\s*\1?\s*([\d,]+(?:\.\d{2})?)',
        
        # Simple price with currency symbol (with or without decimals)
        r'([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)',
        
        # Price with currency code
        r'([\d,]+(?:\.\d{1,2})?)\s*(CAD|USD|EUR|GBP)',
        
        # Starting from / From price
        r'(?:starting\s+)?(?:from|as\s+low\s+as)\s+([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)',
        
        # Base price explicitly labeled
        r'base\s+price:\s*([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)',
    ]

    # Option price patterns (price modifiers)
    # Updated to handle prices with or without decimals
    OPTION_PRICE_PATTERNS = [
        # Parentheses with modifier and symbol - most common pattern
        r'\(([+\-]?)\s*([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)\)',
        
        # + or - with price
        r'([+\-])\s*([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)',
        
        # Additional/Extra cost
        r'(?:additional|extra|add)\s+([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)',
        
        # No additional cost
        r'(?:no\s+(?:additional\s+)?(?:cost|charge)|included|free)',
    ]

    # Pattern to extract option name and price from same tag/text
    # Matches: "Option Name (+$1234)" or "Option Name ($1234)"
    OPTION_WITH_PRICE_PATTERN = r'^(.+?)\s*\(([+\-]?)\s*([$€£¥₹])\s*([\d,]+(?:\.\d{1,2})?)\)\s*$'
    
    # Pattern to extract from input value attribute
    # Matches: "Option Name - $1234" or "Option Name - $0"
    INPUT_VALUE_PATTERN = r'^(.+?)\s*-\s*\$\s*([\d,]+(?:\.\d{1,2})?)\s*$'

    def __init__(self):
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.PRICE_PATTERNS]
        self.compiled_option_patterns = [re.compile(p, re.IGNORECASE) for p in self.OPTION_PRICE_PATTERNS]
        self.compiled_option_with_price = re.compile(self.OPTION_WITH_PRICE_PATTERN, re.IGNORECASE)
        self.compiled_input_value = re.compile(self.INPUT_VALUE_PATTERN, re.IGNORECASE)

    # ------------------------------------------------------------------
    # Main extraction methods
    # ------------------------------------------------------------------

    def extract_base_price(self, markdown: str) -> Optional[str]:
        """
        Extract the base/main price from markdown content.
        
        Args:
            markdown: The markdown content to search
            
        Returns:
            Formatted price string (e.g., "$1,299 USD") or None
        """
        # Try to find explicit base price label first
        base_price_match = re.search(
            r'base\s+price:\s*([$€£¥₹])\s*([\d,]+(?:\.\d{2})?)\s*(CAD|USD|EUR|GBP)?',
            markdown,
            re.IGNORECASE
        )
        
        if base_price_match:
            symbol = base_price_match.group(1)
            amount = base_price_match.group(2)
            currency = base_price_match.group(3) or self.CURRENCY_SYMBOLS.get(symbol, 'USD')
            return f"{symbol}{amount} {currency}"

        # Try other patterns
        for pattern in self.compiled_patterns:
            match = pattern.search(markdown)
            if match:
                price_info = self._parse_price_match(match)
                if price_info and price_info.numeric_value:
                    if price_info.is_range:
                        return f"${price_info.min_price:,.2f} - ${price_info.max_price:,.2f} {price_info.currency}"
                    else:
                        return self._format_price(price_info.numeric_value, price_info.currency)

        return None

    def extract_all_prices(self, markdown: str) -> List[PriceInfo]:
        """
        Extract all prices found in the markdown content.
        
        Args:
            markdown: The markdown content to search
            
        Returns:
            List of PriceInfo objects
        """
        prices = []
        seen_values = set()

        for pattern in self.compiled_patterns:
            for match in pattern.finditer(markdown):
                price_info = self._parse_price_match(match)
                if price_info and price_info.numeric_value:
                    # Avoid duplicates
                    if price_info.numeric_value not in seen_values:
                        prices.append(price_info)
                        seen_values.add(price_info.numeric_value)

        return sorted(prices, key=lambda x: x.numeric_value or 0)

    def extract_option_price(self, option_text: str) -> Optional[str]:
        """
        Extract price modifier from an option/customization text.
        
        Args:
            option_text: Text describing the option (e.g., "Premium Finish (+$200)")
            
        Returns:
            Formatted price modifier (e.g., "+$200") or None
        """
        # Strip HTML tags if present
        clean_text = self._strip_html_tags(option_text)
        
        # Check for "no cost" indicators first
        if re.search(r'(?:no\s+(?:additional\s+)?(?:cost|charge)|included|free)', clean_text, re.IGNORECASE):
            return "+$0"

        for pattern in self.compiled_option_patterns:
            match = pattern.search(clean_text)
            if match:
                groups = match.groups()
                
                # Handle different pattern structures
                if len(groups) >= 3:
                    modifier = groups[0] if groups[0] in ['+', '-'] else '+'
                    symbol = groups[1] if groups[1] in self.CURRENCY_SYMBOLS else '$'
                    amount = groups[2] if len(groups) > 2 else groups[1]
                    
                    # Clean and parse amount
                    numeric_value = self._parse_numeric_value(amount)
                    if numeric_value is not None:
                        # Format with decimals only if needed
                        if numeric_value % 1 == 0:
                            return f"{modifier}${int(numeric_value):,}"
                        else:
                            return f"{modifier}${numeric_value:,.2f}"
                elif len(groups) == 2:
                    modifier = '+'
                    symbol = groups[0]
                    amount = groups[1]
                    
                    numeric_value = self._parse_numeric_value(amount)
                    if numeric_value is not None:
                        # Format with decimals only if needed
                        if numeric_value % 1 == 0:
                            return f"{modifier}${int(numeric_value):,}"
                        else:
                            return f"{modifier}${numeric_value:,.2f}"

        return None

    def extract_option_with_price(self, option_text: str) -> Optional[OptionPriceInfo]:
        """
        Extract both option name and price from text like "Custom Color Metal Cladding (+$1850)".
        
        Args:
            option_text: Text containing option name and price in same string
            
        Returns:
            OptionPriceInfo object with name and price, or None
        """
        # Strip HTML tags if present
        clean_text = self._strip_html_tags(option_text)
        
        # Try the parentheses pattern first (most common)
        match = self.compiled_option_with_price.search(clean_text)
        
        if match:
            option_name = match.group(1).strip()
            modifier = match.group(2) if match.group(2) in ['+', '-'] else '+'
            symbol = match.group(3)
            amount = match.group(4)
            
            # Parse numeric value
            numeric_value = self._parse_numeric_value(amount)
            
            if numeric_value is not None:
                # Format price modifier
                if numeric_value % 1 == 0:
                    price_modifier = f"{modifier}${int(numeric_value):,}"
                else:
                    price_modifier = f"{modifier}${numeric_value:,.2f}"
                
                return OptionPriceInfo(
                    option_name=option_name,
                    price_modifier=price_modifier,
                    numeric_value=numeric_value if modifier == '+' else -numeric_value
                )
        
        # Try the input value pattern (e.g., "Option Name - $1234")
        match = self.compiled_input_value.search(clean_text)
        
        if match:
            option_name = match.group(1).strip()
            amount = match.group(2)
            
            # Parse numeric value
            numeric_value = self._parse_numeric_value(amount)
            
            if numeric_value is not None:
                # Determine modifier (if $0, it's included)
                modifier = '+' if numeric_value > 0 else ''
                
                # Format price modifier
                if numeric_value % 1 == 0:
                    price_modifier = f"{modifier}${int(numeric_value):,}" if numeric_value > 0 else "+$0"
                else:
                    price_modifier = f"{modifier}${numeric_value:,.2f}"
                
                return OptionPriceInfo(
                    option_name=option_name,
                    price_modifier=price_modifier,
                    numeric_value=numeric_value
                )
        
        return None

    def extract_options_from_html_inputs(self, html_content: str) -> List[OptionPriceInfo]:
        """
        Extract options from HTML input elements (radio buttons, checkboxes, etc.).
        This is useful for parsing form options before Jina conversion.
        
        Looks for patterns like:
        <input ... value="Option Name - $1234" ... alt="Option Name (+$1234)">
        
        Args:
            html_content: Raw HTML content containing input elements
            
        Returns:
            List of OptionPriceInfo objects
        """
        from bs4 import BeautifulSoup
        
        options = []
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all input elements (radio, checkbox, etc.)
        inputs = soup.find_all('input', {'type': ['radio', 'checkbox']})
        
        for input_elem in inputs:
            # Try to extract from value attribute
            value = input_elem.get('value', '')
            if value:
                option_info = self.extract_option_with_price(value)
                if option_info:
                    options.append(option_info)
                    continue
            
            # Try to extract from alt attribute in associated images
            label = input_elem.find_parent('label')
            if label:
                img = label.find('img')
                if img and img.get('alt'):
                    alt_text = img.get('alt')
                    option_info = self.extract_option_with_price(alt_text)
                    if option_info:
                        options.append(option_info)
                        continue
                
                # Try to extract from span text
                spans = label.find_all('span', class_='frm_text_label_for_image_inner')
                if spans:
                    for span in spans:
                        option_info = self.extract_option_with_price(span.get_text())
                        if option_info:
                            options.append(option_info)
                            break
        
        return options

    def parse_option_text(self, option_text: str) -> Tuple[str, Optional[str]]:
        """
        Parse option text to extract name and price separately.
        Handles cases where they're in the same string.
        
        Args:
            option_text: Text like "Custom Color Metal Cladding (+$1850)" or just "Custom Color"
            
        Returns:
            Tuple of (option_name, price_modifier) where price_modifier may be None
        """
        option_info = self.extract_option_with_price(option_text)
        
        if option_info:
            return (option_info.option_name, option_info.price_modifier)
        else:
            # No price found in text, return text as-is with no price
            clean_text = self._strip_html_tags(option_text)
            return (clean_text.strip(), None)

    def extract_price_from_text(self, text: str) -> Optional[str]:
        """
        Extract any price from arbitrary text.
        Useful for extracting prices from titles, descriptions, etc.
        
        Args:
            text: Text to search for prices
            
        Returns:
            Formatted price string or None
        """
        print(f"\033[34m Extracting price from text: {text[:60]}... \033[0m")
        for pattern in self.compiled_patterns:
            match = pattern.search(text)
            if match:
                price_info = self._parse_price_match(match)
                print("\033[32m Price match found: \033[0m", price_info)
                if price_info and price_info.numeric_value:
                    return self._format_price(price_info.numeric_value, price_info.currency)
        
        return None

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _parse_price_match(self, match: re.Match) -> Optional[PriceInfo]:
        """Parse a regex match into a PriceInfo object."""
        groups = match.groups()
        
        if not groups:
            return None

        # Try to identify the structure
        # Could be: (symbol, amount), (amount, currency), (symbol, min, max), etc.
        
        # Check for range pattern (symbol, min, max)
        if len(groups) >= 3 and self._is_numeric(groups[1]) and self._is_numeric(groups[2]):
            symbol = groups[0]
            min_val = self._parse_numeric_value(groups[1])
            max_val = self._parse_numeric_value(groups[2])
            
            if min_val is not None and max_val is not None:
                currency = self.CURRENCY_SYMBOLS.get(symbol, 'USD')
                return PriceInfo(
                    raw_price=match.group(0),
                    numeric_value=min_val,
                    currency=currency,
                    is_range=True,
                    min_price=min_val,
                    max_price=max_val
                )
        
        # Single price with symbol
        if len(groups) >= 2:
            # Try (symbol, amount) or (amount, currency)
            if groups[0] in self.CURRENCY_SYMBOLS:
                symbol = groups[0]
                amount = groups[1]
                currency = self.CURRENCY_SYMBOLS.get(symbol, 'USD')
            elif groups[1] in self.CURRENCY_SYMBOLS:
                amount = groups[0]
                currency = groups[1]
            else:
                # Assume first is symbol, second is amount
                symbol = groups[0] if groups[0] in self.CURRENCY_SYMBOLS else '$'
                amount = groups[1] if self._is_numeric(groups[1]) else groups[0]
                currency = groups[2] if len(groups) > 2 else self.CURRENCY_SYMBOLS.get(symbol, 'USD')
            
            numeric_value = self._parse_numeric_value(amount)
            if numeric_value is not None:
                return PriceInfo(
                    raw_price=match.group(0),
                    numeric_value=numeric_value,
                    currency=currency
                )
        
        return None

    def _strip_html_tags(self, text: str) -> str:
        """Remove HTML tags from text."""
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', text)
        # Clean up extra whitespace
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
    
    def _parse_numeric_value(self, value_str: str) -> Optional[float]:
        """Parse a string into a numeric value, handling commas and formatting."""
        if not value_str:
            return None
        
        # Remove currency symbols and extra whitespace
        cleaned = re.sub(r'[$€£¥₹,\s]', '', str(value_str))
        
        try:
            return float(cleaned)
        except ValueError:
            return None

    def _is_numeric(self, value: str) -> bool:
        """Check if a string represents a numeric value."""
        if not value:
            return False
        cleaned = re.sub(r'[,\s]', '', str(value))
        try:
            float(cleaned)
            return True
        except ValueError:
            return False

    def _format_price(self, value: float, currency: str = 'USD') -> str:
        """Format a numeric value as a price string."""
        return f"${value:,.2f} {currency}"

    def extract_price_context(self, markdown: str, max_context: int = 200) -> Dict[str, str]:
        """
        Extract price along with surrounding context for better understanding.
        
        Args:
            markdown: The markdown content
            max_context: Maximum characters of context to include
            
        Returns:
            Dictionary with price and context information
        """
        for pattern in self.compiled_patterns:
            match = pattern.search(markdown)
            if match:
                price_info = self._parse_price_match(match)
                if price_info and price_info.numeric_value:
                    # Get surrounding text
                    start = max(0, match.start() - max_context // 2)
                    end = min(len(markdown), match.end() + max_context // 2)
                    context = markdown[start:end].strip()
                    
                    return {
                        'price': self._format_price(price_info.numeric_value, price_info.currency),
                        'context': context,
                        'raw_match': match.group(0)
                    }
        
        return {}

    def validate_price(self, price_str: str, min_value: float = 0, max_value: float = 1000000) -> bool:
        """
        Validate that a price string represents a reasonable value.
        
        Args:
            price_str: Price string to validate
            min_value: Minimum acceptable price
            max_value: Maximum acceptable price
            
        Returns:
            True if price is valid and within range
        """
        numeric_value = self._parse_numeric_value(price_str)
        if numeric_value is None:
            return False
        
        return min_value <= numeric_value <= max_value