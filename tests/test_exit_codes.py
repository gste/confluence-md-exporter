from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from confluence_md_exporter.cli import main, parse_cli
from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.flow import run_export
from confluence_md_exporter.output import (
    write_asset_sidecar,
    write_bronze,
    write_gold_markdown,
    write_interim,
)
from confluence_md_exporter.settings import Settings


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


def test_anonymous_skips_auth_probe(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=11\n", encoding="utf-8")
    probe = Mock(side_effect=AssertionError("probe must not run for anonymous"))
    export = Mock(return_value=0)
    code = main(
        argv=["-i", str(urls), "-o", str(tmp_path / "data")],
        environ={},
        run_export=export,
        auth_probe=probe,
    )
    assert code == 0
    probe.assert_not_called()
    export.assert_called_once()
    assert export.call_args.args[0].confluence_auth_type == "anonymous"


def test_exit_2_on_http_401_before_pages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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
    err = capsys.readouterr().err
    assert "401" in err
    assert "dummy-token" not in err
    assert "Authorization" not in err


def test_exit_2_on_http_404_before_pages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    export = Mock()

    def auth_probe(settings) -> None:
        def transport(url: str, headers: dict[str, str]) -> HttpResponse:
            return HttpResponse(404, b"<html>not found</html>", {"Content-Type": "text/html"})

        ConfluenceClient(settings, transport=transport, sleep=lambda _d: None).probe()

    code = main(
        argv=[],
        environ=_env(tmp_path),
        run_export=export,
        auth_probe=auth_probe,
    )
    assert code == 2
    export.assert_not_called()
    err = capsys.readouterr().err
    assert "404" in err
    assert "dummy-token" not in err
    assert "Authorization" not in err


def test_exit_2_on_non_json_200_before_pages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    export = Mock()

    def auth_probe(settings) -> None:
        def transport(url: str, headers: dict[str, str]) -> HttpResponse:
            return HttpResponse(200, b"<html>login</html>", {"Content-Type": "text/html"})

        ConfluenceClient(settings, transport=transport, sleep=lambda _d: None).probe()

    code = main(
        argv=[],
        environ=_env(tmp_path),
        run_export=export,
        auth_probe=auth_probe,
    )
    assert code == 2
    export.assert_not_called()
    err = capsys.readouterr().err
    assert "JSON" in err
    assert "dummy-token" not in err
    assert "Authorization" not in err


def test_auth_probe_passes_on_current_user_json(tmp_path: Path) -> None:
    export = Mock(return_value=0)

    def auth_probe(settings) -> None:
        def transport(url: str, headers: dict[str, str]) -> HttpResponse:
            return HttpResponse(
                200,
                json.dumps({"username": "jdoe", "userKey": "abc"}).encode("utf-8"),
                {},
            )

        ConfluenceClient(settings, transport=transport, sleep=lambda _d: None).probe()

    code = main(
        argv=[],
        environ=_env(tmp_path),
        run_export=export,
        auth_probe=auth_probe,
    )
    assert code == 0
    export.assert_called_once()


def test_cli_has_no_out_of_scope_flags() -> None:
    with pytest.raises(SystemExit):
        parse_cli(["--cloud"])
    with pytest.raises(SystemExit):
        parse_cli(["--descendants"])
    with pytest.raises(SystemExit):
        parse_cli(["--write"])


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), {})


def _page_payload(page_id: str, title: str, version: int = 1) -> dict[str, object]:
    return {
        "id": page_id,
        "type": "page",
        "status": "current",
        "title": title,
        "space": {"key": "DEV"},
        "version": {
            "number": version,
            "when": "2026-01-01T00:00:00.000Z",
            "by": {"displayName": "Jane"},
        },
        "history": {"createdBy": {"displayName": "Jane"}},
        "body": {"storage": {"value": f"<p>{title}</p>"}},
        "metadata": {"labels": {"results": []}},
        "ancestors": [],
        "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
    }


def _seed_unchanged(output_dir: Path, page_id: str = "42") -> None:
    write_bronze(
        output_dir,
        {
            "page_id": page_id,
            "edition": "datacenter",
            "title": "Hello",
            "space_key": "DEV",
            "version": 4,
            "status": "current",
            "created_by": "jdoe",
            "updated_at": "2026-01-01T00:00:00Z",
            "source_url": f"https://confluence.example.com/pages/viewpage.action?pageId={page_id}",
            "labels": [],
            "ancestors": [],
            "body_storage": "<p>hi</p>",
            "attachments": [],
            "fetched_at": "2026-01-01T00:00:01Z",
        },
    )
    write_asset_sidecar(output_dir, page_id, {})
    write_interim(output_dir, page_id, "<p>hi</p>")
    write_gold_markdown(
        output_dir,
        page_id,
        {
            "id": page_id,
            "title": "Hello",
            "space_key": "DEV",
            "version": 4,
            "status": "current",
            "created_by": "jdoe",
            "updated_at": "2026-01-01T00:00:00Z",
            "source_url": f"https://confluence.example.com/pages/viewpage.action?pageId={page_id}",
            "labels": [],
            "breadcrumbs": [],
            "attachments_count": 0,
            "unsupported_macros": [],
        },
        "old\n",
    )


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


def _run_via_cli(tmp_path: Path, transport: ScriptedTransport, *, force_refresh: bool = False) -> int:
    env = _env(tmp_path)
    if force_refresh:
        env["EXPORT_FORCE_REFRESH"] = "true"

    def export(settings: Settings) -> int:
        client = ConfluenceClient(settings, transport=transport, sleep=lambda _d: None)
        return run_export(settings, client=client, publish=lambda **_kw: None)

    return main(argv=[], environ=env, run_export=export, auth_probe=lambda _s: None)


def test_exit_0_all_ok_or_skipped(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/pages/viewpage.action?pageId=42\n"
        "https://confluence.example.com/pages/viewpage.action?pageId=43\n",
        encoding="utf-8",
    )
    out = tmp_path / "data"
    _seed_unchanged(out, "42")
    transport = ScriptedTransport(
        [
            _json(200, {"id": "42", "version": {"number": 4}}),
            _json(200, _page_payload("43", "New")),
            _json(200, {"results": [], "_links": {}}),
        ]
    )
    code = _run_via_cli(tmp_path, transport)
    assert code == 0
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    assert report["failed"] == 0
    assert report["skipped"] == 1
    assert report["ok"] == 1


def test_exit_0_all_skipped(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/pages/viewpage.action?pageId=42\n",
        encoding="utf-8",
    )
    out = tmp_path / "data"
    _seed_unchanged(out)
    transport = ScriptedTransport([_json(200, {"id": "42", "version": {"number": 4}})])
    code = _run_via_cli(tmp_path, transport)
    assert code == 0
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    assert report["ok"] == 0
    assert report["failed"] == 0
    assert report["skipped"] == 1


def test_exit_1_partial_failure(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/pages/viewpage.action?pageId=10\n"
        "https://confluence.example.com/pages/viewpage.action?pageId=11\n",
        encoding="utf-8",
    )
    transport = ScriptedTransport(
        [
            _json(403, {"message": "forbidden"}),
            _json(200, _page_payload("11", "Kept")),
            _json(200, {"results": [], "_links": {}}),
        ]
    )
    code = _run_via_cli(tmp_path, transport, force_refresh=True)
    assert code == 1
    report = json.loads((tmp_path / "data" / "run_report.json").read_text(encoding="utf-8"))
    assert report["failed"] >= 1
    assert report["ok"] == 1
