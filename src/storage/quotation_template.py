"""Quotation template generator."""

import json
from typing import Dict


class QuotationTemplate:
    """Generate quotation templates for sales team."""
    
    @staticmethod
    def create(catalog: Dict, filepath: str):
        """
        Create a template that sales team can use for quotations.
        
        Args:
            catalog: The product catalog
            filepath: Where to save the template
        """
        template = {
            "products": {},
            "instructions": "Use this template to generate quotations. Select options for each category."
        }
        
        for product_id, product_data in catalog.items():
            template["products"][product_id] = {
                "product_name": product_data['product_name'],
                "base_price": product_data['base_price'],
                "url": product_data['url'],
                "customizations": {}
            }
            
            for category, options in product_data['customizations'].items():
                template["products"][product_id]["customizations"][category] = {
                    "options": [
                        {
                            "label": opt['label'],
                            "price": opt['price'],
                            "image": opt['image'],
                            "selected": False  # Sales team can toggle this
                        }
                        for opt in options
                    ]
                }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Saved quotation template to {filepath}")