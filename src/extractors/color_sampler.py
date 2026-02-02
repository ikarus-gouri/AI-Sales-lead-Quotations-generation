"""Extract dominant colors from swatch images using CV techniques."""

import numpy as np
from typing import List, Tuple, Optional
from PIL import Image
from io import BytesIO
import requests
from dataclasses import dataclass
from collections import Counter


@dataclass
class ExtractedColor:
    """A color extracted from an image."""
    rgb: Tuple[int, int, int]
    hex: str
    percentage: float  # Percentage of image
    cluster_size: int  # Number of pixels in cluster


class ColorSampler: 
    """
    Extract dominant colors from swatch images using k-means clustering.
    
    Handles common edge cases:
    - Gradients
    - Text overlays
    - Shadows
    - Noise
    """
    
    def __init__(
        self,
        default_k: int = 8,
        min_percentage: float = 2.0,
        similarity_threshold: int = 30
    ):
        """
        Initialize color sampler.
        
        Args:
            default_k: Default number of color clusters
            min_percentage: Minimum percentage of image to consider a color (filters noise)
            similarity_threshold: RGB distance threshold for deduplication
        """
        self.default_k = default_k
        self.min_percentage = min_percentage
        self.similarity_threshold = similarity_threshold
    
    def extract_colors(
        self,
        image_url: str,
        k: Optional[int] = None,
        timeout: int = 10
    ) -> List[ExtractedColor]:
        """
        Extract dominant colors from image URL.
        
        Args:
            image_url: URL of the image to analyze
            k: Number of clusters (None = auto-detect)
            timeout: Request timeout in seconds
            
        Returns:
            List of ExtractedColor objects, sorted by percentage
        """
        try:
            # Download image
            img = self._download_image(image_url, timeout)
            
            if img is None:
                return []
            
            # Preprocess image
            img = self._preprocess_image(img)
            
            # Determine k if not provided
            if k is None:
                k = self._estimate_k(img)
            
            # Extract colors using k-means
            colors = self._kmeans_colors(img, k)
            
            # Post-process: normalize, deduplicate, filter
            colors = self._normalize_colors(colors)
            colors = self._deduplicate_colors(colors)
            colors = self._filter_noise(colors)
            
            # Sort by percentage (most dominant first)
            colors.sort(key=lambda c: c.percentage, reverse=True)
            
            return colors
            
        except Exception as e:
            print(f"  ⚠ Color extraction failed: {e}")
            return []
    
    def _download_image(self, image_url: str, timeout: int) -> Optional[Image.Image]:
        """Download and open image from URL."""
        try:
            # Handle relative URLs (you may need to pass base_url)
            if image_url.startswith('//'):
                image_url = 'https:' + image_url
            
            response = requests.get(
                image_url,
                timeout=timeout,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            response.raise_for_status()
            
            img = Image.open(BytesIO(response.content))
            
            # Convert to RGB (handles RGBA, grayscale, etc.)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            return img
            
        except Exception as e:
            print(f"  ⚠ Failed to download image: {e}")
            return None
    
    def _preprocess_image(self, img: Image.Image) -> Image.Image:
        """
        Preprocess image for better color extraction.
        
        - Resize to reasonable size (faster processing)
        - Could add: crop center region, remove borders, etc.
        """
        # Resize if too large (maintain aspect ratio)
        max_dimension = 400
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = tuple(int(dim * ratio) for dim in img.size)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        return img
    
    def _estimate_k(self, img: Image.Image) -> int:
        """
        Estimate optimal number of color clusters.
        
        Simple heuristic based on image size and variance.
        """
        # Get pixel data
        pixels = np.array(img).reshape(-1, 3)
        
        # Calculate color variance
        variance = np.var(pixels, axis=0).mean()
        
        # High variance = more colors
        if variance > 2000:
            return 12  # Many distinct colors
        elif variance > 1000:
            return 8   # Normal color palette
        else:
            return 6   # Limited colors
    
    def _kmeans_colors(self, img: Image.Image, k: int) -> List[ExtractedColor]:
        """
        Extract colors using k-means clustering.
        
        Args:
            img: PIL Image
            k: Number of clusters
            
        Returns:
            List of ExtractedColor objects
        """
        try:
            from sklearn.cluster import KMeans
        except ImportError:
            print("  ⚠ scikit-learn not installed, using fallback")
            return self._simple_color_extraction(img, k)
        
        # Convert image to numpy array
        pixels = np.array(img).reshape(-1, 3)
        
        # Remove extreme outliers (very dark or very bright noise)
        pixels = self._filter_outlier_pixels(pixels)
        
        # Run k-means
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
        kmeans.fit(pixels)
        
        # Get cluster centers and labels
        centers = kmeans.cluster_centers_
        labels = kmeans.labels_
        
        # Count pixels in each cluster
        label_counts = Counter(labels)
        total_pixels = len(labels)
        
        # Create ExtractedColor objects
        colors = []
        for i, center in enumerate(centers):
            count = label_counts[i]
            percentage = (count / total_pixels) * 100
            
            rgb = tuple(int(c) for c in center)
            hex_code = self._rgb_to_hex(rgb)
            
            colors.append(ExtractedColor(
                rgb=rgb,
                hex=hex_code,
                percentage=percentage,
                cluster_size=count
            ))
        
        return colors
    
    def _filter_outlier_pixels(self, pixels: np.ndarray) -> np.ndarray:
        """
        Remove extreme outlier pixels (noise, artifacts).
        
        Keeps pixels with brightness between 5% and 95% percentiles.
        """
        brightness = np.mean(pixels, axis=1)
        
        low_threshold = np.percentile(brightness, 5)
        high_threshold = np.percentile(brightness, 95)
        
        mask = (brightness >= low_threshold) & (brightness <= high_threshold)
        
        return pixels[mask]
    
    def _simple_color_extraction(self, img: Image.Image, k: int) -> List[ExtractedColor]:
        """
        Fallback color extraction without sklearn.
        
        Uses median cut algorithm (PIL's quantize).
        """
        # Quantize to k colors
        quantized = img.quantize(colors=k)
        
        # Get color palette
        palette = quantized.getpalette()
        
        # Convert to list of RGB tuples
        colors = []
        for i in range(k):
            rgb = tuple(palette[i*3:(i+1)*3])
            hex_code = self._rgb_to_hex(rgb)
            
            # Estimate percentage (equal distribution)
            percentage = 100.0 / k
            
            colors.append(ExtractedColor(
                rgb=rgb,
                hex=hex_code,
                percentage=percentage,
                cluster_size=0
            ))
        
        return colors
    
    def _normalize_colors(self, colors: List[ExtractedColor]) -> List[ExtractedColor]:
        """
        Normalize RGB values to avoid slight variations.
        
        Rounds to nearest 5 for cleaner hex codes.
        """
        normalized = []
        
        for color in colors:
            # Round to nearest 5
            rgb = tuple(round(c / 5) * 5 for c in color.rgb)
            rgb = tuple(min(255, max(0, c)) for c in rgb)  # Clamp
            
            normalized.append(ExtractedColor(
                rgb=rgb,
                hex=self._rgb_to_hex(rgb),
                percentage=color.percentage,
                cluster_size=color.cluster_size
            ))
        
        return normalized
    
    def _deduplicate_colors(self, colors: List[ExtractedColor]) -> List[ExtractedColor]:
        """
        Merge very similar colors.
        
        Uses RGB distance threshold.
        """
        unique = []
        
        for color in colors:
            # Check if similar to any existing color
            merged = False
            for existing in unique:
                if self._color_distance(color.rgb, existing.rgb) < self.similarity_threshold:
                    # Merge into existing (combine percentages)
                    existing.percentage += color.percentage
                    existing.cluster_size += color.cluster_size
                    merged = True
                    break
            
            if not merged:
                unique.append(color)
        
        return unique
    
    def _filter_noise(self, colors: List[ExtractedColor]) -> List[ExtractedColor]:
        """
        Remove colors that are likely noise.
        
        Filters:
        1. Very small percentage of image
        2. Extreme values (pure black/white from shadows/highlights)
        """
        filtered = []
        
        for color in colors:
            # Filter 1: Too small percentage
            if color.percentage < self.min_percentage:
                continue
            
            # Filter 2: Pure black (shadows)
            if all(c < 10 for c in color.rgb):
                continue
            
            # Filter 3: Pure white (highlights)
            if all(c > 245 for c in color.rgb):
                continue
            
            filtered.append(color)
        
        return filtered
    
    def _rgb_to_hex(self, rgb: Tuple[int, int, int]) -> str:
        """Convert RGB tuple to hex string."""
        return "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])
    
    def _color_distance(self, rgb1: Tuple[int, int, int], rgb2: Tuple[int, int, int]) -> float:
        """
        Calculate Euclidean distance between two colors in RGB space.
        
        Returns:
            Distance value (0 = identical, 441 = max difference)
        """
        return np.sqrt(sum((c1 - c2) ** 2 for c1, c2 in zip(rgb1, rgb2)))
    
    def extract_with_fallback(
        self,
        image_url: str,
        attempts: List[int] = [8, 12, 6]
    ) -> List[ExtractedColor]:
        """
        Extract colors with multiple attempts if first fails.
        
        Args:
            image_url: Image URL
            attempts: List of k values to try
            
        Returns:
            Best color extraction result
        """
        best_result = []
        
        for k in attempts:
            result = self.extract_colors(image_url, k=k)
            
            # Check if result is good
            if len(result) >= 3:  # Got at least 3 colors
                return result
            
            # Keep best attempt
            if len(result) > len(best_result):
                best_result = result
        
        return best_result