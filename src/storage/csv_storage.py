import csv
import io
from typing import Dict, List, Union


class CSVStorage:
    """Save catalog data as CSV (in-memory)."""

    @staticmethod
    def catalog_to_rows(catalog: Union[Dict, List]) -> List[List[str]]:
        """Convert catalog to CSV rows, handling both dict and list formats"""
        rows = []

        # Handle list format (array of products)
        if isinstance(catalog, list):
            for product in catalog:
                product_name = product.get("product_name") or product.get("name", "Unknown Product")
                product_url = product.get("url", "")

                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    product_url
                ])

                customizations = product.get("customizations", {})
                if isinstance(customizations, dict):
                    for category, options in customizations.items():
                        if not options:
                            continue

                        # First option in category
                        rows.append([
                            category,
                            options[0].get("label", ""),
                            options[0].get("image", "")
                        ])

                        # Remaining options
                        for opt in options[1:]:
                            rows.append([
                                "",
                                opt.get("label", ""),
                                opt.get("image", "")
                            ])

        # Handle dict format (keyed by product ID)
        elif isinstance(catalog, dict):
            for product_id, product in catalog.items():
                product_name = product.get("product_name") or product.get("name", "Unknown Product")
                product_url = product.get("url", "")

                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    product_url
                ])

                customizations = product.get("customizations", {})
                if isinstance(customizations, dict):
                    for category, options in customizations.items():
                        if not options:
                            continue

                        # First option in category
                        rows.append([
                            category,
                            options[0].get("label", ""),
                            options[0].get("image", "")
                        ])

                        # Remaining options
                        for opt in options[1:]:
                            rows.append([
                                "",
                                opt.get("label", ""),
                                opt.get("image", "")
                            ])

        return rows

    @staticmethod
    def to_csv_string(catalog: Union[Dict, List]) -> str:
        """Convert catalog to CSV string"""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Categories", "Component", "References"])
        writer.writerows(CSVStorage.catalog_to_rows(catalog))
        return output.getvalue()