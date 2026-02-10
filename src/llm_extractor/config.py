"""Configuration loader for the LLM extractor."""

from pathlib import Path

import yaml

_MODULE_DIR = Path(__file__).parent
_CONFIG_PATH = _MODULE_DIR / "config.yaml"
_TEMPLATE_PATH = _MODULE_DIR / "config.yaml.template"


def load_config() -> dict:
    """Load configuration from config.yaml.

    :returns: Parsed config dict.
    :raises FileNotFoundError: If config.yaml is missing.
    """
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Config not found: {_CONFIG_PATH}\n  cp {_TEMPLATE_PATH} {_CONFIG_PATH}"
        )
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
