"""CSV storage for catalog data."""

import csv
from typing import Dict, List


class CSVStorage:
    """Save catalog data as CSV files."""
    
    @staticmethod
    def catalog_to_rows(catalog: Dict) -> List[List[str]]:
        """
        Convert product catalog to CSV rows format:
        Categories | Component | References
        """
        rows = []
        
        for product_id, product_data in catalog.items():
            product_name = product_data['product_name']
            product_url = product_data['url']
            
            # Add product header row
            rows.append([f"Base Model({product_name})", product_name, product_url])
            
            # Add each customization category
            for category, options in product_data['customizations'].items():
                # First option in category includes category name
                if options:
                    first_option = options[0]
                    rows.append([
                        category,
                        first_option['label'],
                        first_option['image'] or ''
                    ])
                    
                    # Remaining options have empty category cell
                    for option in options[1:]:
                        rows.append([
                            '',
                            option['label'],
                            option['image'] or ''
                        ])
        
        return rows
    
    @staticmethod
    def save_simple(catalog: Dict, filepath: str):
        """Save catalog as simple CSV."""
        rows = CSVStorage.catalog_to_rows(catalog)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Categories', 'Component', 'References'])
            writer.writerows(rows)
        
        print(f"✓ Saved {len(rows)} rows to {filepath}")
    
    @staticmethod
    def save_with_prices(catalog: Dict, filepath: str):
        """
        Save in a format with prices and additional metadata.
        """
        rows = []
        
        for product_id, product_data in catalog.items():
            product_name = product_data['product_name']
            base_price = product_data['base_price'] or 'N/A'
            product_url = product_data['url']
            
            # Product header
            rows.append([
                f"Base Model({product_name})",
                product_name,
                base_price,
                product_url,
                ''  # Notes column
            ])
            
            # Customization categories
            for category, options in product_data['customizations'].items():
                for i, option in enumerate(options):
                    rows.append([
                        category if i == 0 else '',
                        option['label'],
                        option['price'] or '',
                        option['image'] or '',
                        f"Category: {category}"
                    ])
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Categories', 'Component', 'Price', 'References', 'Notes'])
            writer.writerows(rows)
        
        print(f"✓ Saved {len(rows)} rows to {filepath} (with prices)")