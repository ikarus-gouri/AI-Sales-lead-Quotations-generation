"""Configuration management for the scraper."""

import os
from dataclasses import dataclass
from typing import Optional

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, just use environment variables
    pass


@dataclass
class ScraperConfig:
    """Configuration for the web scraper."""
    
    # Target website
    base_url: str = "https://eg.com/"
    
    # Crawling settings
    max_pages: int = 50
    max_depth: int = 3
    crawl_delay: float = 0.5  # seconds between requests
    
    # Scraping settings
    request_timeout: int = 15
    
    # AI settings
    use_ai_classification: bool = False
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"
    
    # Storage settings
    output_dir: str = "data/catalogs"
    output_filename: str = "product_catalog.json"
    
    # Jina AI settings
    jina_api_url: str = "https://r.jina.ai/"
    
    # Cache settings
    use_cache: bool = True  # Enable/disable HTTP caching
    
    # Intent-driven LAM settings
    user_intent: Optional[str] = None  # Natural language intent for LAM model
    max_variants_per_model: int = 50   # Max variants to explore per model (LAM guardrail)
    time_budget: int = 300             # Max session duration in seconds (LAM guardrail)
    confidence_threshold: float = 0.7  # Minimum extraction confidence (LAM guardrail)
    
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