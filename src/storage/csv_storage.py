import csv
import io
from typing import Dict, List


class CSVStorage:
    """Save catalog data as CSV (in-memory)."""

    @staticmethod
    def catalog_to_rows(catalog: Dict) -> List[List[str]]:
        rows = []

        for _, product in catalog.items():
            product_name = product.get("product_name")
            product_url = product.get("url")

            rows.append([
                f"Base Model({product_name})",
                product_name,
                product_url
            ])

            for category, options in product.get("customizations", {}).items():
                if not options:
                    continue

                rows.append([
                    category,
                    options[0]["label"],
                    options[0].get("image", "")
                ])

                for opt in options[1:]:
                    rows.append([
                        "",
                        opt["label"],
                        opt.get("image", "")
                    ])

        return rows

    @staticmethod
    def to_csv_string(catalog: Dict) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Categories", "Component", "References"])
        writer.writerows(CSVStorage.catalog_to_rows(catalog))
        return output.getvalue()
