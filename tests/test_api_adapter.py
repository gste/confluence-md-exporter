from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.settings import Settings
from confluence_md_exporter.url_resolver import AcceptedEntry

BASE = "https://confluence.example.com"


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "confluence_base_url": BASE,
        "confluence_edition": "datacenter",
        "confluence_auth_type": "bearer",
        "confluence_token": "dummy-token",
        "confluence_username": None,
        "confluence_verify_ssl": True,
        "confluence_timeout_seconds": 30,
        "confluence_max_retries": 3,
        "export_output_dir": "data",
        "export_input_file": "input/urls.txt",
        "export_force_refresh": False,
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _json(status: int, payload: object, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), headers or {})


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append((url, dict(headers)))
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


def _page_payload(*, page_id: str = "10", page_type: str = "page", status: str = "current") -> dict[str, object]:
    return {
        "id": page_id,
        "type": page_type,
        "status": status,
        "title": "Hello",
        "space": {"key": "DEV"},
        "version": {"number": 2, "when": "2026-01-01T00:00:00.000Z", "by": {"displayName": "Jane"}},
        "history": {"createdBy": {"displayName": "Jane"}},
        "body": {"storage": {"value": "<p>hi</p>"}},
        "metadata": {"labels": {"results": [{"name": "docs"}]}},
        "ancestors": [{"id": "1", "title": "Root"}],
        "_links": {"webui": "/pages/viewpage.action?pageId=" + page_id},
    }


def _attachments() -> dict[str, object]:
    return {"results": [], "_links": {}}


def test_content_expand_storage_only_without_wiki_prefix() -> None:
    transport = ScriptedTransport([_json(200, _page_payload()), _json(200, _attachments())])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    result = client.fetch_entry(AcceptedEntry("10", "10", None, None, False))
    assert result.status == "ok"
    assert result.raw is not None
    assert result.raw["edition"] == "datacenter"
    url = transport.calls[0][0]
    parsed = urlparse(url)
    assert parsed.path == "/rest/api/content/10"
    assert "/wiki/" not in parsed.path
    expand = (parse_qs(parsed.query).get("expand") or [""])[0]
    assert "body.storage" in expand.split(",")
    assert "body.view" not in expand
    assert "body.export_view" not in expand
    assert "body.atlas_doc_format" not in expand


def test_404_and_trashed_are_skipped() -> None:
    not_found = ScriptedTransport([_json(404, {"message": "no"})])
    client = ConfluenceClient(_settings(), transport=not_found, sleep=lambda _d: None)
    result = client.fetch_entry(AcceptedEntry("11", "11", None, None, False))
    assert result.status == "skipped"
    assert result.error == "not_found"

    trashed = ScriptedTransport([_json(200, _page_payload(status="trashed"))])
    client = ConfluenceClient(_settings(), transport=trashed, sleep=lambda _d: None)
    result = client.fetch_entry(AcceptedEntry("12", "12", None, None, False))
    assert result.status == "skipped"
    assert result.error == "trashed"


def test_403_is_failed_forbidden_without_retry() -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport([_json(403, {"message": "no"})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=sleeps.append)
    result = client.fetch_entry(AcceptedEntry("13", "13", None, None, False))
    assert result.status == "failed"
    assert result.error == "forbidden"
    assert sleeps == []
    assert len(transport.calls) == 1


def test_non_page_type_is_unsupported_content_type() -> None:
    transport = ScriptedTransport([_json(200, _page_payload(page_type="blogpost"))])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    result = client.fetch_entry(AcceptedEntry("14", "14", None, None, False))
    assert result.status == "failed"
    assert result.error == "unsupported_content_type"


def test_display_search_empty_is_skipped_with_null_id() -> None:
    transport = ScriptedTransport([_json(200, {"results": []})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    entry = AcceptedEntry("display", None, "DEV", "My Page", True)
    result = client.fetch_entry(entry)
    assert result.status == "skipped"
    assert result.page_id is None
    assert result.space_key == "DEV"
    assert result.title == "My Page"
    url = transport.calls[0][0]
    parsed = urlparse(url)
    assert parsed.path == "/rest/api/content"
    assert "/wiki/" not in parsed.path
    query = parse_qs(parsed.query)
    assert query["spaceKey"] == ["DEV"]
    assert query["title"] == ["My Page"]
    assert query["type"] == ["page"]


def test_rest_paths_use_application_base() -> None:
    transport = ScriptedTransport([_json(200, _page_payload()), _json(200, _attachments())])
    client = ConfluenceClient(
        _settings(confluence_base_url="https://confluence.example.com/confluence"),
        transport=transport,
        sleep=lambda _d: None,
    )
    result = client.fetch_entry(AcceptedEntry("10", "10", None, None, False))
    assert result.status == "ok"
    parsed = urlparse(transport.calls[0][0])
    assert parsed.path == "/confluence/rest/api/content/10"
    assert "/wiki/" not in parsed.path


def test_page_error_does_not_stop_the_batch() -> None:
    transport = ScriptedTransport(
        [
            _json(403, {}),
            _json(200, _page_payload(page_id="20")),
            _json(200, _attachments()),
        ]
    )
    client = ConfluenceClient(_settings(), transport=transport, sleep=lambda _d: None)
    results = client.fetch_entries(
        [
            AcceptedEntry("13", "13", None, None, False),
            AcceptedEntry("20", "20", None, None, False),
        ]
    )
    assert results[0].status == "failed"
    assert results[1].status == "ok"
    assert results[1].page_id == "20"
