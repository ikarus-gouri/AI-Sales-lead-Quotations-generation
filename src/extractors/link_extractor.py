"""Extract links from markdown content."""

import re
from typing import Set
from ..utils.url_utils import URLUtils


class LinkExtractor:
    """Extract and process links from markdown content."""
    
    def __init__(self):
        self.url_utils = URLUtils()
    
    def extract_from_markdown(self, markdown: str, base_url: str) -> Set[str]:
        """
        Extract all links from markdown content.
        
        Args:
            markdown: The markdown content
            base_url: The base URL for making links absolute
             
        Returns:
            Set of cleaned, absolute URLs (excluding images and media)
        """
        links = set()
        
        # Find markdown links: [text](url)
        markdown_links = re.findall(r'\[([^\]]+)\]\(([^\)]+)\)', markdown)
        
        for text, url in markdown_links:
            # Skip invalid URLs
            if not self.url_utils.is_valid_url(url):
                continue
            
            # Make absolute URL
            url = self.url_utils.make_absolute(url, base_url)
            
            # Skip if not from same domain
            if not self.url_utils.is_same_domain(url, base_url):
                continue
            
            # Skip media files and other non-crawlable URLs
            if not self.url_utils.should_crawl(url):
                continue
            
            # Clean URL
            clean_url = self.url_utils.clean_url(url)
            links.add(clean_url)
        
        return links
    
    def extract_image_urls(self, markdown: str) -> Set[str]:
        """
        Extract only image URLs from markdown (for product images).
        
        Args:
            markdown: The markdown content
            
        Returns:
            Set of image URLs
        """
        images = set()
        
        # Find markdown images: ![alt](url)
        image_pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
        matches = re.findall(image_pattern, markdown)
        
        for alt_text, url in matches:
            # Skip tracking pixels and very small images
            if 'pixel' in url.lower() or 'g.gif' in url:
                continue
            images.add(url)
        
        return images