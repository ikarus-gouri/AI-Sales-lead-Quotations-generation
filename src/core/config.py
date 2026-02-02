"""Configuration management for the scraper.

This module handles all configuration settings for both Model-S (static) and
Model-D (dynamic) scrapers. Configuration can be set via:
    - Command-line arguments (main.py)
    - Environment variables (.env file)
    - Programmatic defaults
"""

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ScraperConfig:
    """Configuration for the web scraper.
    
    This dataclass holds all settings for crawling, scraping, and storage.
    Settings are automatically loaded from environment variables in __post_init__.
    """
    
    # Target website
    base_url: str = "https://casarista.com/"
    
    # Crawling settings 
    max_pages: int = 50
    max_depth: int = 3
    crawl_delay: float = 0.5  # seconds between requests
    
    # Scraping settings
    request_timeout: int = 15
    
    # AI settings
    use_ai_classification: bool = False
    gemini_api_key: Optional[str] = None
    gemini_model: str = "models/gemini-2.0-flash-exp"
    
    # Storage settings
    output_dir: str = "data/catalogs"
    output_filename: str = "product_catalog.json"
    
    # Jina AI settings
    jina_api_url: str = "https://r.jina.ai/"
    
    def __post_init__(self):
        """Initialize configuration from environment variables."""
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY") or 
            os.getenv("GEMINAI_API_KEY")
        )
        
        # Create output directory if it doesn't exist
        os.makedirs(self.output_dir, exist_ok=True)
    
    @property
    def full_output_path(self) -> str:
        """Get the full path for output file."""
        return os.path.join(self.output_dir, self.output_filename)
    
    def validate(self) -> bool:
        """Validate configuration."""
        if self.use_ai_classification and not self.gemini_api_key:
            print("⚠ Warning: AI classification enabled but no API key found")
            return False
        return True