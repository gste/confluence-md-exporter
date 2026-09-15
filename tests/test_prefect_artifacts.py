from __future__ import annotations

import inspect
import json
from pathlib import Path

import confluence_md_exporter.client as client_mod
import confluence_md_exporter.flow as flow_mod
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


class ScriptedTransport:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self._responses = list(responses)

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


def test_ok_page_gets_markdown_preview_and_run_summary_without_tokens(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "https://confluence.example.com/pages/viewpage.action?pageId=11\n",
        encoding="utf-8",
    )
    published: list[dict[str, object]] = []
    transport = ScriptedTransport(
        [
            _json(
                200,
                {
                    "id": "11",
                    "type": "page",
                    "status": "current",
                    "title": "Kept",
                    "space": {"key": "DEV"},
                    "version": {
                        "number": 1,
                        "when": "2026-01-01T00:00:00.000Z",
                        "by": {"displayName": "Jane"},
                    },
                    "history": {"createdBy": {"displayName": "Jane"}},
                    "body": {"storage": {"value": "<p>hello body</p>"}},
                    "metadata": {"labels": {"results": []}},
                    "ancestors": [],
                    "_links": {"webui": "/pages/viewpage.action?pageId=11"},
                },
            ),
            _json(200, {"results": [], "_links": {}}),
        ]
    )
    settings = _settings(tmp_path, urls)
    client = ConfluenceClient(settings, transport=transport, sleep=lambda _d: None)

    code = run_export(settings, client=client, publish=lambda **kw: published.append(kw))

    assert code == 0
    keys = {item.get("key") for item in published}
    assert "page-11" in keys
    assert "run-summary" in keys
    preview = next(item["markdown"] for item in published if item.get("key") == "page-11")
    summary = next(item["markdown"] for item in published if item.get("key") == "run-summary")
    assert isinstance(preview, str) and preview.strip()
    assert "hello body" in preview
    assert "ok:" in summary
    assert "failed:" in summary
    assert "skipped:" in summary
    assert "invalid_urls:" in summary
    assert "force_refresh:" in summary
    blob = "\n".join(str(item["markdown"]) for item in published)
    assert "dummy-token" not in blob
    assert settings.confluence_token not in blob


def test_run_summary_lists_each_invalid_url_and_reason(tmp_path: Path) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text(
        "\n".join(
            [
                "https://confluence.example.com/x/AbCdEf",
                "not-a-url",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    published: list[dict[str, object]] = []
    settings = _settings(tmp_path, urls)
    client = ConfluenceClient(settings, transport=ScriptedTransport([]), sleep=lambda _d: None)

    code = run_export(settings, client=client, publish=lambda **kw: published.append(kw))

    assert code == 0
    summary = next(item["markdown"] for item in published if item.get("key") == "run-summary")
    assert isinstance(summary, str)
    assert "https://confluence.example.com/x/AbCdEf: tiny_link" in summary
    assert "not-a-url: unrecognized_form" in summary
    report = json.loads((tmp_path / "data" / "run_report.json").read_text(encoding="utf-8"))
    assert report["invalid_urls"] == [
        {"url": "https://confluence.example.com/x/AbCdEf", "reason": "tiny_link"},
        {"url": "not-a-url", "reason": "unrecognized_form"},
    ]


def test_flow_does_not_call_confluence_write_api() -> None:
    blob = inspect.getsource(client_mod) + inspect.getsource(flow_mod)
    for verb in ("POST", "PUT", "DELETE", "PATCH"):
        assert f'method="{verb}"' not in blob
        assert f"method='{verb}'" not in blob
    assert 'method="GET"' in inspect.getsource(client_mod)
