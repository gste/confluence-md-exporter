from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from confluence_md_exporter.cli import main
from confluence_md_exporter.settings import ConfigError, Settings, load_settings


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    urls = tmp_path / "urls.txt"
    if not urls.exists():
        urls.write_text("", encoding="utf-8")
    env = {
        "CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "CONFLUENCE_AUTH_TYPE": "bearer",
        "CONFLUENCE_TOKEN": "dummy-token",
        "EXPORT_INPUT_FILE": str(urls),
        "EXPORT_OUTPUT_DIR": str(tmp_path / "data"),
    }
    env.update(overrides)
    return env


def test_valid_settings_loaded(tmp_path: Path) -> None:
    settings = load_settings(_env(tmp_path))
    assert settings.confluence_base_url == "https://confluence.example.com"
    assert settings.confluence_edition == "datacenter"
    assert settings.confluence_auth_type == "bearer"
    assert settings.confluence_token == "dummy-token"
    assert settings.confluence_username is None
    assert settings.confluence_verify_ssl is True
    assert settings.confluence_timeout_seconds == 30
    assert settings.confluence_max_retries == 3
    assert settings.export_output_dir == str(tmp_path / "data")
    assert settings.export_input_file == str(tmp_path / "urls.txt")
    assert settings.export_force_refresh is False
    assert settings.log_level == "INFO"


def test_reject_cloud_edition(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="datacenter"):
        load_settings(_env(tmp_path, CONFLUENCE_EDITION="cloud"))


def test_reject_base_url_with_wiki(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="/wiki"):
        load_settings(_env(tmp_path, CONFLUENCE_BASE_URL="https://confluence.example.com/wiki"))


def test_anonymous_default_when_no_token(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["CONFLUENCE_TOKEN"]
    del env["CONFLUENCE_AUTH_TYPE"]
    settings = load_settings(env)
    assert settings.confluence_auth_type == "anonymous"
    assert settings.confluence_token == ""
    assert settings.confluence_username is None


def test_username_and_password_infer_basic(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["CONFLUENCE_AUTH_TYPE"]
    del env["CONFLUENCE_TOKEN"]
    settings = load_settings(env, username="jdoe", password="secret-password")
    assert settings.confluence_auth_type == "basic"
    assert settings.confluence_username == "jdoe"
    assert settings.confluence_token == "secret-password"


def test_username_and_token_collision_raises(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["CONFLUENCE_AUTH_TYPE"]
    with pytest.raises(ConfigError, match="Both username"):
        load_settings(env, username="jdoe", token="pat-1")


def test_token_only_infers_bearer(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["CONFLUENCE_AUTH_TYPE"]
    del env["CONFLUENCE_TOKEN"]
    settings = load_settings(env, token="pat-1")
    assert settings.confluence_auth_type == "bearer"
    assert settings.confluence_token == "pat-1"


def test_base_url_inferred_from_input_urls(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/confluence/pages/viewpage.action?pageId=11\n",
        encoding="utf-8",
    )
    env = {
        "EXPORT_INPUT_FILE": str(urls),
        "EXPORT_OUTPUT_DIR": str(tmp_path / "data"),
    }
    settings = load_settings(env)
    assert settings.confluence_base_url == "https://confluence.example.com/confluence"
    assert settings.confluence_auth_type == "anonymous"


def test_cli_user_password_override_env(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-u", "alice", "-p", "secret"],
        environ={},
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )
    assert code == 0
    settings = captured["settings"]
    assert settings.confluence_auth_type == "basic"
    assert settings.confluence_username == "alice"
    assert settings.confluence_token == "secret"
    assert settings.confluence_base_url == "https://confluence.example.com"


def test_cli_input_output_force_refresh_override_env(tmp_path: Path) -> None:
    other_input = tmp_path / "other.txt"
    other_input.write_text("", encoding="utf-8")
    other_output = str(tmp_path / "out")
    env = _env(
        tmp_path,
        EXPORT_FORCE_REFRESH="false",
    )
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(other_input), "-o", other_output, "--force-refresh"],
        environ=env,
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )
    assert code == 0
    settings = captured["settings"]
    assert settings.export_input_file == str(other_input)
    assert settings.export_output_dir == other_output
    assert settings.export_force_refresh is True


def test_missing_input_file_raises(tmp_path: Path) -> None:
    env = _env(tmp_path, EXPORT_INPUT_FILE=str(tmp_path / "nonexistent.txt"))
    with pytest.raises(ConfigError, match="input file does not exist"):
        load_settings(env)


def test_invalid_integer_setting_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="must be an integer"):
        load_settings(_env(tmp_path, CONFLUENCE_TIMEOUT_SECONDS="not-an-int"))


def test_invalid_boolean_setting_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="must be 'true' or 'false'"):
        load_settings(_env(tmp_path, CONFLUENCE_VERIFY_SSL="maybe"))


def test_invalid_log_level_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        load_settings(_env(tmp_path, LOG_LEVEL="VERBOSE_INVALID"))
