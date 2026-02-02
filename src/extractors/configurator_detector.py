"""Detect and classify product configurators dynamically."""

import re
from typing import Dict, Optional, Tuple, List
from urllib.parse import urljoin, urlparse


class ConfiguratorDetector:
    """Dynamically detects if a product has a configurator and its type."""
    
    def __init__(self):
        """Initialize the configurator detector."""
        # Dynamic keyword categories
        self.action_keywords = [
            'customize', 'personalize', 'design', 'configure', 'build',
            'create', 'make your own', 'start designing', 'start building'
        ]
         
        self.customization_indicators = [
            'choose', 'select', 'pick', 'add', 'upgrade',
            'option', 'variant', 'color', 'size', 'material'
        ]
        
        # Common external configurator patterns (can be extended)
        self.external_domains = [
            'zakeke', 'inksoft', 'customcat', 'printful',
            'threekit', 'configit', 'product-builder'
        ]
    
    def has_configurator(self, url: str, markdown: str) -> Dict:
        """
        Dynamically check if product page has a configurator.
        
        Args:
            url: Product page URL
            markdown: Page content in markdown
            
        Returns:
            Dictionary with configurator information
        """
        result = {
            'has_configurator': False,
            'configurator_type': 'none',
            'configurator_url': None,
            'confidence': 0.0,
            'indicators': [],
            'signals': {}  # Detailed signal breakdown
        }
        
        # Signal 1: Look for configurator-related links
        config_links = self._find_configurator_links(url, markdown)
        
        if config_links:
            result['indicators'].append('configurator_links_found')
            result['signals']['links'] = len(config_links)
            
            # Pick the most likely configurator URL
            result['configurator_url'] = config_links[0]
            
            # Determine if external
            if self._is_external_url(result['configurator_url'], url):
                result['configurator_type'] = 'external'
                result['indicators'].append('external_domain')
            else:
                result['configurator_type'] = 'embedded'
                result['indicators'].append('same_domain')
            
            result['has_configurator'] = True
        
        # Signal 2: Analyze content for customization patterns
        content_score = self._analyze_content_patterns(markdown)
        result['signals']['content_score'] = content_score
        
        if content_score > 0:
            result['has_configurator'] = True
            result['indicators'].append(f'content_patterns_{content_score}')
            
            # If no URL found, likely embedded
            if not result['configurator_url']:
                result['configurator_type'] = 'embedded'
                result['indicators'].append('embedded_inferred')
        
        # Signal 3: Detect interactive form elements
        form_elements = self._detect_form_elements(markdown)
        result['signals']['form_elements'] = form_elements
        
        if form_elements > 0:
            result['has_configurator'] = True
            result['indicators'].append(f'form_elements_{form_elements}')
            
            if not result['configurator_type'] or result['configurator_type'] == 'none':
                result['configurator_type'] = 'embedded'
        
        # Signal 4: Look for option/variant structures
        option_groups = self._detect_option_groups(markdown)
        result['signals']['option_groups'] = option_groups
        
        if option_groups >= 2:
            result['has_configurator'] = True
            result['indicators'].append(f'option_groups_{option_groups}')
            
            if result['configurator_type'] == 'none':
                result['configurator_type'] = 'embedded'
        
        # Signal 5: Price variation patterns
        price_variants = self._detect_price_variants(markdown)
        result['signals']['price_variants'] = price_variants
        
        if price_variants >= 3:
            result['has_configurator'] = True
            result['indicators'].append(f'price_variants_{price_variants}')
        
        # Calculate confidence from all signals
        result['confidence'] = self._calculate_confidence(result['signals'], result['indicators'])
        
        return result
    
    def _find_configurator_links(self, base_url: str, markdown: str) -> List[str]:
        """
        Dynamically find links that might lead to configurators.
        
        Args:
            base_url: Current page URL
            markdown: Page content
            
        Returns:
            List of potential configurator URLs
        """
        config_links = []
        
        # Extract all markdown links
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        links = re.findall(link_pattern, markdown)
        
        for link_text, link_url in links:
            text_lower = link_text.lower()
            url_lower = link_url.lower()
            
            # Score this link based on relevance
            score = 0
            
            # Check link text for action keywords
            for keyword in self.action_keywords:
                if keyword in text_lower:
                    score += 3
            
            # Check URL for customization patterns
            customization_patterns = [
                'custom', 'config', 'builder', 'design',
                'personalize', 'create', 'build'
            ]
            
            for pattern in customization_patterns:
                if pattern in url_lower:
                    score += 2
            
            # Buttons with certain text are strong signals
            button_phrases = ['get started', 'start now', 'begin', 'design now']
            if any(phrase in text_lower for phrase in button_phrases):
                score += 2
            
            # If score is high enough, it's likely a configurator link
            if score >= 3:
                absolute_url = urljoin(base_url, link_url)
                config_links.append(absolute_url)
        
        # Sort by likelihood (could be enhanced)
        return config_links
    
    def _analyze_content_patterns(self, markdown: str) -> int:
        """
        Analyze content for customization patterns.
        
        Args:
            markdown: Page content
            
        Returns:
            Content pattern score
        """
        markdown_lower = markdown.lower()
        score = 0
        
        # Check for action keywords
        for keyword in self.action_keywords:
            if keyword in markdown_lower:
                score += 1
        
        # Check for customization indicators
        for indicator in self.customization_indicators:
            if indicator in markdown_lower:
                score += 0.5
        
        # Look for phrases like "step 1", "step 2" (wizard pattern)
        step_pattern = r'step\s+\d+'
        steps = len(re.findall(step_pattern, markdown_lower))
        if steps >= 2:
            score += 3
        
        return int(score)
    
    def _detect_form_elements(self, markdown: str) -> int:
        """
        Detect form-like elements in content.
        
        Args:
            markdown: Page content
            
        Returns:
            Number of form elements detected
        """
        count = 0
        
        # Checkboxes
        checkboxes = len(re.findall(r'-\s*\[[x ]\]', markdown))
        count += min(checkboxes // 3, 3)  # Cap contribution
        
        # Radio button patterns
        radio_patterns = [
            r'\(\s*\)\s+',  # ( ) Option
            r'○\s+',         # ○ Option
            r'◯\s+',         # ◯ Option
        ]
        for pattern in radio_patterns:
            count += min(len(re.findall(pattern, markdown)) // 3, 2)
        
        # Dropdown indicators
        dropdown_keywords = ['select from', 'choose from', 'dropdown', 'select:']
        for keyword in dropdown_keywords:
            if keyword in markdown.lower():
                count += 1
        
        return min(count, 10)  # Cap at 10
    
    def _detect_option_groups(self, markdown: str) -> int:
        """
        Detect grouped options (like color options, size options, etc.).
        
        Args:
            markdown: Page content
            
        Returns:
            Number of option groups detected
        """
        # Look for category headers followed by options
        lines = markdown.split('\n')
        groups = 0
        
        in_group = False
        group_items = 0
        
        for line in lines:
            line_stripped = line.strip()
            
            # Potential category header patterns
            if re.match(r'^#+\s+', line_stripped) or \
               re.match(r'^[A-Z][^:]{3,30}:\s*$', line_stripped) or \
               re.match(r'^\*\*[A-Z][^*]+\*\*\s*$', line_stripped):
                
                # Save previous group if it had items
                if in_group and group_items >= 2:
                    groups += 1
                
                in_group = True
                group_items = 0
                continue
            
            # Count items in group
            if in_group:
                # Bullet points, checkboxes, or numbered items
                if re.match(r'^[-*•]\s+', line_stripped) or \
                   re.match(r'^\d+\.\s+', line_stripped) or \
                   re.match(r'^-\s*\[[x ]\]', line_stripped):
                    group_items += 1
                elif line_stripped == '':
                    # Empty line might end group
                    if group_items >= 2:
                        groups += 1
                    in_group = False
                    group_items = 0
        
        # Don't forget the last group
        if in_group and group_items >= 2:
            groups += 1
        
        return groups
    
    def _detect_price_variants(self, markdown: str) -> int:
        """
        Detect multiple price points (suggests customization).
        
        Args:
            markdown: Page content
            
        Returns:
            Number of price variants found
        """
        # Find all price mentions
        price_patterns = [
            r'\$[\d,]+(?:\.\d{2})?',
            r'[\d,]+(?:\.\d{2})?\s*(?:CAD|USD|EUR|GBP)',
            r'\+\s*\$[\d,]+',
        ]
        
        prices = set()
        for pattern in price_patterns:
            matches = re.findall(pattern, markdown)
            prices.update(matches)
        
        return len(prices)
    
    def _is_external_url(self, url: str, base_url: str) -> bool:
        """
        Check if URL is external to the base domain.
        
        Args:
            url: URL to check
            base_url: Base/current URL
            
        Returns:
            True if external
        """
        url_domain = urlparse(url).netloc.lower()
        base_domain = urlparse(base_url).netloc.lower()
        
        # Different domain = external
        if url_domain != base_domain:
            # Also check if it's a known external configurator
            for ext_domain in self.external_domains:
                if ext_domain in url_domain:
                    return True
            return True
        
        return False
    
    def _calculate_confidence(self, signals: Dict, indicators: List[str]) -> float:
        """
        Calculate confidence score based on signals.
        
        Args:
            signals: Signal data
            indicators: List of indicators found
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        if not indicators:
            return 0.0
        
        score = 0.0
        
        # Weight different signals
        if signals.get('links', 0) > 0:
            score += 0.35
        
        if signals.get('content_score', 0) >= 3:
            score += 0.25
        elif signals.get('content_score', 0) > 0:
            score += 0.15
        
        if signals.get('form_elements', 0) >= 3:
            score += 0.20
        elif signals.get('form_elements', 0) > 0:
            score += 0.10
        
        if signals.get('option_groups', 0) >= 3:
            score += 0.15
        elif signals.get('option_groups', 0) >= 2:
            score += 0.10
        
        if signals.get('price_variants', 0) >= 5:
            score += 0.15
        elif signals.get('price_variants', 0) >= 3:
            score += 0.10
        
        return min(score, 1.0)
    
    def should_scrape_configurator(self, configurator_info: Dict) -> Tuple[bool, str]:
        """
        Determine if configurator should be scraped based on detection results.
        
        Args:
            configurator_info: Result from has_configurator()
            
        Returns:
            Tuple of (should_scrape, reason)
        """
        if not configurator_info['has_configurator']:
            return False, "no_configurator_detected"
        
        if configurator_info['confidence'] < 0.25:
            return False, "confidence_too_low"
        
        # Scrape both embedded AND external configurators
        # External configurators are just URLs on different domains - we can still scrape them
        if configurator_info['configurator_type'] == 'external':
            if configurator_info['confidence'] >= 0.5:
                return True, "external_configurator_high_confidence"
            return True, "external_configurator_medium_confidence"
        
        # Embedded configurators
        if configurator_info['confidence'] >= 0.5:
            return True, "embedded_configurator_high_confidence"
        
        # Medium confidence - still scrape but note it
        return True, "embedded_configurator_medium_confidence"