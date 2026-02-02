"""Detect color swatches in product pages using CV-first approach."""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SwatchCandidate:
    """A potential color swatch image."""
    image_url: str
    context_text: str
    confidence: float
    detection_reason: str
    nearby_options: List[str] = None


class ColorSwatchDetector:
    """
    Detect color swatch images in product pages.
    
    Uses multiple signals:
    1. Contextual keywords near images
    2. Image filename patterns
    3. Alt text analysis
    4. Structural patterns (multiple small images in sequence) 
    """
    
    def __init__(self):
        # Context keywords that suggest color options
        self.color_keywords = [
            'color', 'colour', 'colors', 'colours',
            'finish', 'finishes',
            'wood type', 'wood types', 'wood species',
            'stain', 'stains',
            'paint', 'coating',
            'material', 'materials',
            'surface', 'surfaces',
            'tone', 'tones', 'shade', 'shades'
        ]
        
        # Filename patterns that indicate color swatches
        self.filename_patterns = [
            r'color', r'colour', r'swatch', r'palette',
            r'finish', r'wood[-_]', r'stain', r'tone',
            r'sample', r'chip'
        ]
        
        # Color names that might appear in alt text or nearby
        self.common_color_names = [
            'black', 'white', 'gray', 'grey', 'brown',
            'red', 'blue', 'green', 'yellow', 'orange',
            'beige', 'tan', 'cream', 'ivory',
            'walnut', 'oak', 'cherry', 'maple', 'pine',
            'mahogany', 'teak', 'cedar', 'ash',
            'natural', 'dark', 'light', 'medium'
        ]
    
    def detect_swatches(self, markdown: str, all_images: List[str]) -> List[SwatchCandidate]:
        """
        Detect color swatch images in markdown content.
        
        Args:
            markdown: Page content in markdown
            all_images: List of all image URLs found on page
            
        Returns:
            List of SwatchCandidate objects sorted by confidence
        """
        candidates = []
        
        # Method 1: Analyze images with context
        for image_url, context in self._extract_images_with_context(markdown):
            candidate = self._analyze_image(image_url, context, markdown)
            if candidate:
                candidates.append(candidate)
        
        # Method 2: Detect image clusters (multiple small images)
        cluster_candidates = self._detect_image_clusters(markdown, all_images)
        candidates.extend(cluster_candidates)
        
        # Method 3: Filename analysis for missed images
        for image_url in all_images:
            if not any(c.image_url == image_url for c in candidates):
                filename_candidate = self._analyze_filename(image_url)
                if filename_candidate:
                    candidates.append(filename_candidate)
        
        # Deduplicate and sort by confidence
        candidates = self._deduplicate(candidates)
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        
        return candidates
    
    def _extract_images_with_context(self, markdown: str) -> List[Tuple[str, str]]:
        """
        Extract images with surrounding context text.
        
        Returns:
            List of (image_url, context_text) tuples
        """
        lines = markdown.split('\n')
        images_with_context = []
        
        for i, line in enumerate(lines):
            # Find markdown images: ![alt](url)
            image_matches = re.finditer(r'!\[([^\]]*)\]\(([^\)]+)\)', line)
            
            for match in image_matches:
                alt_text = match.group(1)
                image_url = match.group(2)
                
                # Get context: 2 lines before and after
                context_lines = lines[max(0, i-2):min(len(lines), i+3)]
                context = ' '.join(context_lines)
                
                # Include alt text in context
                full_context = f"{alt_text} {context}"
                
                images_with_context.append((image_url, full_context))
        
        return images_with_context
    
    def _analyze_image(
        self,
        image_url: str,
        context: str,
        full_markdown: str
    ) -> Optional[SwatchCandidate]:
        """
        Analyze a single image to determine if it's a color swatch.
        
        Returns:
            SwatchCandidate if likely a swatch, None otherwise
        """
        context_lower = context.lower()
        
        # Calculate confidence score
        confidence = 0.0
        reasons = []
        
        # Signal 1: Color keywords in context (strongest signal)
        color_keyword_matches = sum(
            1 for keyword in self.color_keywords
            if keyword in context_lower
        )
        if color_keyword_matches > 0:
            confidence += min(0.4, color_keyword_matches * 0.2)
            reasons.append(f"color_keywords({color_keyword_matches})")
        
        # Signal 2: Filename suggests color swatch
        filename_lower = image_url.lower()
        filename_matches = sum(
            1 for pattern in self.filename_patterns
            if re.search(pattern, filename_lower)
        )
        if filename_matches > 0:
            confidence += 0.25
            reasons.append(f"filename_pattern")
        
        # Signal 3: Multiple color names in context (strong signal)
        color_name_matches = sum(
            1 for color in self.common_color_names
            if color in context_lower
        )
        if color_name_matches >= 2:
            confidence += 0.3
            reasons.append(f"color_names({color_name_matches})")
        elif color_name_matches == 1:
            confidence += 0.1
            reasons.append(f"color_name(1)")
        
        # Signal 4: Phrases that strongly indicate color selection
        strong_phrases = [
            'choose your color', 'select your color',
            'available colors', 'color options',
            'pick a color', 'available finishes',
            'wood species', 'stain colors'
        ]
        if any(phrase in context_lower for phrase in strong_phrases):
            confidence += 0.35
            reasons.append("strong_phrase")
        
        # Threshold check
        if confidence >= 0.3:
            # Extract nearby options (text that might be color names)
            nearby_options = self._extract_nearby_options(context)
            
            return SwatchCandidate(
                image_url=image_url,
                context_text=context[:200],  # Truncate for storage
                confidence=min(confidence, 1.0),
                detection_reason=' + '.join(reasons),
                nearby_options=nearby_options
            )
        
        return None
    
    def _detect_image_clusters(
        self,
        markdown: str,
        all_images: List[str]
    ) -> List[SwatchCandidate]:
        """
        Detect clusters of multiple small images (typical for swatches).
        
        Color swatches often appear as:
        - Multiple images on consecutive lines
        - Multiple images in a table/list structure
        """
        candidates = []
        lines = markdown.split('\n')
        
        # Look for consecutive lines with images
        consecutive_images = []
        for i, line in enumerate(lines):
            images_in_line = re.findall(r'!\[([^\]]*)\]\(([^\)]+)\)', line)
            
            if images_in_line:
                consecutive_images.append({
                    'line_num': i,
                    'images': images_in_line,
                    'line_text': line
                })
            elif consecutive_images:
                # End of sequence - analyze it
                if len(consecutive_images) >= 3:
                    candidates.extend(
                        self._analyze_image_cluster(consecutive_images, lines)
                    )
                consecutive_images = []
        
        # Check final sequence
        if len(consecutive_images) >= 3:
            candidates.extend(
                self._analyze_image_cluster(consecutive_images, lines)
            )
        
        return candidates
    
    def _analyze_image_cluster(
        self,
        cluster: List[Dict],
        all_lines: List[str]
    ) -> List[SwatchCandidate]:
        """Analyze a cluster of consecutive images."""
        candidates = []
        
        # Get context around cluster
        first_line = cluster[0]['line_num']
        last_line = cluster[-1]['line_num']
        context_start = max(0, first_line - 3)
        context_end = min(len(all_lines), last_line + 3)
        context = ' '.join(all_lines[context_start:context_end])
        
        # Check if context suggests colors
        has_color_context = any(
            keyword in context.lower()
            for keyword in self.color_keywords
        )
        
        if has_color_context:
            # Mark all images in cluster as swatch candidates
            for item in cluster:
                for alt_text, image_url in item['images']:
                    candidates.append(SwatchCandidate(
                        image_url=image_url,
                        context_text=context[:200],
                        confidence=0.6,  # Medium-high for clusters
                        detection_reason=f"image_cluster({len(cluster)}_images)",
                        nearby_options=None
                    ))
        
        return candidates
    
    def _analyze_filename(self, image_url: str) -> Optional[SwatchCandidate]:
        """Analyze image filename for color swatch indicators."""
        filename_lower = image_url.lower()
        
        # Strong filename indicators
        strong_patterns = [
            r'color[-_]swatch',
            r'swatch[-_]',
            r'palette',
            r'color[-_]wheel',
            r'finish[-_]options'
        ]
        
        for pattern in strong_patterns:
            if re.search(pattern, filename_lower):
                return SwatchCandidate(
                    image_url=image_url,
                    context_text=image_url,
                    confidence=0.5,
                    detection_reason="strong_filename",
                    nearby_options=None
                )
        
        return None
    
    def _extract_nearby_options(self, context: str) -> List[str]:
        """
        Extract potential color names from context.
        
        These might be text labels for the swatches.
        """
        options = []
        context_lower = context.lower()
        
        # Look for bullet points with color names
        lines = context.split('\n')
        for line in lines:
            line_stripped = line.strip()
            
            # Bullet points
            if line_stripped.startswith(('-', '*', '•')):
                text = line_stripped.lstrip('-*•').strip()
                
                # Check if it contains color names
                if any(color in text.lower() for color in self.common_color_names):
                    options.append(text[:50])  # Limit length
        
        # Look for comma-separated color names
        if not options:
            sentences = re.split(r'[.!?]', context)
            for sentence in sentences:
                if any(keyword in sentence.lower() for keyword in ['available', 'choose', 'select']):
                    # Extract items after colons or "include"
                    if ':' in sentence:
                        items_text = sentence.split(':')[-1]
                        items = [item.strip() for item in items_text.split(',')]
                        options.extend([item for item in items if len(item) < 30])
        
        return options[:10]  # Limit to 10 options
    
    def _deduplicate(self, candidates: List[SwatchCandidate]) -> List[SwatchCandidate]:
        """Remove duplicate candidates (same image URL)."""
        seen = {}
        unique = []
        
        for candidate in candidates:
            if candidate.image_url not in seen:
                seen[candidate.image_url] = candidate
                unique.append(candidate)
            else:
                # Keep the one with higher confidence
                existing = seen[candidate.image_url]
                if candidate.confidence > existing.confidence:
                    unique.remove(existing)
                    seen[candidate.image_url] = candidate
                    unique.append(candidate)
        
        return unique
    
    def should_extract_colors(self, candidates: List[SwatchCandidate]) -> bool:
        """
        Determine if we should run color extraction on any candidates.
        
        Returns:
            True if at least one high-confidence candidate exists
        """
        return any(c.confidence >= 0.5 for c in candidates)
    
    def get_best_candidate(self, candidates: List[SwatchCandidate]) -> Optional[SwatchCandidate]:
        """Get the single most likely color swatch image."""
        if not candidates:
            return None
        
        # Filter to high confidence
        high_conf = [c for c in candidates if c.confidence >= 0.5]
        
        if high_conf:
            return max(high_conf, key=lambda c: c.confidence)
        
        return None