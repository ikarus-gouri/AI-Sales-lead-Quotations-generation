"""Main color extraction orchestrator - integrates all CV components."""

from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from .swatch_detector import ColorSwatchDetector, SwatchCandidate
from .color_sampler import ColorSampler, ExtractedColor
from .color_normalizer import ColorNormalizer, NormalizedColor


@dataclass
class ColorExtractionResult:
    """Complete result of color extraction process."""
    success: bool
    colors: List[Dict]  # List of color dicts {hex, name, percentage}
    source_image: str
    method: str  # "cv_extraction", "text_only", "failed"
    confidence: float
    detection_reason: str
    error: Optional[str] = None
     
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class ColorExtractor:
    """
    Main color extraction system - CV-first approach.
    
    Pipeline:
    1. ColorSwatchDetector: Find color swatch images
    2. ColorSampler: Extract HEX codes using k-means
    3. ColorNormalizer: Map to human-friendly names
    
    Usage:
        extractor = ColorExtractor()
        result = extractor.extract(markdown, image_urls)
    """
    
    def __init__(
        self,
        use_llm_naming: bool = False,
        llm_client = None,
        cache_results: bool = True
    ):
        """
        Initialize color extractor.
        
        Args:
            use_llm_naming: Use LLM for color naming (costs tokens, better names)
            llm_client: LLM client for naming (optional)
            cache_results: Cache image → color mappings
        """
        self.detector = ColorSwatchDetector()
        self.sampler = ColorSampler()
        self.normalizer = ColorNormalizer()
        
        self.use_llm_naming = use_llm_naming
        self.llm_client = llm_client
        
        # Cache to avoid reprocessing same images
        self.cache = {} if cache_results else None
        
        # Statistics
        self.stats = {
            'images_processed': 0,
            'colors_extracted': 0,
            'cache_hits': 0,
            'llm_calls': 0
        }
    
    def extract(
        self,
        markdown: str,
        image_urls: List[str],
        category_name: Optional[str] = None
    ) -> Optional[ColorExtractionResult]:
        """
        Extract colors from a product page.
        
        Args:
            markdown: Page content in markdown
            image_urls: All image URLs from page
            category_name: Optional category name (e.g., "Wood Type", "Finish")
            
        Returns:
            ColorExtractionResult or None if no colors found
        """
        # STEP 1: Detect color swatch images
        candidates = self.detector.detect_swatches(markdown, image_urls)
        
        if not candidates:
            return None
        
        # Log detection
        print(f"  🎨 Color Detection:")
        print(f"     Found {len(candidates)} potential swatch images")
        
        # STEP 2: Filter to best candidate(s)
        best_candidate = self.detector.get_best_candidate(candidates)
        
        if not best_candidate:
            return None
        
        print(f"     Best: {best_candidate.image_url}")
        print(f"     Confidence: {best_candidate.confidence:.1%}")
        print(f"     Reason: {best_candidate.detection_reason}")
        
        # STEP 3: Check cache
        if self.cache is not None and best_candidate.image_url in self.cache:
            print(f"     ✓ Using cached color data")
            self.stats['cache_hits'] += 1
            return self.cache[best_candidate.image_url]
        
        # STEP 4: Extract colors from image (CV)
        print(f"     → Extracting colors from image...")
        extracted_colors = self.sampler.extract_colors(best_candidate.image_url)
        
        if not extracted_colors:
            return ColorExtractionResult(
                success=False,
                colors=[],
                source_image=best_candidate.image_url,
                method="failed",
                confidence=0.0,
                detection_reason=best_candidate.detection_reason,
                error="Color extraction failed"
            )
        
        print(f"     ✓ Extracted {len(extracted_colors)} colors")
        self.stats['images_processed'] += 1
        self.stats['colors_extracted'] += len(extracted_colors)
        
        # STEP 5: Normalize and name colors
        normalized_colors = self.normalizer.normalize(
            extracted_colors,
            use_llm=self.use_llm_naming,
            llm_client=self.llm_client
        )
        
        if self.use_llm_naming and self.llm_client:
            self.stats['llm_calls'] += 1
        
        # STEP 6: Build result
        result = ColorExtractionResult(
            success=True,
            colors=[
                {
                    'hex': color.hex,
                    'name': color.name,
                    'rgb': color.rgb,
                    'percentage': round(color.percentage, 1),
                    'confidence': color.confidence
                }
                for color in normalized_colors
            ],
            source_image=best_candidate.image_url,
            method="cv_extraction",
            confidence=best_candidate.confidence,
            detection_reason=best_candidate.detection_reason
        )
        
        # Cache result
        if self.cache is not None:
            self.cache[best_candidate.image_url] = result
        
        # Print summary
        print(f"     Colors found:")
        for color in result.colors[:5]:  # Show top 5
            print(f"       • {color['name']:20} {color['hex']} ({color['percentage']:.1f}%)")
        if len(result.colors) > 5:
            print(f"       ... and {len(result.colors) - 5} more")
        
        return result
    
    def extract_from_multiple_categories(
        self,
        customizations: Dict[str, List[Dict]]
    ) -> Dict[str, List[Dict]]:
        """
        Process multiple customization categories and extract colors where applicable.
        
        Args:
            customizations: Standard customization dict from ProductExtractor
            
        Returns:
            Enhanced customizations with color data embedded
        """
        enhanced = {}
        
        for category, options in customizations.items():
            # Check if this category might have colors
            if self._is_color_category(category):
                print(f"\n  🎨 Processing color category: {category}")
                
                # Try to extract colors from images in this category
                image_urls = [opt['image'] for opt in options if opt.get('image')]
                
                if image_urls:
                    # For now, just mark that colors could be extracted
                    # Full extraction happens separately
                    enhanced[category] = options
                    enhanced[category + '_has_colors'] = True
                else:
                    enhanced[category] = options
            else:
                enhanced[category] = options
        
        return enhanced
    
    def _is_color_category(self, category_name: str) -> bool:
        """Check if category name suggests colors."""
        category_lower = category_name.lower()
        
        color_indicators = [
            'color', 'colour', 'finish', 'wood type',
            'stain', 'paint', 'material', 'tone', 'shade'
        ]
        
        return any(indicator in category_lower for indicator in color_indicators)
    
    def extract_text_colors(
        self,
        options: List[Dict],
        category_name: str
    ) -> List[Dict]:
        """
        Fallback: Extract colors from text labels when no images available.
        
        Example: "Oak - Light Brown" → try to extract "Light Brown"
        
        Args:
            options: List of option dicts with 'label' field
            category_name: Category name for context
            
        Returns:
            Enhanced options with color hints
        """
        enhanced = []
        
        for option in options:
            label = option['label'].lower()
            
            # Simple color name detection
            detected_colors = []
            for color_name in self.normalizer.color_map.keys():
                if color_name in label:
                    detected_colors.append(color_name)
            
            if detected_colors:
                enhanced_option = option.copy()
                enhanced_option['color_hints'] = detected_colors
                enhanced.append(enhanced_option)
            else:
                enhanced.append(option)
        
        return enhanced
    
    def should_extract_colors(
        self,
        markdown: str,
        image_urls: List[str]
    ) -> bool:
        """
        Quick check: Should we attempt color extraction?
        
        Returns:
            True if likely to find colors
        """
        candidates = self.detector.detect_swatches(markdown, image_urls)
        return self.detector.should_extract_colors(candidates)
    
    def print_statistics(self):
        """Print extraction statistics."""
        print(f"\n{'='*60}")
        print("COLOR EXTRACTION STATISTICS")
        print(f"{'='*60}")
        print(f"Images processed: {self.stats['images_processed']}")
        print(f"Colors extracted: {self.stats['colors_extracted']}")
        print(f"Cache hits: {self.stats['cache_hits']}")
        
        if self.use_llm_naming:
            print(f"LLM naming calls: {self.stats['llm_calls']}")
        
        avg_colors = (
            self.stats['colors_extracted'] / self.stats['images_processed']
            if self.stats['images_processed'] > 0 else 0
        )
        print(f"Average colors per image: {avg_colors:.1f}")
        print(f"{'='*60}\n")


class ColorExtractionCache:
    """
    Persistent cache for color extraction results.
    
    Saves image URL → colors mappings to disk.
    """
    
    def __init__(self, cache_file: str = "data/color_cache.json"):
        """
        Initialize cache.
        
        Args:
            cache_file: Path to cache file
        """
        self.cache_file = cache_file
        self.cache = self._load_cache()
    
    def _load_cache(self) -> Dict:
        """Load cache from disk."""
        import json
        import os
        
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠ Failed to load color cache: {e}")
        
        return {}
    
    def save(self):
        """Save cache to disk."""
        import json
        import os
        
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"⚠ Failed to save color cache: {e}")
    
    def get(self, image_url: str) -> Optional[Dict]:
        """Get cached colors for image URL."""
        return self.cache.get(image_url)
    
    def set(self, image_url: str, result: ColorExtractionResult):
        """Cache colors for image URL."""
        self.cache[image_url] = result.to_dict()
    
    def clear(self):
        """Clear cache."""
        self.cache = {}
        self.save()