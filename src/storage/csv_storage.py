import csv
import io
from typing import Dict, List, Union


class CSVStorage:
    """Save catalog data as CSV (in-memory)."""

    @staticmethod
    def catalog_to_rows(catalog: Union[Dict, List]) -> List[List[str]]:
        """
        Convert catalog to CSV rows, handling both dict and list formats.
        Each row is: [Category, Component, Reference/Image]
        """
        rows = []

        # Handle list format (array of products)
        if isinstance(catalog, list):
            for product in catalog:
                product_name = product.get("product_name") or product.get("name", "Unknown Product")
                product_url = product.get("url", "")

                # Base product row
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    product_url
                ])

                # Customizations
                customizations = product.get("customizations", {})
                if isinstance(customizations, dict):
                    for category, options in customizations.items():
                        if not options:
                            continue

                        # First option
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

                # Base product row
                rows.append([
                    f"Base Model({product_name})",
                    product_name,
                    product_url
                ])

                # Customizations
                customizations = product.get("customizations", {})
                if isinstance(customizations, dict):
                    for category, options in customizations.items():
                        if not options:
                            continue

                        # First option
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
        """
        Convert catalog to a CSV string.
        Returns a CSV-formatted string suitable for download or API response.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        # Header row
        writer.writerow(["Categories", "Component", "References"])
        # Data rows
        writer.writerows(CSVStorage.catalog_to_rows(catalog))
        return output.getvalue()

    @staticmethod
    def save_simple(catalog: Union[Dict, List], file_path: str = None) -> str:
        """
        Backward-compatible method.
        If file_path is provided, writes CSV to file and returns the path.
        Otherwise, returns CSV string (same as `to_csv_string`).
        """
        csv_str = CSVStorage.to_csv_string(catalog)
        if file_path:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                f.write(csv_str)
            return file_path
        return csv_str
