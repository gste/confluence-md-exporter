from __future__ import annotations

import json
from pathlib import Path

from confluence_md_exporter.output import (
    BRONZE_KEYS,
    FRONTMATTER_KEYS,
    build_source_url,
    write_asset_sidecar,
    write_bronze,
    write_gold_markdown,
    write_interim,
)


def _bronze(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "page_id": "42",
        "edition": "datacenter",
        "title": "Hello &amp; World",
        "space_key": "DEV",
        "version": 4,
        "status": "current",
        "created_by": "jdoe",
        "updated_at": "2026-01-01T00:00:00Z",
        "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=42",
        "labels": ["docs"],
        "ancestors": [{"id": "1", "title": "Root"}],
        "body_storage": "<p>hi</p>",
        "attachments": [
            {
                "id": "a1",
                "title": "img.png",
                "media_type": "image/png",
                "file_size": 10,
                "download_path": "/rest/api/content/42/child/attachment/a1/download",
            }
        ],
        "fetched_at": "2026-01-01T00:00:01Z",
    }
    raw.update(overrides)
    return raw


def test_bronze_required_keys_and_storage_only(tmp_path: Path) -> None:
    path = write_bronze(
        tmp_path,
        _bronze(
            view="nope",
            export_view="nope",
            atlas_doc_format="nope",
            body={"storage": {"value": "<p>x</p>"}, "view": {"value": "html"}},
        ),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in BRONZE_KEYS:
        assert key in payload
    assert payload["page_id"] == "42"
    assert isinstance(payload["page_id"], str)
    assert payload["edition"] == "datacenter"
    assert "body_storage" in payload
    assert "view" not in payload
    assert "export_view" not in payload
    assert "atlas_doc_format" not in payload
    assert payload["body"] == {"storage": {"value": "<p>x</p>"}}


def test_frontmatter_keys_and_gold_path(tmp_path: Path) -> None:
    write_interim(tmp_path, "42", "<p>clean</p>")
    path = write_gold_markdown(
        tmp_path,
        "42",
        {
            "id": "42",
            "title": "Hello World",
            "space_key": "DEV",
            "version": 4,
            "status": "current",
            "created_by": "jdoe",
            "updated_at": "2026-01-01T00:00:00Z",
            "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=42",
            "labels": ["docs"],
            "breadcrumbs": ["Root", "Hello World"],
            "attachments_count": 1,
            "unsupported_macros": [],
        },
        "Hello **world**\n",
    )
    text = path.read_text(encoding="utf-8")
    assert path == tmp_path / "04_markdown" / "42_hello-world.md"
    assert text.startswith("---\n")
    block = text.split("---", 2)[1]
    for key in FRONTMATTER_KEYS:
        assert f"{key}:" in block
    assert "Hello **world**" in text
    assert (tmp_path / "02_interim" / "42.html").read_text(encoding="utf-8") == "<p>clean</p>"


def test_sidecar_only_when_attachments_mapped(tmp_path: Path) -> None:
    written = write_asset_sidecar(tmp_path, "42", {"diagram.png": "diagram.png"})
    assert written == tmp_path / "01_raw" / "42.assets.json"
    assert json.loads(written.read_text(encoding="utf-8")) == {"diagram.png": "diagram.png"}
    assert write_asset_sidecar(tmp_path, "43", {}) is None
    assert not (tmp_path / "01_raw" / "43.assets.json").exists()


def test_source_url_from_webui_or_viewpage() -> None:
    base = "https://confluence.example.com"
    assert (
        build_source_url(base, "7", None)
        == "https://confluence.example.com/pages/viewpage.action?pageId=7"
    )
    assert build_source_url(base, "7", "/display/DEV/Hi") == "https://confluence.example.com/display/DEV/Hi"
    assert (
        build_source_url(base, "7", "https://confluence.example.com/display/DEV/Hi")
        == "https://confluence.example.com/display/DEV/Hi"
    )
