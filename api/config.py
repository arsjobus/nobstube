from pathlib import Path
from typing import Any
import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_FILE = BASE_DIR / "config" / "rules.yaml"

DEFAULT_RULES = {
    "exclusions": {},
    "preferences": {},
    "settings": {
        "results_per_page": 10,
        "candidates_per_source": 10,
        "minimum_duration_seconds": 30,
        "maximum_duration_seconds": 9000,
        "preferred_language": "en",
        "exclude_non_preferred_language": False,
    },
}

def load_rules() -> dict[str, Any]:
    """Load the single canonical YAML rules configuration."""
    if not RULES_FILE.exists():
        return DEFAULT_RULES.copy()
    try:
        with RULES_FILE.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        if not isinstance(loaded, dict):
            return DEFAULT_RULES.copy()
        return {
            "exclusions": loaded.get("exclusions") or {},
            "preferences": loaded.get("preferences") or {},
            "settings": {**DEFAULT_RULES["settings"], **(loaded.get("settings") or {})},
        }
    except (OSError, yaml.YAMLError):
        return DEFAULT_RULES.copy()
