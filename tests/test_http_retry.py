from __future__ import annotations

import json

from confluence_md_exporter.client import ConfluenceClient, HttpResponse
from confluence_md_exporter.settings import Settings
from confluence_md_exporter.url_resolver import AcceptedEntry


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "confluence_base_url": "https://confluence.example.com",
        "confluence_edition": "datacenter",
        "confluence_auth_type": "bearer",
        "confluence_token": "dummy-token",
        "confluence_username": None,
        "confluence_verify_ssl": True,
        "confluence_timeout_seconds": 30,
        "confluence_max_retries": 3,
        "export_output_dir": "data",
        "export_input_file": "input/urls.txt",
        "export_concurrency": 2,
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
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.calls.append(url)
        if not self._responses:
            raise AssertionError(f"unexpected request: {url}")
        return self._responses.pop(0)


def test_retries_429_and_5xx_respect_retry_after() -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport(
        [
            _json(429, {}, {"Retry-After": "5"}),
            _json(503, {}),
            _json(200, {"username": "jdoe"}),
        ]
    )
    client = ConfluenceClient(_settings(), transport=transport, sleep=sleeps.append)
    client.probe()
    assert sleeps == [5.0, 2.0]
    assert len(transport.calls) == 3


def test_403_is_not_retried() -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport([_json(403, {})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=sleeps.append)
    result = client.fetch_entry(AcceptedEntry("1", "1", None, None, False))
    assert result.status == "failed"
    assert result.error == "forbidden"
    assert sleeps == []
    assert len(transport.calls) == 1


def test_401_is_not_retried_on_probe() -> None:
    sleeps: list[float] = []
    transport = ScriptedTransport([_json(401, {})])
    client = ConfluenceClient(_settings(), transport=transport, sleep=sleeps.append)
    try:
        client.probe()
    except Exception:
        pass
    assert sleeps == []
    assert len(transport.calls) == 1
