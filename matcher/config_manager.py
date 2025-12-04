
import json
import os
import logging
from typing import Any, Dict

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".fuzzy_matcher_config_v7_4_1.json")
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """Load configuration from JSON file. Returns empty dict on error."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.warning(f"Config file corrupted, using defaults: {e}")
        return {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """Save configuration to JSON file. Logs errors but doesn't raise."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except PermissionError as e:
        logger.error(f"Permission denied saving config: {e}")
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
