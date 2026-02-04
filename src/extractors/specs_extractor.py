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

    # -----------------------------
    # SECTION DEFINITIONS
    # -----------------------------

    SPEC_SECTION_HEADERS = [
        r'specifications?',
        r'technical\s+(?:details|specs|specifications)',
        r'product\s+(?:specs|specifications)',
        r'dimensions?',
        r'materials?',
        r'features?',
        r'description',
        r'read\s*more',
    ]

    FAQ_SECTION_HEADERS = [
        r'faq',
        r'frequently\s+asked\s+questions?',
        r'questions?',
        r'q\s*&\s*a',
    ]

    QUESTION_PREFIXES = (
        'can ', 'do ', 'does ', 'is ', 'are ',
        'what ', 'why ', 'how ', 'when ', 'where ',
    )

    # -----------------------------
    # SPEC KEY PATTERNS
    # -----------------------------

    SPEC_KEY_PATTERNS = [
        r'dimensions?', r'size', r'length', r'width', r'height', r'depth',
        r'diameter', r'weight', r'capacity', r'material', r'finish',
        r'frame', r'power', r'voltage', r'wattage', r'amperage', r'rpm',
        r'motor', r'engine', r'temperature', r'humidity',
        r'certification', r'rating', r'color', r'model', r'sku',
        r'brand', r'manufacturer', r'warranty', r'type'
    ]

    # -----------------------------
    # INIT
    # -----------------------------

    def __init__(self):
        self.compiled_spec_headers = [
            re.compile(rf'^#+\s*{h}\s*:?\s*$', re.I)
            for h in self.SPEC_SECTION_HEADERS
        ]

        self.compiled_faq_headers = [
            re.compile(rf'^#+\s*{h}\s*:?\s*$', re.I)
            for h in self.FAQ_SECTION_HEADERS
        ]

    # -----------------------------
    # PUBLIC API
    # -----------------------------

    def extract_specifications(self, markdown: str) -> Dict[str, str]:
        specs = {}
        for _, section in self._find_spec_sections(markdown):
            specs.update(self._extract_from_lists(section))
            specs.update(self._extract_from_tables(section))
            specs.update(self._extract_inline_specs(section))
        return self._normalize_specifications(specs)

    def extract_specifications_grouped(self, markdown: str) -> List[SpecificationGroup]:
        groups = []
        for title, section in self._find_spec_sections(markdown):
            specs = {}
            specs.update(self._extract_from_lists(section))
            specs.update(self._extract_from_tables(section))
            specs.update(self._extract_inline_specs(section))
            if specs:
                groups.append(SpecificationGroup(title=title, specs=specs))
        return groups

    # -----------------------------
    # SECTION EXTRACTION
    # -----------------------------

    def _find_spec_sections(self, markdown: str) -> List[Tuple[str, str]]:
        sections = []
        lines = markdown.splitlines()
        current_title = None
        current_lines = []
        in_faq = False

        for line in lines:
            if any(p.match(line) for p in self.compiled_faq_headers):
                current_title = None
                current_lines = []
                in_faq = True
                continue

            spec_match = next((p for p in self.compiled_spec_headers if p.match(line)), None)
            if spec_match:
                if current_title and not in_faq:
                    sections.append((current_title, "\n".join(current_lines)))
                current_title = line.lstrip('#').strip()
                current_lines = []
                in_faq = False
                continue

            if current_title and not in_faq:
                if line.startswith('#'):
                    sections.append((current_title, "\n".join(current_lines)))
                    current_title = None
                    current_lines = []
                else:
                    current_lines.append(line)

        if current_title and current_lines and not in_faq:
            sections.append((current_title, "\n".join(current_lines)))

        return sections

    # -----------------------------
    # LIST EXTRACTION
    # -----------------------------

    def _extract_from_lists(self, content: str) -> Dict[str, str]:
        specs = {}
        pattern = r'^[\s*•\-]+(.{2,50}?):\s*(.{1,120})$'

        for line in content.splitlines():
            m = re.match(pattern, line)
            if not m:
                continue

            key = self._normalize_key(m.group(1))
            value = m.group(2).strip().rstrip('.*')

            if self._is_valid_spec(key, value):
                specs[key] = value

        return specs

    # -----------------------------
    # TABLE EXTRACTION
    # -----------------------------

    def _extract_from_tables(self, content: str) -> Dict[str, str]:
        specs = {}
        for line in content.splitlines():
            if '|' not in line or line.strip().startswith('|---'):
                continue

            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) != 2:
                continue

            key = self._normalize_key(parts[0])
            value = parts[1].strip()

            if self._is_valid_spec(key, value):
                specs[key] = value

        return specs

    # -----------------------------
    # INLINE EXTRACTION (STRICT)
    # -----------------------------

    def _extract_inline_specs(self, content: str) -> Dict[str, str]:
        specs = {}
        pattern = r'^\*?\*?([^*\n:]{2,50})\*?\*?\s*:\s*([^\n]{1,120})$'

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            m = re.match(pattern, line)
            if not m:
                continue

            key = self._normalize_key(m.group(1))
            value = m.group(2).strip().rstrip('.*')

            if self._is_valid_spec(key, value):
                specs[key] = value

        return specs

    # -----------------------------
    # VALIDATION & NORMALIZATION
    # -----------------------------

    def _is_valid_spec(self, key: str, value: str) -> bool:
        key_l = key.lower()

        if key_l.startswith(self.QUESTION_PREFIXES):
            return False

        if len(value.split()) > 20:
            return False

        return self._is_likely_spec_key(key)

    def _is_likely_spec_key(self, key: str) -> bool:
        key_l = key.lower()
        return any(re.search(p, key_l) for p in self.SPEC_KEY_PATTERNS)

    def _normalize_key(self, key: str) -> str:
        key = re.sub(r'\*\*?', '', key).strip().rstrip(':')
        return ' '.join(w.capitalize() for w in key.split())

    def _normalize_specifications(self, specs: Dict[str, str]) -> Dict[str, str]:
        cleaned = {}
        for k, v in specs.items():
            if not v or len(v) > 200:
                continue
            v = re.sub(r'<[^>]+>', '', v)
            v = re.sub(r'\s+', ' ', v).strip()
            cleaned[k] = v
        return cleaned

    # -----------------------------
    # UTIL
    # -----------------------------

    def format_specifications(self, specs: Dict[str, str]) -> str:
        if not specs:
            return "No specifications available."
        return "\n".join(f"{k}: {v}" for k, v in sorted(specs.items()))
