from __future__ import annotations

import json
from pathlib import Path

from confluence_md_exporter.assets import missing_attachment_placeholder, sync_page_assets
from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.settings import Settings

BASE = "https://confluence.example.com"


def _settings() -> Settings:
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
        export_force_refresh=False,
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


def test_download_uses_rest_not_ui_path_and_same_authorization(tmp_path: Path) -> None:
    transport = ScriptedTransport([HttpResponse(200, b"png-bytes", {})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    attachments = [
        {
            "id": "att-1",
            "title": "diagram.png",
            "media_type": "image/png",
            "file_size": 9,
            "download_path": "/download/attachments/42/diagram.png?version=1",
        }
    ]
    result = sync_page_assets(client, tmp_path, "42", attachments)
    assert result.page_failed is False
    url, headers = transport.calls[0]
    assert "/download/attachments/" not in url
    assert "/rest/api/content/att-1" in url
    assert headers["Authorization"] == "Bearer dummy-token"
    assert (tmp_path / "03_assets" / "42" / "diagram.png").read_bytes() == b"png-bytes"
    sidecar = json.loads((tmp_path / "01_raw" / "42.assets.json").read_text(encoding="utf-8"))
    assert sidecar == {"diagram.png": "diagram.png"}
    assert result.original_to_safe == sidecar


def test_anonymous_download_has_no_authorization(tmp_path: Path) -> None:
    transport = ScriptedTransport([HttpResponse(200, b"png-bytes", {})])
    settings = Settings(
        confluence_base_url=BASE,
        confluence_edition="datacenter",
        confluence_auth_type="anonymous",
        confluence_token="",
        confluence_username=None,
        confluence_verify_ssl=True,
        confluence_timeout_seconds=30,
        confluence_max_retries=3,
        export_output_dir="data",
        export_input_file="input/urls.txt",
        export_force_refresh=False,
        log_level="INFO",
    )
    client = ConfluenceClient(settings, transport=transport, sleep=lambda _d: None)
    attachments = [
        {
            "id": "att-1",
            "title": "diagram.png",
            "media_type": "image/png",
            "file_size": 9,
            "download_path": "/rest/api/content/att-1",
        }
    ]
    result = sync_page_assets(client, tmp_path, "42", attachments)
    assert result.page_failed is False
    _url, headers = transport.calls[0]
    assert "Authorization" not in headers


def test_inaccessible_cross_page_attachment_is_placeholder_not_failed(tmp_path: Path) -> None:
    transport = ScriptedTransport([HttpResponse(403, b"forbidden", {})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    attachments = [
        {
            "id": "att-other",
            "title": "secret.pdf",
            "media_type": "application/pdf",
            "file_size": 1,
            "download_path": "/download/attachments/99/secret.pdf",
        }
    ]
    result = sync_page_assets(client, tmp_path, "42", attachments)
    assert result.page_failed is False
    assert result.missing_placeholders == [missing_attachment_placeholder("secret.pdf")]
    assert result.missing_placeholders == ["[missing-attachment: secret.pdf]"]
    assert not (tmp_path / "03_assets" / "42" / "secret.pdf").exists()
    assert result.sidecar_path is None
    assert "/download/attachments/" not in transport.calls[0][0]


def test_sidecar_records_safe_names_after_collision(tmp_path: Path) -> None:
    transport = ScriptedTransport(
        [HttpResponse(200, b"a", {}), HttpResponse(200, b"b", {})]
    )
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    attachments = [
        {"id": "1", "title": "a/b.txt", "media_type": "text/plain", "file_size": 1, "download_path": ""},
        {"id": "2", "title": "a_b.txt", "media_type": "text/plain", "file_size": 1, "download_path": ""},
    ]
    result = sync_page_assets(client, tmp_path, "7", attachments)
    assert result.page_failed is False
    assert result.original_to_safe["a/b.txt"] != result.original_to_safe["a_b.txt"]
    sidecar = json.loads((tmp_path / "01_raw" / "7.assets.json").read_text(encoding="utf-8"))
    assert sidecar == result.original_to_safe
    for safe in sidecar.values():
        assert (tmp_path / "03_assets" / "7" / safe).is_file()
