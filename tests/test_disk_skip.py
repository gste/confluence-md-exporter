from __future__ import annotations

import json
from pathlib import Path

from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.disk_skip import sync_page
from confluence_md_exporter.layout import gold_markdown_path, slugify
from confluence_md_exporter.output import (
    write_asset_sidecar,
    write_bronze,
    write_gold_markdown,
    write_interim,
    write_manifest,
    write_run_report,
)
from confluence_md_exporter.settings import Settings

BASE = "https://confluence.example.com"
PAGE_ID = "42"
ASSET_NAME = "img.png"
ASSET_BYTES = b"0123456789"
MARKDOWN_BODY = "old markdown\n"


def _settings(*, force_refresh: bool = False) -> Settings:
    return Settings(
        confluence_base_url=BASE,
        confluence_edition="datacenter",
        confluence_auth_type="bearer",
        confluence_token="dummy-token",
        confluence_username=None,
        confluence_verify_ssl=True,
        confluence_timeout_seconds=30,
        confluence_max_retries=3,
        export_output_dir="data",
        export_input_file="input/urls.txt",
        export_concurrency=2,
        export_force_refresh=force_refresh,
        log_level="INFO",
    )


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), {})


def _bronze(*, version: int = 4) -> dict[str, object]:
    return {
        "page_id": PAGE_ID,
        "edition": "datacenter",
        "title": "Hello",
        "space_key": "DEV",
        "version": version,
        "status": "current",
        "created_by": "jdoe",
        "updated_at": "2026-01-01T00:00:00Z",
        "source_url": f"{BASE}/pages/viewpage.action?pageId={PAGE_ID}",
        "labels": ["docs"],
        "ancestors": [{"id": "1", "title": "Root"}],
        "body_storage": "<p>hi</p>",
        "attachments": [
            {
                "id": "a1",
                "title": ASSET_NAME,
                "media_type": "image/png",
                "file_size": len(ASSET_BYTES),
                "download_path": "/rest/api/content/a1",
            }
        ],
        "fetched_at": "2026-01-01T00:00:01Z",
    }


def _frontmatter() -> dict[str, object]:
    return {
        "id": PAGE_ID,
        "title": "Hello",
        "space_key": "DEV",
        "version": 4,
        "status": "current",
        "created_by": "jdoe",
        "updated_at": "2026-01-01T00:00:00Z",
        "source_url": f"{BASE}/pages/viewpage.action?pageId={PAGE_ID}",
        "labels": ["docs"],
        "breadcrumbs": ["Root"],
        "attachments_count": 1,
        "unsupported_macros": [],
    }


def _seed_local(output_dir: Path, *, version: int = 4) -> dict[str, bytes]:
    write_bronze(output_dir, _bronze(version=version))
    write_asset_sidecar(output_dir, PAGE_ID, {ASSET_NAME: ASSET_NAME})
    asset = output_dir / "03_assets" / PAGE_ID / ASSET_NAME
    asset.parent.mkdir(parents=True, exist_ok=True)
    asset.write_bytes(ASSET_BYTES)
    write_interim(output_dir, PAGE_ID, "<p>hi</p>")
    md = write_gold_markdown(output_dir, PAGE_ID, _frontmatter(), MARKDOWN_BODY)
    return {
        "raw": (output_dir / "01_raw" / f"{PAGE_ID}.json").read_bytes(),
        "asset": asset.read_bytes(),
        "interim": (output_dir / "02_interim" / f"{PAGE_ID}.html").read_bytes(),
        "markdown": md.read_bytes(),
    }


def _page_payload(*, version: int) -> dict[str, object]:
    return {
        "id": PAGE_ID,
        "type": "page",
        "status": "current",
        "title": "Hello",
        "space": {"key": "DEV"},
        "version": {"number": version, "when": "2026-02-01T00:00:00.000Z", "by": {"displayName": "Jane"}},
        "history": {"createdBy": {"displayName": "Jane"}},
        "body": {"storage": {"value": "<p>new</p>"}},
        "metadata": {"labels": {"results": [{"name": "docs"}]}},
        "ancestors": [{"id": "1", "title": "Root"}],
        "_links": {"webui": f"/pages/viewpage.action?pageId={PAGE_ID}"},
    }


def _attachments_payload() -> dict[str, object]:
    return {
        "results": [
            {
                "id": "a1",
                "title": ASSET_NAME,
                "extensions": {"mediaType": "image/png", "fileSize": 7},
                "_links": {"download": "/rest/api/content/a1"},
            }
        ],
        "_links": {},
    }


def _full_refresh_responses(*, version: int) -> list[HttpResponse]:
    return [
        _json(200, {"id": PAGE_ID, "version": {"number": version}}),
        _json(200, _page_payload(version=version)),
        _json(200, _attachments_payload()),
        HttpResponse(200, b"NEWFILE", {}),
    ]


def _markdown_files(output_dir: Path) -> list[Path]:
    folder = output_dir / "04_markdown"
    return sorted(folder.glob(f"{PAGE_ID}_*.md"))


