from __future__ import annotations

import os
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml

from constraint_scanner.config.models import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.local.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config" / "settings.example.yaml"
DEFAULT_ENV_FILE_PATH = PROJECT_ROOT / ".env"
SETTINGS_FILE_ENV = "CONSTRAINT_SCANNER_SETTINGS_FILE"
SECRET_FIELDS = {
    "database": {"password", "url"},
    "polymarket": {"private_key", "api_key", "api_secret", "api_passphrase"},
}


def _normalize_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _read_yaml_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None or not config_path.exists():
        return {}

    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        msg = f"Expected mapping at top level of config file: {config_path}"
        raise ValueError(msg)
    return loaded


def _read_env_file(env_file_path: Path | None) -> dict[str, str]:
    if env_file_path is None or not env_file_path.exists():
        return {}

    parsed: dict[str, str] = {}
    for raw_line in env_file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        parsed[key] = value

    return parsed


def _strip_yaml_secrets(raw: Mapping[str, Any]) -> dict[str, Any]:
    clean = deepcopy(dict(raw))
    for section_name, secret_names in SECRET_FIELDS.items():
        section_data = clean.get(section_name)
        if not isinstance(section_data, dict):
            continue
        for secret_name in secret_names:
            section_data.pop(secret_name, None)
    return clean


def _apply_env_overrides(raw: Mapping[str, Any], environ: Mapping[str, str]) -> dict[str, Any]:
    merged = deepcopy(dict(raw))
    defaults = Settings()

    for section_name, section_value in defaults.model_dump(mode="python").items():
        if not isinstance(section_value, dict):
            continue

        current_section = dict(merged.get(section_name) or {})
        for field_name in section_value:
            env_name = f"CONSTRAINT_SCANNER_{section_name.upper()}_{field_name.upper()}"
            env_value = environ.get(env_name)
            if env_value is not None and env_value != "":
                current_section[field_name] = env_value

        if current_section:
            merged[section_name] = current_section

    return merged


def _resolve_config_path(
    config_path: str | Path | None,
    environ: Mapping[str, str],
) -> Path | None:
    if config_path is not None:
        return _normalize_path(config_path)

    env_path = environ.get(SETTINGS_FILE_ENV)
    if env_path:
        return _normalize_path(env_path)

    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if EXAMPLE_CONFIG_PATH.exists():
        return EXAMPLE_CONFIG_PATH
    return None


def load_settings(
    config_path: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    active_environ = (
        {**_read_env_file(DEFAULT_ENV_FILE_PATH), **os.environ}
        if environ is None
        else dict(environ)
    )
    resolved_path = _resolve_config_path(config_path, active_environ)
    raw_yaml = _read_yaml_config(resolved_path)
    raw_without_secrets = _strip_yaml_secrets(raw_yaml)
    merged = _apply_env_overrides(raw_without_secrets, active_environ)
    return Settings.model_validate(merged)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
