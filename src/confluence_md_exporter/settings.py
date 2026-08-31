"""Load and validate launch configuration from the environment and CLI overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

ALLOWED_AUTH_TYPES = frozenset({"basic", "bearer"})
ALLOWED_EDITION = "datacenter"
ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
TRUE_VALUES = frozenset({"true"})
FALSE_VALUES = frozenset({"false"})


class ConfigError(Exception):
    """Impossible start: configuration is not usable."""


@dataclass(frozen=True)
class Settings:
    confluence_base_url: str
    confluence_edition: str
    confluence_auth_type: str
    confluence_token: str
    confluence_username: str | None
    confluence_verify_ssl: bool
    confluence_timeout_seconds: int
    confluence_max_retries: int
    export_output_dir: str
    export_input_file: str
    export_concurrency: int
    export_force_refresh: bool
    log_level: str


def load_settings(
    environ: Mapping[str, str],
    *,
    input_file: str | None = None,
    output_dir: str | None = None,
    force_refresh: bool | None = None,
) -> Settings:
    edition = _optional(environ, "CONFLUENCE_EDITION", ALLOWED_EDITION)
    if edition != ALLOWED_EDITION:
        raise ConfigError("CONFLUENCE_EDITION must be 'datacenter'")

    auth_type = _required(environ, "CONFLUENCE_AUTH_TYPE").lower()
    if auth_type not in ALLOWED_AUTH_TYPES:
        raise ConfigError("CONFLUENCE_AUTH_TYPE must be 'basic' or 'bearer'")

    token = _required(environ, "CONFLUENCE_TOKEN")
    username = _optional(environ, "CONFLUENCE_USERNAME", "") or None
    if auth_type == "basic" and username is None:
        raise ConfigError("CONFLUENCE_USERNAME is required when CONFLUENCE_AUTH_TYPE is 'basic'")

    base_url = _normalize_base_url(_required(environ, "CONFLUENCE_BASE_URL"))

    verify_ssl = _boolean(environ, "CONFLUENCE_VERIFY_SSL", default=True)
    timeout_seconds = _int(environ, "CONFLUENCE_TIMEOUT_SECONDS", default=30, minimum=1)
    max_retries = _int(environ, "CONFLUENCE_MAX_RETRIES", default=3, minimum=0)

    export_input = input_file if input_file is not None else _optional(
        environ, "EXPORT_INPUT_FILE", "input/urls.txt"
    )
    export_output = output_dir if output_dir is not None else _optional(
        environ, "EXPORT_OUTPUT_DIR", "data"
    )
    if force_refresh is None:
        export_force = _boolean(environ, "EXPORT_FORCE_REFRESH", default=False)
    else:
        export_force = force_refresh

    concurrency = _int(environ, "EXPORT_CONCURRENCY", default=2, minimum=1)
    log_level = _optional(environ, "LOG_LEVEL", "INFO").upper()
    if log_level == "WARN":
        log_level = "WARNING"
    if log_level not in ALLOWED_LOG_LEVELS:
        raise ConfigError("LOG_LEVEL is not a recognised logging level")

    input_path = Path(export_input)
    if not input_path.is_file():
        raise ConfigError(f"input file does not exist: {export_input}")

    return Settings(
        confluence_base_url=base_url,
        confluence_edition=ALLOWED_EDITION,
        confluence_auth_type=auth_type,
        confluence_token=token,
        confluence_username=username,
        confluence_verify_ssl=verify_ssl,
        confluence_timeout_seconds=timeout_seconds,
        confluence_max_retries=max_retries,
        export_output_dir=export_output,
        export_input_file=export_input,
        export_concurrency=concurrency,
        export_force_refresh=export_force,
        log_level=log_level,
    )


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key)
    if value is None or not str(value).strip():
        raise ConfigError(f"{key} is required")
    return str(value).strip()


def _optional(environ: Mapping[str, str], key: str, default: str) -> str:
    value = environ.get(key)
    if value is None or not str(value).strip():
        return default
    return str(value).strip()


def _boolean(environ: Mapping[str, str], key: str, *, default: bool) -> bool:
    value = environ.get(key)
    if value is None or not str(value).strip():
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ConfigError(f"{key} must be 'true' or 'false'")


def _int(environ: Mapping[str, str], key: str, *, default: int, minimum: int) -> int:
    value = environ.get(key)
    if value is None or not str(value).strip():
        return default
    raw = str(value).strip()
    try:
        parsed = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer") from exc
    if parsed < minimum:
        raise ConfigError(f"{key} must be >= {minimum}")
    return parsed


def _normalize_base_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ConfigError("CONFLUENCE_BASE_URL must be an origin (scheme + host + optional port)")
    if parsed.path not in {"",} or parsed.params or parsed.query or parsed.fragment:
        raise ConfigError("CONFLUENCE_BASE_URL must not include a path, query, or fragment")
    if parsed.username or parsed.password:
        raise ConfigError("CONFLUENCE_BASE_URL must not include credentials")
    return f"{parsed.scheme}://{parsed.netloc}"
