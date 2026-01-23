"""Color extraction utility with hex code support."""

import cv2
import numpy as np
from sklearn.cluster import KMeans
from collections import Counter
import requests
from io import BytesIO
import re
from typing import List, Optional, Dict


class ColorExtractor:
    """Extract dominant colors from images and convert to hex codes."""
    
    def __init__(self):
        """Initialize the color extractor."""
        self.color_keywords = [
            'color', 'colour', 'paint', 'exterior', 'finish', 
            'shade', 'palette', 'choose your color', 'select color',
            'pick a color', 'custom color'
        ]
    
    def is_color_selection_category(self, category_name: str) -> bool:
        """
        Check if a category is related to color selection.
        
        Args:
            category_name: The category name to check
            
        Returns:
            True if category is color-related
        """
        category_lower = category_name.lower()
        return any(keyword in category_lower for keyword in self.color_keywords)
    
    def is_color_wheel_image(self, image_url: str, category_name: str = "", alt_text: str = "") -> bool:
        """
        Detect if an image is likely a color wheel/palette/swatch.
        
        Args:
            image_url: URL of the image
            category_name: The category this image belongs to
            alt_text: Alt text of the image
            
        Returns:
            True if image appears to be a color wheel
        """
        # Check category name
        if category_name and self.is_color_selection_category(category_name):
            # Check image URL for color-related keywords
            url_lower = image_url.lower()
            url_indicators = ['color', 'swatch', 'palette', 'wheel', 'spectrum', 'paint']
            
            if any(indicator in url_lower for indicator in url_indicators):
                return True
            
            # Check alt text
            if alt_text:
                alt_lower = alt_text.lower()
                if any(indicator in alt_lower for indicator in url_indicators):
                    return True
        
        return False
    
    def extract_colors_from_url(self, image_url: str, num_colors: int = 12) -> Optional[List[str]]:
        """
        Extract dominant colors from an image URL using KMeans clustering.
        
        Args:
            image_url: URL of the image
            num_colors: Number of dominant colors to extract
            
        Returns:
            List of hex color codes or None if extraction fails
        """
        try:
            # Download image from URL
            response = requests.get(image_url, timeout=10)
            if response.status_code != 200:
                print(f"     ⚠ Failed to fetch image: HTTP {response.status_code}")
                return None
            
            # Decode image
            image_data = np.asarray(bytearray(response.content), dtype=np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
            
            if image is None:
                print(f"     ⚠ Failed to decode image")
                return None
            
            # Convert BGR to RGB
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Reshape image to a 2D array of pixels
            pixels = image.reshape(-1, 3)
            
            # Apply KMeans clustering
            kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init=10)
            labels = kmeans.fit_predict(pixels)
            counts = Counter(labels)
            
            # Sort colors by frequency
            center_colors = kmeans.cluster_centers_
            ordered_colors = [center_colors[i] for i in counts.keys()]
            
            # Convert RGB to Hex
            hex_colors = ['#%02x%02x%02x' % tuple(map(int, color)) for color in ordered_colors]
            
            return hex_colors
            
        except requests.exceptions.RequestException as e:
            print(f"     ⚠ Network error fetching image: {e}")
            return None
        except Exception as e:
            print(f"     ⚠ Error extracting colors: {e}")
            return None
    
    def create_color_options_from_hex(self, hex_colors: List[str], category_name: str = "Color") -> List[Dict]:
        """
        Convert hex colors to option format.
        
        Args:
            hex_colors: List of hex color codes
            category_name: Category name for labeling
            
        Returns:
            List of option dictionaries
        """
        options = []
        
        for i, hex_code in enumerate(hex_colors, 1):
            option = {
                "label": f"Color Option {i}",
                "hex_code": hex_code,
                "price": None,
                "image": None
            }
            options.append(option)
        
        return options


# Integration helper for existing extractors
def enhance_option_with_colors(option_dict: Dict, image_url: str, category_name: str, 
                               color_extractor: ColorExtractor, num_colors: int = 12) -> Dict:
    """
    Enhance an option dictionary with extracted hex colors if it's a color wheel.
    
    Args:
        option_dict: Original option dictionary
        image_url: URL of the option's image
        category_name: Category this option belongs to
        color_extractor: ColorExtractor instance
        num_colors: Number of colors to extract
        
    Returns:
        Enhanced option dictionary with hex_colors field if applicable
    """
    # Check if this is a color wheel image
    alt_text = option_dict.get('label', '')
    
    if color_extractor.is_color_wheel_image(image_url, category_name, alt_text):
        print(f"     🎨 Detected color wheel image for '{category_name}'")
        print(f"        Extracting hex codes from: {image_url[:60]}...")
        
        hex_colors = color_extractor.extract_colors_from_url(image_url, num_colors)
        
        if hex_colors:
            print(f"     ✓ Extracted {len(hex_colors)} colors: {', '.join(hex_colors[:5])}...")
            option_dict['hex_colors'] = hex_colors
            option_dict['is_color_palette'] = True
        else:
            print(f"     ✗ Failed to extract colors")
    
    return option_dict


if __name__ == "__main__":
    # Test the color extractor
    extractor = ColorExtractor()
    
    test_url = "https://i0.wp.com/theraluxe.ca/wp-content/uploads/2025/05/Custom-Colors-Sample.png?w=800&ssl=1"
    
    print("Testing Color Extractor")
    print("=" * 80)
    
    # Test color wheel detection
    print("\n1. Testing color wheel detection:")
    is_color = extractor.is_color_wheel_image(
        test_url, 
        category_name="Choose Your Exterior Color"
    )
    print(f"   Is color wheel: {is_color}")
    
    # Test color extraction
    print("\n2. Extracting colors from image:")
    colors = extractor.extract_colors_from_url(test_url, num_colors=12)
    
    if colors:
        print(f"   ✓ Successfully extracted {len(colors)} colors:")
        for i, color in enumerate(colors, 1):
            print(f"      {i}. {color}")
    else:
        print("   ✗ Failed to extract colors")
    
    # Test option creation
    print("\n3. Creating color options:")
    if colors:
        options = extractor.create_color_options_from_hex(colors, "Exterior Color")
        print(f"   Created {len(options)} color options")
        for opt in options[:3]:
            print(f"      - {opt['label']}: {opt['hex_code']}")