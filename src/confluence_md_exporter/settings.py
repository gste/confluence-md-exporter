"""Load and validate launch configuration from the environment and CLI overlays."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

ALLOWED_AUTH_TYPES = frozenset({"anonymous", "basic", "bearer"})
ALLOWED_EDITION = "datacenter"
ALLOWED_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
TRUE_VALUES = frozenset({"true"})
FALSE_VALUES = frozenset({"false"})


class ConfigError(Exception):
    """Impossible start: configuration is not usable."""


class AuthError(ConfigError):
    """Identity probe did not confirm the operator; the process must not fetch pages."""


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
    export_force_refresh: bool
    log_level: str


def load_settings(
    environ: Mapping[str, str],
    *,
    input_file: str | None = None,
    output_dir: str | None = None,
    force_refresh: bool | None = None,
    base_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
    token: str | None = None,
    log_level: str | None = None,
) -> Settings:
    edition = _optional(environ, "CONFLUENCE_EDITION", ALLOWED_EDITION)
    if edition != ALLOWED_EDITION:
        raise ConfigError("CONFLUENCE_EDITION must be 'datacenter'")

    token_value = _first(token, environ.get("CONFLUENCE_TOKEN"))
    username_value = _first(username, environ.get("CONFLUENCE_USERNAME"))
    password_value = _first(password, environ.get("CONFLUENCE_PASSWORD"))

    if username_value and token_value:
        raise ConfigError(
            "Both username (-u/--username) and token (-t/--token) were provided. "
            "Personal Access Tokens (-t) do not require a username; "
            "if using Basic Auth, pass password with -p/--password instead."
        )

    if username_value and not password_value:
        raise ConfigError(
            "Password (-p/--password or CONFLUENCE_PASSWORD) is required when username is provided."
        )

    auth_type = _resolve_auth_type(
        environ.get("CONFLUENCE_AUTH_TYPE"),
        username=username_value,
        password=password_value,
        token=token_value,
    )

    if auth_type == "basic":
        if not username_value:
            raise ConfigError("CONFLUENCE_USERNAME is required when CONFLUENCE_AUTH_TYPE is 'basic'")
        if not password_value:
            raise ConfigError("CONFLUENCE_PASSWORD is required when CONFLUENCE_AUTH_TYPE is 'basic'")
        secret_value = password_value
    elif auth_type == "bearer":
        if not token_value:
            raise ConfigError("CONFLUENCE_TOKEN is required when CONFLUENCE_AUTH_TYPE is 'bearer'")
        secret_value = token_value
    else:
        secret_value = ""

    verify_ssl = _boolean(environ, "CONFLUENCE_VERIFY_SSL", default=True)
    timeout_seconds = _int(environ, "CONFLUENCE_TIMEOUT_SECONDS", default=30, minimum=1)
    max_retries = _int(environ, "CONFLUENCE_MAX_RETRIES", default=3, minimum=0)

    export_input = input_file if input_file is not None else _optional(
        environ, "EXPORT_INPUT_FILE", "input/urls.txt"
    )
    export_output = output_dir if output_dir is not None else _optional(
        environ, "EXPORT_OUTPUT_DIR", "output"
    )
    if force_refresh is None:
        export_force = _boolean(environ, "EXPORT_FORCE_REFRESH", default=False)
    else:
        export_force = force_refresh

    resolved_log_level = _first(log_level, environ.get("LOG_LEVEL"), "INFO")
    assert resolved_log_level is not None
    resolved_log_level = resolved_log_level.upper()
    if resolved_log_level == "WARN":
        resolved_log_level = "WARNING"
    if resolved_log_level not in ALLOWED_LOG_LEVELS:
        raise ConfigError("LOG_LEVEL is not a recognised logging level")

    input_path = Path(export_input)
    if not input_path.is_file():
        raise ConfigError(f"input file does not exist: {export_input}")

    explicit_base = _first(base_url, environ.get("CONFLUENCE_BASE_URL"))
    if explicit_base:
        resolved_base = _normalize_base_url(explicit_base)
    else:
        from confluence_md_exporter.url_resolver import infer_base_url

        resolved_base = infer_base_url(export_input)

    return Settings(
        confluence_base_url=resolved_base,
        confluence_edition=ALLOWED_EDITION,
        confluence_auth_type=auth_type,
        confluence_token=secret_value,
        confluence_username=username_value,
        confluence_verify_ssl=verify_ssl,
        confluence_timeout_seconds=timeout_seconds,
        confluence_max_retries=max_retries,
        export_output_dir=export_output,
        export_input_file=export_input,
        export_force_refresh=export_force,
        log_level=resolved_log_level,
    )


def _first(*values: str | None) -> str | None:
    for value in values:
        if value is None:
            continue
        stripped = str(value).strip()
        if stripped:
            return stripped
    return None


def _resolve_auth_type(
    explicit: str | None,
    *,
    username: str | None,
    password: str | None,
    token: str | None,
) -> str:
    if explicit is not None and str(explicit).strip():
        auth_type = str(explicit).strip().lower()
        if auth_type not in ALLOWED_AUTH_TYPES:
            raise ConfigError("CONFLUENCE_AUTH_TYPE must be 'anonymous', 'basic' or 'bearer'")
        return auth_type
    if username and password:
        return "basic"
    if token:
        return "bearer"
    return "anonymous"


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
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc
    if parsed < minimum:
        raise ConfigError(f"{key} must be at least {minimum}, got {parsed}")
    return parsed


def _normalize_base_url(value: str) -> str:
    stripped = value.strip().rstrip("/")
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"}:
        raise ConfigError(f"CONFLUENCE_BASE_URL scheme must be http or https, got {stripped!r}")
    if not parsed.netloc:
        raise ConfigError(f"CONFLUENCE_BASE_URL host is missing in {stripped!r}")
    path = parsed.path or ""
    if path == "/wiki" or path.startswith("/wiki/") or "/wiki" in path.split("/"):
        raise ConfigError(f"CONFLUENCE_BASE_URL must not contain /wiki: {stripped!r}")
    return stripped
