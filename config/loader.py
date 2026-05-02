from __future__ import annotations

import os
from pathlib import Path

import yaml


_CONFIG_PATH = Path(__file__).parent / "settings.yaml"


def load_config(path: str | Path | None = None) -> dict:
    """Load config from YAML file."""
    config_path = Path(path) if path else _CONFIG_PATH
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config
