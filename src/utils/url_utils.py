"""URL manipulation utilities."""

from urllib.parse import urljoin, urlparse
from typing import Set


class URLUtils:
    """Utilities for URL manipulation and validation."""
    
    # File extensions to skip
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp'}
    MEDIA_EXTENSIONS = {'.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mp3', '.wav'}
    DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar'}
    SKIP_EXTENSIONS = IMAGE_EXTENSIONS | MEDIA_EXTENSIONS | DOCUMENT_EXTENSIONS
    
    @staticmethod
    def is_same_domain(url1: str, url2: str) -> bool:
        """Check if two URLs are from the same domain."""
        return urlparse(url1).netloc == urlparse(url2).netloc
    
    @staticmethod
    def clean_url(url: str) -> str:
        """
        Clean URL by removing fragments and query parameters.
        
        Args:
            url: The URL to clean
            
        Returns:
            Cleaned URL
        """
        return url.split('#')[0].split('?')[0]
    
    @staticmethod
    def make_absolute(url: str, base_url: str) -> str:
        """
        Convert relative URL to absolute URL.
        
        Args:
            url: The URL (relative or absolute)
            base_url: The base URL
            
        Returns:
            Absolute URL
        """
        if not url.startswith('http'):
            return urljoin(base_url, url)
        return url
    
    @staticmethod
    def is_valid_url(url: str) -> bool:
        """
        Check if URL is valid and not an anchor or mailto link.
        
        Args:
            url: The URL to validate
            
        Returns:
            True if valid, False otherwise
        """
        if url.startswith('#') or url.startswith('mailto:'):
            return False
        return True
    
    @staticmethod
    def is_media_file(url: str) -> bool:
        """
        Check if URL points to a media file (image, video, document).
        
        Args:
            url: The URL to check
            
        Returns:
            True if media file, False otherwise
        """
        # Parse URL and get the path
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check if path ends with any media extension
        for ext in URLUtils.SKIP_EXTENSIONS:
            if path.endswith(ext):
                return True
        
        # Also check for common media directory patterns
        media_patterns = ['/wp-content/uploads/', '/images/', '/media/', '/assets/']
        for pattern in media_patterns:
            if pattern in path and any(path.endswith(ext) for ext in URLUtils.SKIP_EXTENSIONS):
                return True
        
        return False
    
    @staticmethod
    def should_crawl(url: str) -> bool:
        """
        Determine if a URL should be crawled.
        
        Args:
            url: The URL to check
            
        Returns:
            True if should crawl, False otherwise
        """
        # Skip invalid URLs
        if not URLUtils.is_valid_url(url):
            return False
        
        # Skip media files
        if URLUtils.is_media_file(url):
            return False
        
        # Skip common non-page URLs
        skip_patterns = [
            '/feed/',
            '/rss/',
            '/wp-json/',
            '/xmlrpc.php',
            '/wp-login.php',
            '/wp-admin/',
        ]
        
        url_lower = url.lower()
        for pattern in skip_patterns:
            if pattern in url_lower:
                return False
        
        return True
    
    @staticmethod
    def get_path_segment(url: str, segment: int = -1) -> str:
        """
        Get a specific path segment from URL.
        
        Args:
            url: The URL
            segment: Which segment to get (default: last)
            
        Returns:
            Path segment
        """
        path = urlparse(url).path
        segments = [s for s in path.split('/') if s]
        if segments:
            return segments[segment]
        return ""