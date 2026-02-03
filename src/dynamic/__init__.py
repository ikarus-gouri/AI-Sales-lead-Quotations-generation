"""Dynamic scraping module (Model-D).

This module provides browser-based extraction for interactive configurators.

Components:
    - browser_engine: Playwright browser automation
    - option_discovery: Interactive control detection
    - interaction_explorer: UI state exploration engine
"""

from .browser_engine import BrowserRunner, BrowserConfig, PlaywrightEngine
from .option_discovery import OptionDiscovery
from .interaction_explorer import InteractionExplorer, UIState

__all__ = [
    'BrowserRunner',
    'BrowserConfig',
    'PlaywrightEngine',
    'OptionDiscovery',
    'InteractionExplorer',
    'UIState'
]
