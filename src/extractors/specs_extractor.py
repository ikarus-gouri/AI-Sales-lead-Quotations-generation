"""Extract product specifications and technical details from markdown content."""

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field


@dataclass
class SpecificationGroup:
    """Container for a group of related specifications."""
    title: str
    specs: Dict[str, str] = field(default_factory=dict)


class SpecsExtractor:
    """Extract and normalize product specifications from scraped content."""

    # Section headers that typically contain specifications
    SPEC_SECTION_HEADERS = [
        r'specifications?',
        r'technical\s+(?:details|specs|specifications)',
        r'product\s+(?:details|specs|specifications|information)',
        r'details?',
        r'features?',
        r'dimensions?',
        r'about\s+(?:this\s+)?product',
        r'overview',
        r'description',
        r'included\s+features?',
    ]

    # Common specification key patterns
    SPEC_KEY_PATTERNS = [
        # Dimensions
        r'(?:overall\s+)?dimensions?',
        r'(?:product\s+)?size',
        r'length',
        r'width',
        r'height',
        r'depth',
        r'diameter',
        r'clearance',
        r'footprint',
        
        # Weight and Capacity
        r'weight',
        r'capacity',
        r'(?:load\s+)?rating',
        r'payload',
        r'(?:max(?:imum)?\s+)?load',
        r'gvwr',
        r'gross\s+vehicle\s+weight',
        
        # Materials and Construction
        r'material',
        r'construction',
        r'frame',
        r'body',
        r'finish',
        r'coating',
        r'(?:wood\s+)?type',
        r'grade',
        
        # Power and Performance
        r'(?:power\s+)?(?:source|supply)',
        r'voltage',
        r'wattage',
        r'(?:amp(?:erage)?|current)',
        r'(?:horse)?power',
        r'torque',
        r'speed',
        r'rpm',
        r'efficiency',
        
        # Engine/Motor
        r'engine',
        r'motor',
        r'transmission',
        r'drivetrain',
        r'fuel\s+type',
        r'displacement',
        
        # Temperature and Environment
        r'temperature(?:\s+range)?',
        r'humidity',
        r'(?:operating\s+)?environment',
        r'climate\s+zone',
        
        # Certifications and Compliance
        r'certification',
        r'complian(?:ce|t)',
        r'standard',
        r'rating',
        r'class',
        r'grade',
        
        # Other Common Specs
        r'color',
        r'model(?:\s+(?:number|#))?',
        r'sku',
        r'part\s+number',
        r'upc',
        r'brand',
        r'manufacturer',
        r'warranty',
        r'year',
        r'make',
        r'style',
        r'type',
        r'configuration',
    ]

    def __init__(self):
        self.compiled_section_patterns = [
            re.compile(rf'^#+\s*{pattern}\s*:?\s*$', re.IGNORECASE | re.MULTILINE)
            for pattern in self.SPEC_SECTION_HEADERS
        ]
        self.compiled_key_patterns = [
            re.compile(rf'^\s*(?:\*\*)?({pattern})(?:\*\*)?\s*:?\s*$', re.IGNORECASE)
            for pattern in self.SPEC_KEY_PATTERNS
        ]

    # ------------------------------------------------------------------
    # Main extraction methods
    # ------------------------------------------------------------------

    def extract_specifications(self, markdown: str) -> Dict[str, Any]:
        """
        Extract all product specifications from markdown content.
        
        Args:
            markdown: The markdown content to search
            
        Returns:
            Dictionary of specifications organized by category
        """
        specifications = {}
        
        # Try different extraction strategies
        specs_from_sections = self._extract_from_sections(markdown)
        specs_from_lists = self._extract_from_lists(markdown)
        specs_from_tables = self._extract_from_tables(markdown)
        specs_from_inline = self._extract_inline_specs(markdown)
        
        # Merge all extracted specs (sections take priority)
        specifications.update(specs_from_inline)
        specifications.update(specs_from_lists)
        specifications.update(specs_from_tables)
        specifications.update(specs_from_sections)
        
        # Clean up and normalize
        return self._normalize_specifications(specifications)

    def extract_specifications_grouped(self, markdown: str) -> List[SpecificationGroup]:
        """
        Extract specifications grouped by section headers.
        
        Args:
            markdown: The markdown content to search
            
        Returns:
            List of SpecificationGroup objects
        """
        groups = []
        
        # Find specification sections
        sections = self._find_spec_sections(markdown)
        
        for section_title, section_content in sections:
            specs = {}
            
            # Extract from lists
            specs.update(self._extract_from_lists(section_content))
            
            # Extract from tables
            specs.update(self._extract_from_tables(section_content))
            
            # Extract inline
            specs.update(self._extract_inline_specs(section_content))
            
            if specs:
                groups.append(SpecificationGroup(
                    title=section_title,
                    specs=specs
                ))
        
        # If no sections found, create a general group
        if not groups:
            all_specs = self.extract_specifications(markdown)
            if all_specs:
                groups.append(SpecificationGroup(
                    title="Specifications",
                    specs=all_specs
                ))
        
        return groups

    # ------------------------------------------------------------------
    # Section-based extraction
    # ------------------------------------------------------------------

    def _find_spec_sections(self, markdown: str) -> List[Tuple[str, str]]:
        """Find and extract specification sections from markdown."""
        sections = []
        lines = markdown.split('\n')
        current_section = None
        current_content = []
        
        for i, line in enumerate(lines):
            # Check if this line is a section header
            is_header = False
            for pattern in self.compiled_section_patterns:
                if pattern.match(line):
                    # Save previous section if exists
                    if current_section:
                        sections.append((current_section, '\n'.join(current_content)))
                    
                    # Start new section
                    current_section = line.lstrip('#').strip().rstrip(':')
                    current_content = []
                    is_header = True
                    break
            
            if not is_header and current_section:
                # Add to current section content
                # Stop if we hit another major header (but not within the spec section)
                if line.startswith('#') and not line.startswith('###'):
                    # Check if it's another spec header
                    is_spec_header = any(p.match(line) for p in self.compiled_section_patterns)
                    if not is_spec_header:
                        # End current section
                        sections.append((current_section, '\n'.join(current_content)))
                        current_section = None
                        current_content = []
                        continue
                
                current_content.append(line)
        
        # Add last section
        if current_section and current_content:
            sections.append((current_section, '\n'.join(current_content)))
        
        return sections

    def _extract_from_sections(self, markdown: str) -> Dict[str, str]:
        """Extract specifications from dedicated sections."""
        specs = {}
        sections = self._find_spec_sections(markdown)
        
        for section_title, section_content in sections:
            # Extract specs from this section
            section_specs = {}
            section_specs.update(self._extract_from_lists(section_content))
            section_specs.update(self._extract_from_tables(section_content))
            section_specs.update(self._extract_inline_specs(section_content))
            
            specs.update(section_specs)
        
        return specs

    # ------------------------------------------------------------------
    # List-based extraction
    # ------------------------------------------------------------------

    def _extract_from_lists(self, content: str) -> Dict[str, str]:
        """Extract specifications from bullet or numbered lists."""
        specs = {}
        
        # Pattern: - Key: Value or * Key: Value
        # Note: Put - at the end of character class to avoid range interpretation
        list_pattern = r'^[\s*•\-]+(.+?):\s*(.+)$'
        
        for line in content.split('\n'):
            match = re.match(list_pattern, line, re.IGNORECASE)
            if match:
                key = self._normalize_key(match.group(1))
                value = match.group(2).strip()
                
                # Clean up value (remove trailing periods, asterisks)
                value = value.rstrip('.*')
                
                if key and value and len(value) > 0:
                    specs[key] = value
        
        return specs

    # ------------------------------------------------------------------
    # Table-based extraction
    # ------------------------------------------------------------------

    def _extract_from_tables(self, content: str) -> Dict[str, str]:
        """Extract specifications from markdown tables."""
        specs = {}
        
        # Simple table pattern: | Key | Value |
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '|' in line and not line.strip().startswith('|---'):
                parts = [p.strip() for p in line.split('|') if p.strip()]
                
                # Two-column table (Key | Value)
                if len(parts) == 2:
                    key = self._normalize_key(parts[0])
                    value = parts[1].strip()
                    
                    if key and value and not self._is_table_header(key, value):
                        specs[key] = value
        
        return specs

    # ------------------------------------------------------------------
    # Inline extraction
    # ------------------------------------------------------------------

    def _extract_inline_specs(self, content: str) -> Dict[str, str]:
        """Extract specifications from inline text patterns."""
        specs = {}
        
        # Pattern: **Key**: Value or Key: Value on its own line
        inline_pattern = r'^\*?\*?([^*\n:]+)\*?\*?\s*:\s*([^\n]+)$'
        
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            match = re.match(inline_pattern, line, re.IGNORECASE)
            if match:
                key = self._normalize_key(match.group(1))
                value = match.group(2).strip()
                
                # Check if this looks like a spec key
                if self._is_likely_spec_key(key):
                    # Clean value
                    value = value.rstrip('.*')
                    if value and len(value) > 0:
                        specs[key] = value
        
        return specs

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _normalize_key(self, key: str) -> str:
        """Normalize a specification key."""
        # Remove markdown formatting
        key = re.sub(r'\*\*?', '', key)
        key = key.strip()
        
        # Remove trailing colons
        key = key.rstrip(':')
        
        # Capitalize first letter of each word
        key = ' '.join(word.capitalize() for word in key.split())
        
        return key

    def _normalize_specifications(self, specs: Dict[str, str]) -> Dict[str, str]:
        """Clean and normalize the extracted specifications."""
        normalized = {}
        
        for key, value in specs.items():
            # Skip empty or very short values
            if not value or len(value.strip()) < 1:
                continue
            
            # Skip values that are too long (likely not a spec)
            if len(value) > 200:
                continue
            
            # Clean up HTML tags if any
            value = re.sub(r'<[^>]+>', '', value)
            
            # Clean up extra whitespace
            value = re.sub(r'\s+', ' ', value).strip()
            
            # Skip if value is just punctuation
            if re.match(r'^[^\w\d]+$', value):
                continue
            
            normalized[key] = value
        
        return normalized

    def _is_likely_spec_key(self, key: str) -> bool:
        """Check if a key looks like a specification key."""
        key_lower = key.lower()
        
        # Check against known patterns
        for pattern in self.SPEC_KEY_PATTERNS:
            if re.search(pattern, key_lower):
                return True
        
        # Additional heuristics
        # - Not too long (likely not a sentence)
        if len(key) > 50:
            return False
        
        # - Contains spec-related words
        spec_words = ['size', 'weight', 'material', 'type', 'color', 'model', 
                      'capacity', 'power', 'voltage', 'dimensions']
        if any(word in key_lower for word in spec_words):
            return True
        
        return False

    def _is_table_header(self, key: str, value: str) -> bool:
        """Check if a table row is likely a header."""
        header_words = ['specification', 'value', 'description', 'detail', 'property']
        key_lower = key.lower()
        value_lower = value.lower()
        
        return any(word in key_lower for word in header_words) and \
               any(word in value_lower for word in header_words)

    def format_specifications(self, specs: Dict[str, str]) -> str:
        """
        Format specifications as a readable string.
        
        Args:
            specs: Dictionary of specifications
            
        Returns:
            Formatted string
        """
        if not specs:
            return "No specifications available."
        
        lines = []
        for key, value in sorted(specs.items()):
            lines.append(f"{key}: {value}")
        
        return '\n'.join(lines)

    def filter_specifications(
        self, 
        specs: Dict[str, str], 
        categories: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Filter specifications by category keywords.
        
        Args:
            specs: Dictionary of specifications
            categories: List of category keywords (e.g., ['dimension', 'weight'])
            
        Returns:
            Filtered dictionary of specifications
        """
        if not categories:
            return specs
        
        filtered = {}
        categories_lower = [c.lower() for c in categories]
        
        for key, value in specs.items():
            key_lower = key.lower()
            if any(cat in key_lower for cat in categories_lower):
                filtered[key] = value
        
        return filtered
