import json
from typing import Dict


class QuotationTemplate:
    """Generate quotation template JSON."""

    @staticmethod
    def to_json_string(catalog: Dict) -> str:
        template = {
            "instructions": "Select options to generate quotations",
            "products": {}
        }

        for product_id, product in catalog.items():
            template["products"][product_id] = {
                "product_name": product["product_name"],
                "base_price": product.get("base_price"),
                "url": product["url"],
                "customizations": {}
            }

            for category, options in product.get("customizations", {}).items():
                template["products"][product_id]["customizations"][category] = {
                    "options": [
                        {
                            "label": opt["label"],
                            "price": opt.get("price"),
                            "image": opt.get("image"),
                            "selected": False
                        }
                        for opt in options
                    ]
                }

        return json.dumps(template, indent=2, ensure_ascii=False)