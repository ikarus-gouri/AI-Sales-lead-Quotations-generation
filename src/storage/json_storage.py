import json
from typing import Dict


class JSONStorage:
    """Save catalog data as JSON (in-memory)."""

    @staticmethod
    def to_json_string(catalog: Dict) -> str:
        return json.dumps(catalog, indent=2, ensure_ascii=False)
