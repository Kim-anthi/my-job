"""Config loading: TOML via the stdlib, plus a minimal .env reader.

TOML (not YAML) so the whole worker stays dependency-free on Python 3.11+.
"""
from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PACKAGE_ROOT = Path(__file__).resolve().parent.parent

DEFAULTS: dict[str, Any] = {
    "match": {
        "require_include_in_title": False,
        "min_score": 3,
        "max_age_days": 21,
    },
    "include": {"title_any": [], "anywhere_any": []},
    "exclude": {"title_any": [], "anywhere_any": []},
    "notify": {
        "max_per_run": 12,
        "allow_console_fallback": False,
        "console": False,
        "telegram": {"enabled": True, "pause_seconds": 1.1},
    },
    "storage": {
        "database": "data/radar.db",
        "export_json": "data/latest.json",
        "export_limit": 300,
        "prune_after_days": 120,
    },
    "sources": {},
}


class ConfigError(RuntimeError):
    pass


def default_config_path() -> Path:
    return PACKAGE_ROOT / "config.toml"


def load(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else default_config_path()
    if not config_path.exists():
        raise ConfigError(f"config file not found: {config_path}")
    try:
        with config_path.open("rb") as handle:
            user_config = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{config_path} is not valid TOML: {exc}") from exc

    merged = merge(DEFAULTS, user_config)
    merged["_path"] = str(config_path)
    merged["_root"] = str(config_path.parent)
    return merged


def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge dicts; lists and scalars from ``override`` win outright."""
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = merge(current, value)
        else:
            result[key] = value
    return result


def resolve_path(config: dict[str, Any], value: str) -> Path:
    """Resolve a config path relative to the config file, not the shell's cwd."""
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return Path(config.get("_root", PACKAGE_ROOT)) / candidate


def load_env(path: str | Path | None = None) -> None:
    """Load ``KEY=value`` lines into the environment without overwriting it.

    Real environment variables (CI secrets) always win over the local file.
    """
    env_path = Path(path) if path else PACKAGE_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
    log.debug("loaded env file %s", env_path)
