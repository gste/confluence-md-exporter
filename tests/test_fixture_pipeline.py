from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from confluence_md_exporter.cli import main, parse_cli
from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.flow import run_export
from confluence_md_exporter.settings import Settings
from confluence_md_exporter.url_resolver import resolve_input_file

BASE = "https://confluence.example.com"
FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN = (FIXTURES / "kitchen_sink.xml").read_text(encoding="utf-8")
ASSET_HREF = re.compile(r"\[[^\]]*\]\((../03_assets/[^)]+)\)")
DIAGRAM = b"PNG-BYTES"
SPEC_PDF = b"%PDF-fake"
FLOW_PNG = b"FLOWPNG!"
FLOW_XML = b"<mxfile/>"
TOKEN = "dummy-token"


def _settings(tmp_path: Path, urls: Path, *, force_refresh: bool) -> Settings:
    return Settings(
        confluence_base_url=BASE,
        confluence_edition="datacenter",
        confluence_auth_type="bearer",
        confluence_token=TOKEN,
        confluence_username=None,
        confluence_verify_ssl=True,
        confluence_timeout_seconds=30,
        confluence_max_retries=3,
        export_output_dir=str(tmp_path / "data"),
        export_input_file=str(urls),
        export_concurrency=1,
        export_force_refresh=force_refresh,
        log_level="INFO",
    )


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), {})


def _page(
    page_id: str,
    title: str,
    *,
    body: str = "<p>ok</p>",
    status: str = "current",
    version: int = 7,
    labels: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": page_id,
        "type": "page",
        "status": status,
        "title": title,
        "space": {"key": "DEV"},
        "version": {
            "number": version,
            "when": "2026-01-01T00:00:00.000Z",
            "by": {"displayName": "Jane"},
        },
        "history": {"createdBy": {"displayName": "Jane"}},
        "body": {"storage": {"value": body}},
        "metadata": {"labels": {"results": [{"name": name} for name in (labels or [])]}},
        "ancestors": [{"id": "1", "title": "Root &amp; Co"}],
        "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
    }


def _attachments_101() -> dict[str, object]:
    return {
        "results": [
            {
                "id": "att-diagram",
                "title": "diagram.png",
                "extensions": {"mediaType": "image/png", "fileSize": len(DIAGRAM)},
                "_links": {"download": "/rest/api/content/att-diagram"},
            },
            {
                "id": "att-spec",
                "title": "spec.pdf",
                "extensions": {"mediaType": "application/pdf", "fileSize": len(SPEC_PDF)},
                "_links": {"download": "/rest/api/content/att-spec"},
            },
            {
                "id": "att-flow-png",
                "title": "flow.png",
                "extensions": {"mediaType": "image/png", "fileSize": len(FLOW_PNG)},
                "_links": {"download": "/rest/api/content/att-flow-png"},
            },
            {
                "id": "att-flow-src",
                "title": "flow.drawio",
                "extensions": {"mediaType": "application/xml", "fileSize": len(FLOW_XML)},
                "_links": {"download": "/rest/api/content/att-flow-src"},
            },
        ],
        "_links": {},
    }


class FixtureTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self._binaries = {
            "att-diagram": DIAGRAM,
            "att-spec": SPEC_PDF,
            "att-flow-png": FLOW_PNG,
            "att-flow-src": FLOW_XML,
        }
        self._pages = {
            "101": _page("101", "Kitchen &amp; Sink", body=KITCHEN, labels=["docs"]),
            "102": _page("102", "In Batch"),
            "103": _page("103", "Look Up"),
            "108": _page("108", "Personal", body="<p>unclosed"),
            "109": _page("109", "Empty", body=""),
            "106": _page("106", "Trash", status="trashed"),
        }

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        with self._lock:
            self.calls.append(url)
            parsed = urlparse(url)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/rest/api/content":
                return self._search(query)
            if "/child/attachment" in path:
                page_id = path.split("/content/")[1].split("/")[0]
                if page_id == "101":
                    return _json(200, _attachments_101())
                return _json(200, {"results": [], "_links": {}})
            content_id = path.rsplit("/", 1)[-1]
            if content_id in self._binaries:
                return HttpResponse(200, self._binaries[content_id], {})
            expand = (query.get("expand") or [""])[0]
            version_only = expand == "version"
            if content_id == "104":
                return _json(403, {"message": "forbidden"})
            if content_id == "105":
                return _json(404, {"message": "not found"})
            if content_id not in self._pages:
                raise AssertionError(f"unexpected request: {url}")
            payload = self._pages[content_id]
            if version_only:
                return _json(200, {"id": content_id, "version": payload["version"]})
            return _json(200, payload)

    def _search(self, query: dict[str, list[str]]) -> HttpResponse:
        space = (query.get("spaceKey") or [""])[0]
        title = (query.get("title") or [""])[0]
        if space == "DEV" and title == "Look Up":
            return _json(200, {"results": [{"id": "103"}], "_links": {}})
        return _json(200, {"results": [], "_links": {}})


