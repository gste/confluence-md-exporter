from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Mapping

from confluence_md_exporter.cli import main, parse_cli
from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.flow import run_export
from confluence_md_exporter.settings import Settings

BASE = "https://confluence.example.com"


def _settings(tmp_path: Path, urls: Path) -> Settings:
    return Settings(
        confluence_base_url=BASE,
        confluence_edition="datacenter",
        confluence_auth_type="bearer",
        confluence_token="dummy-token",
        confluence_username=None,
        confluence_verify_ssl=True,
        confluence_timeout_seconds=30,
        confluence_max_retries=3,
        export_output_dir=str(tmp_path / "data"),
        export_input_file=str(urls),
        export_force_refresh=True,
        log_level="INFO",
    )


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), {})


def test_diff_page_export_creates_diff_markdown(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    diff_url = f"{BASE}/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42"
    urls.write_text(f"{diff_url}\n", encoding="utf-8")

    def transport_handler(url: str, headers: Mapping[str, str] | None = None) -> HttpResponse:
        if "version=41" in url or "/version/41" in url:
            return _json(
                200,
                {
                    "id": "607636678",
                    "type": "page",
                    "status": "historical",
                    "title": "Sed Integration Service Domain Model",
                    "space": {"key": "DEV"},
                    "version": {
                        "number": 41,
                        "when": "2026-01-10T12:00:00.000Z",
                        "by": {"displayName": "Ivanov"},
                    },
                    "history": {"createdBy": {"displayName": "Ivanov"}},
                    "body": {"storage": {"value": "<p>Initial introductory paragraph.</p><p>Section A: stable text.</p>"}},
                    "metadata": {"labels": {"results": []}},
                    "ancestors": [],
                    "_links": {"webui": "/pages/viewpage.action?pageId=607636678"},
                },
            )
        if "version=42" in url or "/version/42" in url:
            return _json(
                200,
                {
                    "id": "607636678",
                    "type": "page",
                    "status": "current",
                    "title": "Sed Integration Service Domain Model",
                    "space": {"key": "DEV"},
                    "version": {
                        "number": 42,
                        "when": "2026-02-15T14:30:00.000Z",
                        "by": {"displayName": "Petrov"},
                    },
                    "history": {"createdBy": {"displayName": "Ivanov"}},
                    "body": {
                        "storage": {
                            "value": "<p>Updated introductory paragraph with new details.</p><p>Section A: stable text.</p><p>Section B: added new section.</p>"
                        }
                    },
                    "metadata": {"labels": {"results": [{"name": "architecture"}]}},
                    "ancestors": [],
                    "_links": {"webui": "/pages/viewpage.action?pageId=607636678"},
                },
            )
        return _json(404, {"message": "not found"})

    settings = _settings(tmp_path, urls)
    client = ConfluenceClient(settings, transport=transport_handler, sleep=lambda _d: None)

    code = run_export(settings, client=client, publish=lambda **_kw: None)
    assert code == 0

    diff_folder = tmp_path / "data" / "05_diffs"
    assert diff_folder.is_dir()

    diff_files = list(diff_folder.glob("*.md"))
    assert len(diff_files) == 1

    diff_file = diff_files[0]
    assert diff_file.name == "607636678_sed-integration-service-domain-model_v41_to_v42.md"

    content = diff_file.read_text(encoding="utf-8")
    assert "version_from: 41" in content
    assert "version_to: 42" in content
    assert "created_by_from:" in content
    assert "Ivanov" in content
    assert "Petrov" in content
    assert "lines_added:" in content
    assert "lines_removed:" in content
    assert "```diff" in content
    assert "--- v41.md" in content
    assert "+++ v42.md" in content

    manifest = json.loads((tmp_path / "data" / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["status"] == "ok"
    assert "05_diffs/" in manifest[0]["md_path"]

    report = json.loads((tmp_path / "data" / "run_report.json").read_text(encoding="utf-8"))
    assert report["ok"] == 1
    assert report["failed"] == 0


def test_cli_accepts_simple_flag_for_compatibility() -> None:
    args = parse_cli(["-s"])
    assert args.simple is True


def test_run_export_logs_progress(tmp_path: Path, caplog) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=50\n", encoding="utf-8")

    def transport_handler(url: str, headers: Mapping[str, str] | None = None) -> HttpResponse:
        if "/rest/api/content/50" in url:
            return _json(
                200,
                {
                    "id": "50",
                    "type": "page",
                    "status": "current",
                    "title": "Progress Log Test",
                    "space": {"key": "TEST"},
                    "version": {"number": 1, "when": "2026-01-01T00:00:00Z", "by": {"displayName": "Tester"}},
                    "history": {"createdBy": {"displayName": "Tester"}},
                    "body": {"storage": {"value": "<p>hello</p>"}},
                    "metadata": {"labels": {"results": []}},
                    "ancestors": [],
                    "_links": {"webui": "/pages/viewpage.action?pageId=50"},
                },
            )
        if "/child/attachment" in url:
            return _json(200, {"results": [], "_links": {}})
        return _json(404, {})

    settings = _settings(tmp_path, urls)
    client = ConfluenceClient(settings, transport=transport_handler, sleep=lambda _d: None)
    with caplog.at_level(logging.INFO, logger="confluence_md_exporter.flow"):
        code = run_export(settings, client=client, publish=lambda **_kw: None)
    assert code == 0
    text = caplog.text
    assert "Export 1 page(s), 0 invalid URL(s)" in text
    assert "[1/1] fetch page 50 -> ok" in text
    assert "«Progress Log Test»" in text
    assert "[1/1] write page 50 -> ok" in text
    assert "Done ok=1 failed=0 skipped=0 invalid=0" in text


def test_cli_clean_flag(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=50\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    stale_file = data_dir / "stale.txt"
    stale_file.write_text("old data", encoding="utf-8")
    assert stale_file.is_file()

    def auth_probe(settings: Settings) -> None:
        pass

    def run_exp(settings: Settings) -> int:
        return 0

    code = main(
        argv=["-c", "--input", str(urls), "--output", str(data_dir)],
        environ={
            "CONFLUENCE_BASE_URL": BASE,
            "CONFLUENCE_AUTH_TYPE": "bearer",
            "CONFLUENCE_TOKEN": "token",
            "EXPORT_INPUT_FILE": str(urls),
            "EXPORT_OUTPUT_DIR": str(data_dir),
        },
        run_export=run_exp,
        auth_probe=auth_probe,
    )
    assert code == 0
    assert not stale_file.exists()
    assert data_dir.is_dir()
