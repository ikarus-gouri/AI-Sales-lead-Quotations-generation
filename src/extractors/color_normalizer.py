"""Normalize colors and optionally map to human-friendly names."""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class NormalizedColor:
    """A color with both HEX code and human-friendly name."""
    hex: str
    name: str
    rgb: Tuple[int, int, int]
    percentage: float
    confidence: float  # How confident we are in the name


class ColorNormalizer:
    """
    Normalize extracted colors and map to human-friendly names.
    
    Two-stage approach: 
    1. Rule-based mapping for common colors (fast, deterministic)
    2. LLM-assisted naming for complex/uncommon colors (slower, as needed)
    """
    
    def __init__(self):
        # Common color names (rule-based mapping)
        self.color_map = {
            # Grayscale
            'black': [(0, 0, 0), (30, 30, 30)],
            'charcoal': [(30, 30, 30), (60, 60, 60)],
            'dark gray': [(60, 60, 60), (100, 100, 100)],
            'gray': [(100, 100, 100), (150, 150, 150)],
            'light gray': [(150, 150, 150), (200, 200, 200)],
            'silver': [(190, 190, 190), (220, 220, 220)],
            'white': [(240, 240, 240), (255, 255, 255)],
            
            # Browns (common for wood)
            'dark brown': [(40, 20, 10), (80, 50, 30)],
            'walnut': [(80, 50, 30), (100, 70, 50)],
            'brown': [(100, 60, 30), (140, 90, 60)],
            'medium brown': [(120, 80, 50), (160, 110, 80)],
            'light brown': [(160, 120, 90), (200, 170, 140)],
            'tan': [(180, 150, 120), (220, 190, 160)],
            'beige': [(220, 200, 180), (240, 230, 210)],
            
            # Wood-specific
            'mahogany': [(90, 40, 30), (120, 60, 40)],
            'cherry': [(140, 70, 50), (180, 100, 70)],
            'oak': [(180, 140, 100), (210, 170, 130)],
            'maple': [(220, 190, 150), (240, 220, 190)],
            'natural wood': [(200, 160, 120), (230, 200, 170)],
            
            # Common colors
            'red': [(200, 0, 0), (255, 80, 80)],
            'blue': [(0, 80, 200), (100, 150, 255)],
            'green': [(0, 150, 50), (100, 200, 100)],
            'yellow': [(200, 200, 0), (255, 255, 100)],
            'orange': [(255, 140, 0), (255, 180, 50)],
            
            # Neutrals
            'cream': [(240, 230, 210), (255, 250, 240)],
            'ivory': [(250, 245, 230), (255, 255, 245)],
            'off-white': [(245, 245, 240), (255, 255, 250)],
        }
    
    def normalize(
        self,
        extracted_colors: List,  # List[ExtractedColor]
        use_llm: bool = False,
        llm_client = None
    ) -> List[NormalizedColor]:
        """
        Normalize extracted colors to human-friendly names.
        
        Args:
            extracted_colors: List of ExtractedColor from ColorSampler
            use_llm: Whether to use LLM for unknown colors
            llm_client: Optional LLM client (e.g., Gemini)
            
        Returns:
            List of NormalizedColor with names
        """
        normalized = []
        unknown_colors = []
        
        # Phase 1: Rule-based naming
        for color in extracted_colors:
            rule_based_name = self._rule_based_naming(color.rgb)
            
            if rule_based_name:
                normalized.append(NormalizedColor(
                    hex=color.hex,
                    name=rule_based_name,
                    rgb=color.rgb,
                    percentage=color.percentage,
                    confidence=0.9  # High confidence for rule-based
                ))
            else:
                unknown_colors.append(color)
        
        # Phase 2: LLM-assisted naming (only if enabled and needed)
        if use_llm and unknown_colors and llm_client:
            llm_names = self._llm_assisted_naming(unknown_colors, llm_client)
            
            for color, name in zip(unknown_colors, llm_names):
                normalized.append(NormalizedColor(
                    hex=color.hex,
                    name=name,
                    rgb=color.rgb,
                    percentage=color.percentage,
                    confidence=0.6  # Medium confidence for LLM
                ))
        else:
            # Fallback: Use hex as name
            for color in unknown_colors:
                normalized.append(NormalizedColor(
                    hex=color.hex,
                    name=color.hex,  # Use hex code as fallback
                    rgb=color.rgb,
                    percentage=color.percentage,
                    confidence=0.3  # Low confidence
                ))
        
        # Sort by percentage (most dominant first)
        normalized.sort(key=lambda c: c.percentage, reverse=True)
        
        return normalized
    
    def _rule_based_naming(self, rgb: Tuple[int, int, int]) -> Optional[str]:
        """
        Map RGB to human-friendly name using rules.
        
        Args:
            rgb: RGB tuple
            
        Returns:
            Color name or None if no match
        """
        # Find best matching color from map
        best_match = None
        min_distance = float('inf')
        
        for color_name, (low_rgb, high_rgb) in self.color_map.items():
            # Check if RGB is within range
            if all(low_rgb[i] <= rgb[i] <= high_rgb[i] for i in range(3)):
                # Calculate distance to center of range
                center = tuple((low_rgb[i] + high_rgb[i]) // 2 for i in range(3))
                distance = self._color_distance(rgb, center)
                
                if distance < min_distance:
                    min_distance = distance
                    best_match = color_name
        
        # Only return if reasonably close
        if min_distance < 50:  # Threshold
            return best_match
        
        return None
    
    def _llm_assisted_naming(
        self,
        colors: List,  # List[ExtractedColor]
        llm_client
    ) -> List[str]:
        """
        Use LLM to suggest names for unknown colors.
        
        Args:
            colors: List of ExtractedColor objects
            llm_client: LLM client (e.g., Gemini API)
            
        Returns:
            List of color names
        """
        # Build prompt
        hex_codes = [color.hex for color in colors]
        
        prompt = f"""You are a color naming expert for product customization.

Given these hex color codes from a product swatch image:
{hex_codes}

Suggest simple, descriptive color names that would be used in e-commerce.

Guidelines:
- Use common names (e.g., "Walnut Brown", "Natural Oak", "Charcoal Gray")
- Be specific for wood finishes (e.g., "Dark Walnut" not just "Brown")
- Keep names under 3 words
- Use title case

Respond ONLY with a JSON array of names in the same order:
["Color Name 1", "Color Name 2", ...]
"""
        
        try:
            # Call LLM (example using Gemini)
            response = llm_client.generate_content(prompt)
            response_text = response.text.strip()
            
            # Parse JSON response
            import json
            # Remove markdown code blocks if present
            response_text = re.sub(r'```json\s*|\s*```', '', response_text)
            
            names = json.loads(response_text)
            
            # Validate and clean
            names = [self._clean_color_name(name) for name in names]
            
            # Ensure we have enough names
            while len(names) < len(colors):
                names.append(f"Color {len(names) + 1}")
            
            return names[:len(colors)]
            
        except Exception as e:
            print(f"  ⚠ LLM naming failed: {e}")
            # Fallback: Generate descriptive names from RGB
            return [self._generate_descriptive_name(color.rgb) for color in colors]
    
    def _clean_color_name(self, name: str) -> str:
        """Clean and validate color name."""
        # Remove quotes, extra whitespace
        name = name.strip('"\'').strip()
        
        # Title case
        name = name.title()
        
        # Limit length
        if len(name) > 30:
            name = name[:30].strip()
        
        return name
    
    def _generate_descriptive_name(self, rgb: Tuple[int, int, int]) -> str:
        """
        Generate descriptive name from RGB values.
        
        Fallback when LLM fails.
        """
        r, g, b = rgb
        
        # Determine base color family
        max_channel = max(r, g, b)
        min_channel = min(r, g, b)
        
        # Grayscale
        if max_channel - min_channel < 30:
            brightness = (r + g + b) // 3
            if brightness < 50:
                return "Dark Gray"
            elif brightness < 100:
                return "Medium Gray"
            elif brightness < 180:
                return "Light Gray"
            else:
                return "Off-White"
        
        # Browns (common for wood)
        if r > g > b and r - b > 40:
            if r < 100:
                return "Dark Brown"
            elif r < 150:
                return "Medium Brown"
            else:
                return "Light Brown"
        
        # Primary colors
        if r > g and r > b:
            return "Red Tone"
        elif g > r and g > b:
            return "Green Tone"
        elif b > r and b > g:
            return "Blue Tone"
        
        # Fallback
        return "Custom Color"
    
    def _color_distance(
        self,
        rgb1: Tuple[int, int, int],
        rgb2: Tuple[int, int, int]
    ) -> float:
        """Calculate Euclidean distance between colors."""
        return sum((c1 - c2) ** 2 for c1, c2 in zip(rgb1, rgb2)) ** 0.5
    
    def group_by_family(self, colors: List[NormalizedColor]) -> Dict[str, List[NormalizedColor]]:
        """
        Group colors by family (e.g., all browns together).
        
        Useful for organizing large color palettes.
        """
        families = {
            'Grayscale': [],
            'Browns & Woods': [],
            'Reds': [],
            'Blues': [],
            'Greens': [],
            'Neutrals': [],
            'Other': []
        }
        
        for color in colors:
            name_lower = color.name.lower()
            
            if any(kw in name_lower for kw in ['gray', 'grey', 'black', 'white', 'charcoal']):
                families['Grayscale'].append(color)
            elif any(kw in name_lower for kw in ['brown', 'walnut', 'oak', 'cherry', 'wood', 'mahogany']):
                families['Browns & Woods'].append(color)
            elif 'red' in name_lower:
                families['Reds'].append(color)
            elif 'blue' in name_lower:
                families['Blues'].append(color)
            elif 'green' in name_lower:
                families['Greens'].append(color)
            elif any(kw in name_lower for kw in ['beige', 'tan', 'cream', 'ivory']):
                families['Neutrals'].append(color)
            else:
                families['Other'].append(color)
        
        # Remove empty families
        return {k: v for k, v in families.items() if v}