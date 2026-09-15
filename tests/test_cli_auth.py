from __future__ import annotations

from pathlib import Path
import pytest

from confluence_md_exporter.cli import main, parse_cli
from confluence_md_exporter.settings import Settings


def test_cli_bearer_token_supported(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-t", "pat-secret-token"],
        environ={},
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )

    assert code == 0
    settings = captured["settings"]
    assert settings.confluence_auth_type == "bearer"
    assert settings.confluence_username is None
    assert settings.confluence_token == "pat-secret-token"


def test_cli_password_flag_supported(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-u", "alice", "-p", "secret-pass"],
        environ={},
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )

    assert code == 0
    settings = captured["settings"]
    assert settings.confluence_auth_type == "basic"
    assert settings.confluence_username == "alice"
    assert settings.confluence_token == "secret-pass"


def test_cli_username_and_token_collision_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-u", "alice", "-t", "pat-token"],
        environ={},
        run_export=lambda _s: None,
        auth_probe=lambda _settings: None,
    )

    assert code == 2
    err = capsys.readouterr().err
    assert "token" in err.lower() or "collision" in err.lower() or "password" in err.lower()


def test_cli_username_without_password_fails(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-u", "alice"],
        environ={},
        run_export=lambda _s: None,
        auth_probe=lambda _settings: None,
    )

    assert code == 2


def test_cli_verbose_flag_supported(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    captured: dict[str, Settings] = {}

    def run_export(settings: Settings) -> None:
        captured["settings"] = settings

    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "out"), "-v"],
        environ={},
        run_export=run_export,
        auth_probe=lambda _settings: None,
    )

    assert code == 0
    settings = captured["settings"]
    assert settings.log_level == "DEBUG"


def test_cli_help_flags(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc1:
        parse_cli(["-h"])
    assert exc1.value.code == 0
    help_short = capsys.readouterr().out

    with pytest.raises(SystemExit) as exc2:
        parse_cli(["--help"])
    assert exc2.value.code == 0
    help_long = capsys.readouterr().out

    assert help_short == help_long
    assert "--password" in help_short or "-p" in help_short
    assert "--verbose" in help_short or "-v" in help_short
