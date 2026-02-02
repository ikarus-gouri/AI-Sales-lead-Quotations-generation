# src/storage/json_storage.py
import json

class JSONStorage:
    @staticmethod
    def to_json_string(data):
        return json.dumps(data, indent=2)

    @staticmethod
    def save(data, filepath):
        """Save dictionary as JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
 