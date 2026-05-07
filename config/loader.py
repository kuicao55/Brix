from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_CONFIG_PATH = Path(__file__).parent / "settings.yaml"

# Default layer paths
GLOBAL_CONFIG = Path.home() / ".brix" / "config.yaml"


class ConfigLoader:
    """Layered config loader: global -> project -> local -> env overrides."""

    def __init__(
        self,
        global_path: Path | None = None,
        project_path: Path | None = None,
        local_path: Path | None = None,
        fallback_path: Path | None = None,
    ) -> None:
        self._global_path = global_path or GLOBAL_CONFIG
        self._project_path = project_path
        self._local_path = local_path
        self._fallback_path = fallback_path or _CONFIG_PATH

    def load(self) -> dict[str, Any]:
        """Load and merge config from all layers."""
        merged: dict[str, Any] = {}

        # Layer 1: Global
        self._merge_layer(merged, self._global_path)

        # Layer 2: Project
        if self._project_path:
            self._merge_layer(merged, self._project_path)

        # Layer 3: Local
        if self._local_path:
            self._merge_layer(merged, self._local_path)

        # Fallback: if nothing loaded, use the old config/settings.yaml
        if not merged and self._fallback_path:
            self._merge_layer(merged, self._fallback_path)

        return merged

    def _merge_layer(self, base: dict[str, Any], path: Path) -> None:
        """Deep merge a YAML file into base dict. Silently skips if missing."""
        if not path.exists():
            return
        try:
            with open(path) as f:
                layer = yaml.safe_load(f)
            if isinstance(layer, dict):
                self._deep_merge(base, layer)
        except Exception:
            pass  # Malformed YAML — skip this layer

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> None:
        """Recursively merge override into base."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v


def load_config(path: str | Path | None = None) -> dict:
    """Load config from YAML file (backward-compatible single-file mode).

    When called without arguments, uses the layered ConfigLoader.
    When called with a specific path, loads that single file.

    Raises FileNotFoundError if a custom path does not exist.
    Returns {} for an empty YAML file instead of None.
    """
    if path is not None:
        config_path = Path(path).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config if config is not None else {}

    # No explicit path — use layered loader
    # Detect project .brix/ directory
    cwd = Path.cwd()
    project_brix = cwd / ".brix"
    if project_brix.is_dir():
        loader = ConfigLoader(
            project_path=project_brix / "settings.yaml",
            local_path=project_brix / "settings.local.yaml",
        )
    else:
        # No .brix/ dir — fall back to config/settings.yaml
        loader = ConfigLoader()

    return loader.load()
