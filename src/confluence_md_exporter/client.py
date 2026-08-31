"""Synchronous Confluence Server/DC REST client. Read-only; no attachment binaries."""

from __future__ import annotations

import base64
import html
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from confluence_md_exporter.output import EDITION, build_source_url
from confluence_md_exporter.settings import AuthError, ConfigError, Settings
from confluence_md_exporter.url_resolver import AcceptedEntry

RETRY_STATUSES = frozenset({429, 502, 503, 504})
EXPAND = "body.storage,version,space,history,metadata.labels,ancestors"
PROBE_PATH = "/rest/api/user/current"

SleepFn = Callable[[float], None]
TransportFn = Callable[[str, dict[str, str]], "HttpResponse"]


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


@dataclass(frozen=True)
class PageFetchResult:
    status: str
    error: str | None
    page_id: str | None
    space_key: str | None
    title: str | None
    raw: dict[str, Any] | None


class ConfluenceClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: TransportFn | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep or _default_sleep
        self._transport = transport or self._urllib_get

    def probe(self) -> None:
        response = self._request(self._url(PROBE_PATH))
        if response.status == 401:
            raise AuthError("authentication failed")

    def fetch_entry(self, entry: AcceptedEntry) -> PageFetchResult:
        try:
            if entry.needs_title_lookup:
                return self._fetch_display(entry)
            assert entry.page_id is not None
            return self._fetch_by_id(entry.page_id)
        except Exception as exc:
            return PageFetchResult(
                status="failed",
                error=str(exc),
                page_id=entry.page_id,
                space_key=entry.space_key,
                title=entry.title,
                raw=None,
            )

    def fetch_entries(self, entries: list[AcceptedEntry]) -> list[PageFetchResult]:
        return [self.fetch_entry(entry) for entry in entries]

    def _fetch_display(self, entry: AcceptedEntry) -> PageFetchResult:
        space = entry.space_key or ""
        title = entry.title or ""
        query = urllib.parse.urlencode({"spaceKey": space, "title": title, "type": "page"})
        response = self._request(self._url(f"/rest/api/content?{query}"))
        if response.status == 403:
            return PageFetchResult("failed", "forbidden", None, space, title, None)
        if response.status in {401, 404}:
            error = "unauthorized" if response.status == 401 else "not_found"
            status = "failed" if response.status == 401 else "skipped"
            return PageFetchResult(status, error, None, space, title, None)
        payload = response.json() or {}
        results = payload.get("results") or []
        if not results:
            return PageFetchResult("skipped", "not_found", None, space, title, None)
        found_id = str(results[0]["id"])
        return self._fetch_by_id(found_id)

    def _fetch_by_id(self, page_id: str) -> PageFetchResult:
        query = urllib.parse.urlencode({"expand": EXPAND})
        response = self._request(self._url(f"/rest/api/content/{page_id}?{query}"))
        if response.status == 403:
            return PageFetchResult("failed", "forbidden", page_id, None, None, None)
        if response.status == 401:
            return PageFetchResult("failed", "unauthorized", page_id, None, None, None)
        if response.status == 404:
            return PageFetchResult("skipped", "not_found", page_id, None, None, None)
        payload = response.json()
        if not isinstance(payload, dict):
            return PageFetchResult("failed", "invalid_json", page_id, None, None, None)
        status = str(payload.get("status") or "")
        if status == "trashed":
            return PageFetchResult("skipped", "trashed", page_id, None, None, None)
        if payload.get("type") != "page":
            return PageFetchResult(
                "failed",
                "unsupported_content_type",
                page_id,
                None,
                payload.get("title"),
                None,
            )
        attachments = self._list_attachments(page_id)
        raw = _to_bronze(self._settings, payload, attachments)
        return PageFetchResult("ok", None, raw["page_id"], raw["space_key"], raw["title"], raw)

    def _list_attachments(self, page_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url = self._url(f"/rest/api/content/{page_id}/child/attachment")
        while url:
            response = self._request(url)
            if response.status >= 400:
                break
            payload = response.json() or {}
            for item in payload.get("results") or []:
                items.append(_attachment_meta(item))
            next_link = (payload.get("_links") or {}).get("next")
            url = self._absolute(next_link) if next_link else ""
        return items

    def _request(self, url: str) -> HttpResponse:
        headers = self._headers()
        attempts = 1 + self._settings.confluence_max_retries
        last: HttpResponse | None = None
        for attempt in range(attempts):
            last = self._transport(url, headers)
            if last.status not in RETRY_STATUSES or attempt >= attempts - 1:
                return last
            self._sleep(_retry_delay(last.headers, attempt))
        assert last is not None
        return last

    def _headers(self) -> dict[str, str]:
        settings = self._settings
        if settings.confluence_auth_type == "bearer":
            authorization = f"Bearer {settings.confluence_token}"
        else:
            raw = f"{settings.confluence_username}:{settings.confluence_token}".encode("utf-8")
            authorization = f"Basic {base64.b64encode(raw).decode('ascii')}"
        return {"Authorization": authorization, "Accept": "application/json"}

    def _url(self, path: str) -> str:
        return self._settings.confluence_base_url + path

    def _absolute(self, url_or_path: str) -> str:
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            return url_or_path
        if url_or_path.startswith("/"):
            return self._settings.confluence_base_url + url_or_path
        return self._settings.confluence_base_url + "/" + url_or_path

    def _urllib_get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        parsed = urlparse(url)
        if "/wiki/" in parsed.path:
            raise ConfigError("Cloud /wiki API prefix is not used")
        context = ssl.create_default_context()
        if not self._settings.confluence_verify_ssl:
            context = ssl._create_unverified_context()
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            urllib.request.HTTPHandler(),
            urllib.request.HTTPRedirectHandler(),
        )
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with opener.open(request, timeout=self._settings.confluence_timeout_seconds) as response:
                return HttpResponse(int(response.status), response.read(), dict(response.headers))
        except urllib.error.HTTPError as exc:
            return HttpResponse(int(exc.code), exc.read() if exc.fp else b"", dict(exc.headers or {}))
        except urllib.error.URLError as exc:
            raise ConfigError(f"HTTP request failed: {exc.reason}") from exc


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is not None:
        try:
            return max(0.0, float(int(raw)))
        except ValueError:
            pass
    return float(2**attempt)


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _to_bronze(settings: Settings, payload: dict[str, Any], attachments: list[dict[str, Any]]) -> dict[str, Any]:
    page_id = str(payload["id"])
    space = payload.get("space") or {}
    version = payload.get("version") or {}
    history = payload.get("history") or {}
    created = history.get("createdBy") or version.get("by") or {}
    labels = [
        str(item.get("name"))
        for item in ((payload.get("metadata") or {}).get("labels") or {}).get("results") or []
        if item.get("name")
    ]
    ancestors = [
        {"id": str(item.get("id")), "title": html.unescape(str(item.get("title") or ""))}
        for item in payload.get("ancestors") or []
    ]
    webui = (payload.get("_links") or {}).get("webui")
    body = ((payload.get("body") or {}).get("storage") or {}).get("value") or ""
    return {
        "page_id": page_id,
        "edition": EDITION,
        "title": html.unescape(str(payload.get("title") or "")),
        "space_key": str(space.get("key") or ""),
        "version": int(version.get("number") or 0),
        "status": str(payload.get("status") or ""),
        "created_by": str(created.get("displayName") or created.get("username") or created.get("accountId") or ""),
        "updated_at": str(version.get("when") or ""),
        "source_url": build_source_url(settings.confluence_base_url, page_id, webui),
        "labels": labels,
        "ancestors": ancestors,
        "body_storage": body,
        "attachments": attachments,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _attachment_meta(item: dict[str, Any]) -> dict[str, Any]:
    extensions = item.get("extensions") or {}
    download = (item.get("_links") or {}).get("download") or ""
    return {
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "media_type": str(extensions.get("mediaType") or ""),
        "file_size": int(extensions.get("fileSize") or 0),
        "download_path": str(download),
    }
