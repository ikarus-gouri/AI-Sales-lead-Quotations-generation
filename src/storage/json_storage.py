"""JSON storage for catalog data."""

import json
from typing import Dict


class JSONStorage:
    """Save and load catalog data as JSON."""
    
    @staticmethod
    def save(catalog: Dict, filepath: str):
        """
        Save catalog to JSON file.
        
        Args:
            catalog: The catalog data
            filepath: Path to save the file
        """
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*80}")
        print(f"✓ Saved catalog to {filepath}")
        print(f"{'='*80}\n")
    
    @staticmethod
    def load(filepath: str) -> Dict:
        """
        Load catalog from JSON file.
        
        Args:
            filepath: Path to the JSON file
            
        Returns:
            Catalog data
        """
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)