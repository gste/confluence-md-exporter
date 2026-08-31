from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from confluence_md_exporter.cli import main, parse_cli
from confluence_md_exporter.client import ConfluenceClient, HttpResponse


def _env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    urls = tmp_path / "urls.txt"
    urls.write_text("", encoding="utf-8")
    env = {
        "CONFLUENCE_BASE_URL": "https://confluence.example.com",
        "CONFLUENCE_AUTH_TYPE": "bearer",
        "CONFLUENCE_TOKEN": "dummy-token",
        "EXPORT_INPUT_FILE": str(urls),
    }
    env.update(overrides)
    return env


def test_exit_2_on_bad_config(tmp_path: Path) -> None:
    export = Mock()
    code = main(
        argv=[],
        environ=_env(tmp_path, CONFLUENCE_EDITION="cloud"),
        run_export=export,
    )
    assert code == 2
    export.assert_not_called()


def test_exit_2_when_input_file_missing(tmp_path: Path) -> None:
    export = Mock()
    env = _env(tmp_path)
    env["EXPORT_INPUT_FILE"] = str(tmp_path / "missing.txt")
    code = main(argv=[], environ=env, run_export=export)
    assert code == 2
    export.assert_not_called()


def test_exit_2_on_http_401_before_pages(tmp_path: Path) -> None:
    export = Mock()
    transport_calls: list[str] = []

    def auth_probe(settings) -> None:
        def transport(url: str, headers: dict[str, str]) -> HttpResponse:
            transport_calls.append(url)
            return HttpResponse(401, b"{}", {})

        ConfluenceClient(settings, transport=transport, sleep=lambda _d: None).probe()

    code = main(
        argv=[],
        environ=_env(tmp_path),
        run_export=export,
        auth_probe=auth_probe,
    )
    assert code == 2
    export.assert_not_called()
    assert transport_calls
    assert all("/wiki/" not in url for url in transport_calls)


def test_cli_has_no_out_of_scope_flags() -> None:
    with pytest.raises(SystemExit):
        parse_cli(["--cloud"])
    with pytest.raises(SystemExit):
        parse_cli(["--descendants"])
    with pytest.raises(SystemExit):
        parse_cli(["--write"])
