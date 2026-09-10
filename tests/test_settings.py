from __future__ import annotations

from pathlib import Path

import pytest

from confluence_md_exporter.cli import main
from confluence_md_exporter.settings import ConfigError, Settings, load_settings


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    urls = tmp_path / "urls.txt"
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


def test_export_output_dir_defaults_to_output(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["EXPORT_OUTPUT_DIR"]
    settings = load_settings(env)
    assert settings.export_output_dir == "output"


def test_edition_not_datacenter_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="CONFLUENCE_EDITION"):
        load_settings(_env(tmp_path, CONFLUENCE_EDITION="cloud"))


def test_invalid_auth_type_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="CONFLUENCE_AUTH_TYPE"):
        load_settings(_env(tmp_path, CONFLUENCE_AUTH_TYPE="oauth"))


def test_basic_without_username_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="CONFLUENCE_USERNAME"):
        load_settings(_env(tmp_path, CONFLUENCE_AUTH_TYPE="basic"))


def test_missing_required_key_rejected(tmp_path: Path) -> None:
    env = _env(tmp_path)
    del env["CONFLUENCE_TOKEN"]
    with pytest.raises(ConfigError, match="CONFLUENCE_TOKEN"):
        load_settings(env)


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
        argv=["--input", str(other_input), "--output", other_output, "--force-refresh"],
        environ=env,
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )
    assert code == 0
    settings = captured["settings"]
    assert settings.export_input_file == str(other_input)
    assert settings.export_output_dir == other_output
    assert settings.export_force_refresh is True


def test_cli_short_flags_override_env(tmp_path: Path) -> None:
    other_input = tmp_path / "short_input.txt"
    other_input.write_text("", encoding="utf-8")
    other_output = str(tmp_path / "short_out")
    env = _env(tmp_path, EXPORT_FORCE_REFRESH="false")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(other_input), "-o", other_output, "-r"],
        environ=env,
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )
    assert code == 0
    settings = captured["settings"]
    assert settings.export_input_file == str(other_input)
    assert settings.export_output_dir == other_output
    assert settings.export_force_refresh is True


def test_verify_ssl_unrecognised_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="CONFLUENCE_VERIFY_SSL"):
        load_settings(_env(tmp_path, CONFLUENCE_VERIFY_SSL="maybe"))


def test_base_url_rejects_wiki_and_accepts_context_path(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="CONFLUENCE_BASE_URL"):
        load_settings(_env(tmp_path, CONFLUENCE_BASE_URL="https://confluence.example.com/wiki"))
    with pytest.raises(ConfigError, match="CONFLUENCE_BASE_URL"):
        load_settings(_env(tmp_path, CONFLUENCE_BASE_URL="https://confluence.example.com/wiki/foo"))
    settings = load_settings(
        _env(tmp_path, CONFLUENCE_BASE_URL="https://confluence.example.com/confluence/")
    )
    assert settings.confluence_base_url == "https://confluence.example.com/confluence"
    stripped = load_settings(
        _env(tmp_path, CONFLUENCE_BASE_URL="https://confluence.example.com/")
    )
    assert stripped.confluence_base_url == "https://confluence.example.com"