def test_matching_version_and_size_skips_and_does_not_change_page_bytes(tmp_path: Path) -> None:
    snapshots = _seed_local(tmp_path)
    transport = ScriptedTransport([_json(200, {"id": PAGE_ID, "version": {"number": 4}})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=False)

    assert result.status == "skipped"
    assert result.error == "disk_skip"
    assert len(transport.calls) == 1
    assert "expand=version" in transport.calls[0][0]
    assert "body.storage" not in transport.calls[0][0]
    assert (tmp_path / "01_raw" / f"{PAGE_ID}.json").read_bytes() == snapshots["raw"]
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == snapshots["asset"]
    assert (tmp_path / "02_interim" / f"{PAGE_ID}.html").read_bytes() == snapshots["interim"]
    markdown_paths = _markdown_files(tmp_path)
    assert markdown_paths
    assert markdown_paths[0] == tmp_path / gold_markdown_path(PAGE_ID, slugify("Hello"))
    assert markdown_paths[0].read_bytes() == snapshots["markdown"]


def test_changed_version_full_processing(tmp_path: Path) -> None:
    snapshots = _seed_local(tmp_path, version=4)
    transport = ScriptedTransport(_full_refresh_responses(version=5))
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=False)

    assert result.status == "ok"
    assert result.raw is not None
    assert result.raw["version"] == 5
    assert (tmp_path / "01_raw" / f"{PAGE_ID}.json").read_bytes() != snapshots["raw"]
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == b"NEWFILE"
    assert any("body.storage" in url for url, _headers in transport.calls)
    assert any(url.endswith("/rest/api/content/a1") for url, _headers in transport.calls)


def test_missing_asset_full_processing_ignores_prefect_style_cache(tmp_path: Path) -> None:
    _seed_local(tmp_path)
    (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).unlink()
    prefect_cache = {PAGE_ID: {"version": 4, "skip": True}}
    transport = ScriptedTransport(_full_refresh_responses(version=4))
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=False)

    assert prefect_cache[PAGE_ID]["skip"] is True
    assert result.status == "ok"
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == b"NEWFILE"
    assert any("body.storage" in url for url, _headers in transport.calls)


def test_asset_size_mismatch_full_processing(tmp_path: Path) -> None:
    _seed_local(tmp_path)
    (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).write_bytes(b"short")
    transport = ScriptedTransport(_full_refresh_responses(version=4))
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=False)

    assert result.status == "ok"
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == b"NEWFILE"


def test_force_refresh_full_processing(tmp_path: Path) -> None:
    snapshots = _seed_local(tmp_path)
    transport = ScriptedTransport(
        [
            _json(200, _page_payload(version=4)),
            _json(200, _attachments_payload()),
            HttpResponse(200, b"NEWFILE", {}),
        ]
    )
    client = ConfluenceClient(_settings(force_refresh=True), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=True)

    assert result.status == "ok"
    assert all("expand=version" not in url or "body.storage" in url for url, _headers in transport.calls)
    assert (tmp_path / "01_raw" / f"{PAGE_ID}.json").read_bytes() != snapshots["raw"]
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == b"NEWFILE"


def test_skip_still_rewrites_manifest_and_run_report(tmp_path: Path) -> None:
    snapshots = _seed_local(tmp_path)
    write_manifest(
        tmp_path,
        [
            {
                "id": PAGE_ID,
                "title": "Hello",
                "space_key": "DEV",
                "version": 4,
                "source_url": f"{BASE}/pages/viewpage.action?pageId={PAGE_ID}",
                "md_path": f"04_markdown/{PAGE_ID}_hello.md",
                "assets_dir": f"03_assets/{PAGE_ID}",
                "labels": ["docs"],
                "status": "ok",
                "error": None,
            }
        ],
    )
    write_run_report(
        tmp_path,
        {
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:00:01Z",
            "pages_total": 1,
            "ok": 1,
            "failed": 0,
            "skipped": 0,
            "invalid_urls": [],
            "force_refresh": False,
            "errors": [],
        },
    )
    old_manifest = (tmp_path / "04_markdown" / "manifest.json").read_bytes()
    old_report = (tmp_path / "run_report.json").read_bytes()
    transport = ScriptedTransport([_json(200, {"id": PAGE_ID, "version": {"number": 4}})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)

    result = sync_page(client, tmp_path, PAGE_ID, force_refresh=False)
    write_manifest(
        tmp_path,
        [
            {
                "id": PAGE_ID,
                "title": "Hello",
                "space_key": "DEV",
                "version": 4,
                "source_url": f"{BASE}/pages/viewpage.action?pageId={PAGE_ID}",
                "md_path": f"04_markdown/{PAGE_ID}_hello.md",
                "assets_dir": f"03_assets/{PAGE_ID}",
                "labels": ["docs"],
                "status": result.status,
                "error": result.error,
            }
        ],
    )
    write_run_report(
        tmp_path,
        {
            "started_at": "2026-01-02T00:00:00Z",
            "finished_at": "2026-01-02T00:00:01Z",
            "pages_total": 1,
            "ok": 0,
            "failed": 0,
            "skipped": 1,
            "invalid_urls": [],
            "force_refresh": False,
            "errors": [],
        },
    )

    assert result.status == "skipped"
    assert (tmp_path / "03_assets" / PAGE_ID / ASSET_NAME).read_bytes() == snapshots["asset"]
    assert _markdown_files(tmp_path)[0].read_bytes() == snapshots["markdown"]
    assert (tmp_path / "04_markdown" / "manifest.json").read_bytes() != old_manifest
    assert (tmp_path / "run_report.json").read_bytes() != old_report
