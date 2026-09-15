from __future__ import annotations

import json
import threading
from pathlib import Path
from urllib.parse import urlparse

from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.flow import run_export
from confluence_md_exporter.settings import Settings

BASE = "https://confluence.example.com"


def _settings(tmp_path: Path, urls: Path, *, concurrency: int = 2) -> Settings:
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
        export_concurrency=concurrency,
        export_force_refresh=True,
        log_level="INFO",
    )


def _json(status: int, payload: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), {})


def _page(page_id: str, title: str) -> dict[str, object]:
    return {
        "id": page_id,
        "type": "page",
        "status": "current",
        "title": title,
        "space": {"key": "DEV"},
        "version": {"number": 1, "when": "2026-01-01T00:00:00.000Z", "by": {"displayName": "Jane"}},
        "history": {"createdBy": {"displayName": "Jane"}},
        "body": {"storage": {"value": f"<p>{title}</p>"}},
        "metadata": {"labels": {"results": []}},
        "ancestors": [],
        "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
    }


class RoutingTransport:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        with self._lock:
            self.calls.append(url)
            path = urlparse(url).path
            if path.rstrip("/").endswith("/content/10"):
                return _json(403, {"message": "forbidden"})
            if path.rstrip("/").endswith("/content/11/child/attachment"):
                return _json(200, {"results": [], "_links": {}})
            if path.rstrip("/").endswith("/content/11"):
                return _json(200, _page("11", "Kept"))
            raise AssertionError(f"unexpected request: {url}")


def test_one_failed_page_does_not_cancel_the_rest(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/pages/viewpage.action?pageId=10\n"
        "https://confluence.example.com/pages/viewpage.action?pageId=11\n",
        encoding="utf-8",
    )
    published: list[dict[str, object]] = []
    transport = RoutingTransport()
    settings = _settings(tmp_path, urls)
    client = ConfluenceClient(settings, transport=transport, sleep=lambda _d: None)

    code = run_export(settings, client=client, publish=lambda **kw: published.append(kw))

    assert code == 1
    out = tmp_path / "data"
    manifest = json.loads((out / "04_markdown" / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((out / "run_report.json").read_text(encoding="utf-8"))
    statuses = {row["id"]: row["status"] for row in manifest}
    assert statuses["10"] == "failed"
    assert statuses["11"] == "ok"
    assert report["failed"] == 1
    assert report["ok"] == 1
    assert (out / "04_markdown" / "11_kept.md").is_file()
    assert not list(out.glob("04_markdown/10_*.md"))
    assert any("/content/11" in call for call in transport.calls)
