from __future__ import annotations

import json
from pathlib import Path

from confluence_md_exporter.output import write_manifest, write_run_report


def test_manifest_required_keys_and_statuses(tmp_path: Path) -> None:
    records = [
        {
            "id": "1",
            "title": "Ok",
            "space_key": "DEV",
            "version": 3,
            "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=1",
            "md_path": "04_markdown/1_ok.md",
            "assets_dir": "03_assets/1",
            "labels": ["a"],
            "status": "ok",
            "error": None,
        },
        {
            "id": "2",
            "title": None,
            "space_key": None,
            "version": None,
            "source_url": None,
            "md_path": None,
            "assets_dir": "03_assets/2",
            "labels": [],
            "status": "failed",
            "error": "forbidden",
        },
        {
            "id": None,
            "title": "Missing",
            "space_key": "DEV",
            "version": None,
            "source_url": None,
            "md_path": None,
            "assets_dir": None,
            "labels": [],
            "status": "skipped",
            "error": "not_found",
        },
    ]
    path = write_manifest(tmp_path, records)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path == tmp_path / "04_markdown" / "manifest.json"
    assert [row["status"] for row in payload] == ["ok", "failed", "skipped"]
    for row in payload:
        for key in (
            "id",
            "title",
            "space_key",
            "version",
            "source_url",
            "md_path",
            "assets_dir",
            "labels",
            "status",
            "error",
        ):
            assert key in row
    assert payload[2]["id"] is None
    assert isinstance(payload[0]["id"], str)


def test_invalid_urls_stay_out_of_manifest(tmp_path: Path) -> None:
    write_manifest(
        tmp_path,
        [
            {
                "id": "9",
                "title": "Only valid",
                "space_key": "DEV",
                "version": 1,
                "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=9",
                "md_path": "04_markdown/9_only-valid.md",
                "assets_dir": "03_assets/9",
                "labels": [],
                "status": "ok",
                "error": None,
            }
        ],
    )
    report = write_run_report(
        tmp_path,
        {
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "pages_total": 1,
            "ok": 1,
            "failed": 0,
            "skipped": 0,
            "invalid_urls": ["https://confluence.example.com/x/tiny", "not-a-url"],
            "force_refresh": False,
            "errors": [],
        },
    )
    manifest = json.loads((tmp_path / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert len(manifest) == 1
    assert manifest[0]["id"] == "9"
    for key in (
        "started_at",
        "finished_at",
        "pages_total",
        "ok",
        "failed",
        "skipped",
        "invalid_urls",
        "force_refresh",
        "errors",
    ):
        assert key in payload
    assert payload["invalid_urls"] == ["https://confluence.example.com/x/tiny", "not-a-url"]
    assert payload["errors"] == []
