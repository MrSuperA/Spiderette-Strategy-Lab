"""
Configuration management for Spiderette Strategy Lab.

Priority (highest to lowest):
  1. Environment variables: SPIDERETTE_SECTION_KEY (e.g. SPIDERETTE_SERVER_PORT)
  2. Config file: config.toml (project root)
  3. Code defaults (fallback)

Usage:
    from src.utils.config import get_config
    cfg = get_config()
    port = cfg.get("server", "port")  # returns 5679
    port = cfg.get("server", "port", fallback=8080)  # override default
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore[assignment]

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILE = _PROJECT_ROOT / "config.toml"

_config_cache: dict[str, Any] | None = None


def _load_config_file() -> dict[str, Any]:
    """Load config.toml from project root."""
    if tomllib is None:
        return {}
    if not _CONFIG_FILE.exists():
        return {}
    with open(_CONFIG_FILE, "rb") as f:
        return tomllib.load(f)


def _env_overrides() -> dict[str, Any]:
    """Read environment variable overrides.

    Convention: SPIDERETTE_SECTION_KEY=value
    Example: SPIDERETTE_SERVER_PORT=8080 -> config["server"]["port"] = "8080"

    Type coercion: tries int, then float, then bool (true/false), then string.
    """
    prefix = "SPIDERETTE_"
    overrides: dict[str, dict[str, str]] = {}
    for key, val in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix):].lower().split("_", 1)
        if len(parts) != 2:
            continue
        section, field = parts
        overrides.setdefault(section, {})[field] = val

    result: dict[str, Any] = {}
    for section, fields in overrides.items():
        result[section] = {}
        for field, raw_val in fields.items():
            result[section][field] = _coerce(raw_val)
    return result


def _coerce(val: str) -> Any:
    """Try to coerce a string value to int/float/bool."""
    # int
    try:
        return int(val)
    except ValueError:
        pass
    # float
    try:
        return float(val)
    except ValueError:
        pass
    # bool
    if val.lower() in ("true", "yes", "1"):
        return True
    if val.lower() in ("false", "no", "0"):
        return False
    return val


def get_config() -> "Config":
    """Get the global configuration singleton."""
    global _config_cache
    if _config_cache is None:
        file_cfg = _load_config_file()
        env_cfg = _env_overrides()
        merged = _deep_merge(file_cfg, env_cfg)
        _config_cache = Config(merged)
    return _config_cache


def reload_config() -> "Config":
    """Force reload configuration from file + env."""
    global _config_cache
    _config_cache = None
    return get_config()


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base (override wins)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


class Config:
    """Dot-access configuration wrapper.

    Examples:
        cfg = get_config()
        cfg["server"]["port"]          # 5679
        cfg.get("server", "port")       # 5679
        cfg.get("server", "port", 8080) # 5679 (file value wins)
        cfg.server.port                   # 5679 (attribute access)
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getitem__(self, section: str) -> "Section":
        return Section(self._data.get(section, {}))

    def get(self, section: str, key: str, fallback: Any = None) -> Any:
        """Get a config value: config.get("server", "port", fallback=8080)"""
        sec = self._data.get(section, {})
        if key in sec:
            return sec[key]
        return fallback

    def section(self, name: str) -> "Section":
        """Get a section as a Section object."""
        return Section(self._data.get(name, {}))

    def as_dict(self) -> dict[str, Any]:
        """Return raw dict."""
        return dict(self._data)

    def __repr__(self) -> str:
        return "Config(" + repr(self._data) + ")"


class Section:
    """Configuration section with attribute access."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def get(self, key: str, fallback: Any = None) -> Any:
        return self._data.get(key, fallback)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"Config section has no key: {name}")

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return "Section(" + repr(self._data) + ")"