def _write_all_url_forms(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# comment",
                f"{BASE}/pages/viewpage.action?pageId=101",
                f"{BASE}/pages/viewpage.action?pageId=101&src=email",
                f"{BASE}/display/DEV/Look+Up",
                f"{BASE}/wiki/spaces/DEV/pages/102/In+Batch",
                f"{BASE}/wiki/spaces/~user/pages/108/Personal",
                "109",
                f"{BASE}/x/AbCdEf",
                f"{BASE}/pages/viewpage.action?pageId=104",
                f"{BASE}/pages/viewpage.action?pageId=105",
                f"{BASE}/pages/viewpage.action?pageId=106",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _run(
    tmp_path: Path, transport: FixtureTransport, *, force_refresh: bool
) -> tuple[int, list[dict[str, object]]]:
    urls = tmp_path / "urls.txt"
    if not urls.exists():
        _write_all_url_forms(urls)
    published: list[dict[str, object]] = []
    settings = _settings(tmp_path, urls, force_refresh=force_refresh)
    client = ConfluenceClient(settings, transport=transport, sleep=lambda _d: None)
    code = run_export(settings, client=client, publish=lambda **kw: published.append(kw))
    return code, published


def test_all_accepted_url_forms_in_input(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    _write_all_url_forms(urls)
    result = resolve_input_file(urls, BASE)
    ids = {entry.page_id for entry in result.entries if entry.page_id}
    display = [entry for entry in result.entries if entry.needs_title_lookup]
    assert ids == {"101", "102", "104", "105", "106", "108", "109"}
    assert len(display) == 1
    assert display[0].space_key == "DEV"
    assert display[0].title == "Look Up"
    assert result.pages_total == 8
    assert any("/x/" in item for item in result.invalid_urls)


def test_fixture_pipeline_covers_constructs_fallback_assets_and_catalog(tmp_path: Path) -> None:
    transport = FixtureTransport()
    code, published = _run(tmp_path, transport, force_refresh=True)
    out = tmp_path / "data"
    assert code == 1
    manifest = json.loads((out / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in manifest}

    assert by_id["101"]["status"] == "ok"
    assert by_id["102"]["status"] == "ok"
    assert by_id["103"]["status"] == "ok"
    assert by_id["109"]["status"] == "ok"
    assert by_id["104"]["status"] == "failed"
    assert by_id["104"]["error"] == "forbidden"
    assert by_id["105"]["status"] == "skipped"
    assert by_id["106"]["status"] == "skipped"
    assert by_id["108"]["status"] == "failed"
    assert by_id["108"]["error"] == "invalid_xml"
    assert report["ok"] == 4
    assert report["failed"] == 2
    assert report["skipped"] == 2
    assert report["pages_total"] == 8
    assert any("/x/" in item for item in report["invalid_urls"])

    kitchen = (out / "04_markdown" / "101_kitchen-sink.md").read_text(encoding="utf-8")
    assert kitchen.startswith("---\n")
    assert "source_url:" in kitchen
    assert "labels:" in kitchen
    assert "# Heading" in kitchen
    assert "**bold**" in kitchen
    assert "*em*" in kitchen
    assert "```plantuml" in kitchen
    plantuml_body = kitchen.split("```plantuml")[1].split("```")[0]
    assert "![" not in plantuml_body
    assert "> [!NOTE]" in kitchen
    assert "> [!WARNING]" in kitchen
    assert "> [!TIP]" in kitchen
    assert "<details>" in kitchen
    assert "`Blocked`" in kitchen
    assert "Red" not in kitchen
    assert "- [x] Done" in kitchen
    assert ":smile:" in kitchen
    assert "@Ada Lovelace" in kitchen
    assert "2026-08-31" in kitchen
    assert "![diagram](../03_assets/101/diagram.png)" in kitchen
    assert "![remote](https://cdn.example.com/pic.png)" in kitchen
    assert "[spec](../03_assets/101/spec.pdf)" in kitchen
    assert "[missing-attachment: gone.png]" in kitchen
    assert "![flow](../03_assets/101/flow.png)" in kitchen
    assert "[source](../03_assets/101/flow.drawio)" in kitchen
    assert "102_in-batch.md" in kitchen
    assert "pageId=999" in kitchen
    assert "<!-- unsupported-macro: jira -->" in kitchen
    assert "See ticket" in kitchen
    assert "jira" in kitchen
    assert "| xy | z |  |" in kitchen
    assert kitchen.count("```") >= 6

    empty_md = next((out / "04_markdown").glob("109_*.md"))
    empty_text = empty_md.read_text(encoding="utf-8")
    _, _, body = empty_text.split("---", 2)
    assert body.strip() == ""

    md_dir = out / "04_markdown"
    for md_file in md_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        for href in ASSET_HREF.findall(text):
            assert href.startswith("../03_assets/")
            assert (md_dir / href).resolve().is_file(), href
            assert "[missing-attachment:" not in href

    row = by_id["101"]
    assert row["md_path"]
    assert row["assets_dir"] == "03_assets/101"
    assert "docs" in row["labels"]
    assert row["source_url"]
    keys = {item.get("key") for item in published}
    assert "page-101" in keys
    assert "run-summary" in keys
    blob = "\n".join(str(item.get("markdown") or "") for item in published)
    assert TOKEN not in blob


def test_rerun_without_force_refresh_skips_and_keeps_bytes(tmp_path: Path) -> None:
    _run(tmp_path, FixtureTransport(), force_refresh=True)
    out = tmp_path / "data"
    md_path = out / "04_markdown" / "101_kitchen-sink.md"
    asset_path = out / "03_assets" / "101" / "diagram.png"
    md_bytes = md_path.read_bytes()
    asset_bytes = asset_path.read_bytes()
    code, _published = _run(tmp_path, FixtureTransport(), force_refresh=False)
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in manifest}
    assert code == 1
    assert by_id["101"]["status"] == "skipped"
    assert by_id["102"]["status"] == "skipped"
    assert by_id["109"]["status"] == "skipped"
    assert report["skipped"] >= 3
    assert md_path.read_bytes() == md_bytes
    assert asset_path.read_bytes() == asset_bytes
    assert (out / "03_assets" / "101" / "flow.drawio").read_bytes() == FLOW_XML


def test_force_refresh_reprocesses_unchanged_page(tmp_path: Path) -> None:
    _run(tmp_path, FixtureTransport(), force_refresh=True)
    out = tmp_path / "data"
    third = FixtureTransport()
    _run(tmp_path, third, force_refresh=True)
    manifest = json.loads((out / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in manifest}
    assert by_id["101"]["status"] == "ok"
    assert any("body.storage" in url for url in third.calls)
    assert any("/content/101" in url for url in third.calls)


def test_exit_2_when_edition_is_not_datacenter(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("101\n", encoding="utf-8")
    code = main(
        argv=[],
        environ={
            "CONFLUENCE_BASE_URL": BASE,
            "CONFLUENCE_AUTH_TYPE": "bearer",
            "CONFLUENCE_TOKEN": TOKEN,
            "CONFLUENCE_EDITION": "cloud",
            "EXPORT_INPUT_FILE": str(urls),
        },
        run_export=lambda _s: 0,
        auth_probe=lambda _s: None,
    )
    assert code == 2


def test_out_of_scope_absent_from_cli() -> None:
    with pytest.raises(SystemExit):
        parse_cli(["--cloud"])
    with pytest.raises(SystemExit):
        parse_cli(["--descendants"])
    with pytest.raises(SystemExit):
        parse_cli(["--write"])
    with pytest.raises(SystemExit):
        parse_cli(["--rag"])

