# src/core/__init__.py
"""Core scraper components."""
import argparse
from .scraper import TheraluxeScraper
from .config import ScraperConfig

__all__ = ['TheraluxeScraper', 'ScraperConfig',]

