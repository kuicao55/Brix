from __future__ import annotations

from pathlib import Path

import yaml


_CONFIG_PATH = Path(__file__).parent / "settings.yaml"


def load_config(path: str | Path | None = None) -> dict:
    """Load config from YAML file.

    Raises FileNotFoundError if a custom path does not exist.
    Returns {} for an empty YAML file instead of None.
    """
    config_path = Path(path).resolve() if path else _CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config if config is not None else {}
