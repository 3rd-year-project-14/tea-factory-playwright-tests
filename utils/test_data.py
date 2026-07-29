import json
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "test_data.json"


def load_test_data() -> dict:
    """Non-secret fixture values (form inputs, sample payloads) kept out of the
    test files themselves. Real credentials stay in .env / environment variables,
    not here -- see conftest.py."""
    with open(_DATA_FILE) as f:
        return json.load(f)
