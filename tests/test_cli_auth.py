from __future__ import annotations

from pathlib import Path

from confluence_md_exporter.cli import main
from confluence_md_exporter.settings import Settings


def test_cli_api_token_alias_supported(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    try:
        code = main(
            argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-u", "alice", "--api-token", "secret-token"],
            environ={},
            run_export=run_export,
            auth_probe=lambda _settings: None,
        )
    except SystemExit as exc:
        code = exc.code

    assert code == 0, f"Expected exit code 0, got {code}"
    settings = captured["settings"]
    assert settings.confluence_auth_type == "basic"
    assert settings.confluence_username == "alice"
    assert settings.confluence_token == "secret-token"


def test_cli_short_flag_base_url_supported(tmp_path: Path) -> None:
    urls = tmp_path / "ids.txt"
    urls.write_text("12345\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    try:
        code = main(
            argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-b", "https://confluence.example.com"],
            environ={},
            run_export=run_export,
            auth_probe=lambda _settings: None,
        )
    except SystemExit as exc:
        code = exc.code

    assert code == 0, f"Expected exit code 0, got {code}"
    settings = captured["settings"]
    assert settings.confluence_base_url == "https://confluence.example.com"
