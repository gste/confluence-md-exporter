"""Synchronous Confluence Server/DC REST client. Read-only GET, including attachment bytes."""

from __future__ import annotations

import base64
import html
import json
import logging
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

logger = logging.getLogger(__name__)

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
        probe_url = self._url(PROBE_PATH)
        logger.debug("Executing auth probe against %s", probe_url)
        response = self._request(probe_url)
        reason = _probe_failure_reason(response)
        if reason is not None:
            logger.debug("Auth probe failed: %s (status %d)", reason, response.status)
            raise AuthError(reason)
        logger.debug("Auth probe succeeded (status %d)", response.status)

    def fetch_version(self, page_id: str) -> int | None:
        query = urllib.parse.urlencode({"expand": "version"})
        url = self._url(f"/rest/api/content/{page_id}?{query}")
        logger.debug("Fetching page version for id=%s from %s", page_id, url)
        response = self._request(url)
        if response.status >= 400:
            logger.debug("Fetch version for page_id=%s failed with HTTP %d", page_id, response.status)
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        number = (payload.get("version") or {}).get("number")
        if number is None:
            return None
        try:
            ver = int(number)
            logger.debug("Fetched version for page_id=%s: %d", page_id, ver)
            return ver
        except (TypeError, ValueError):
            return None

    def fetch_page_version(self, page_id: str, version: int) -> PageFetchResult:
        try:
            logger.debug("Fetching specific page version id=%s version=%d", page_id, version)
            query = urllib.parse.urlencode({"version": version, "status": "historical", "expand": EXPAND})
            response = self._request(self._url(f"/rest/api/content/{page_id}?{query}"))
            if response.status == 200:
                payload = response.json()
                if isinstance(payload, dict) and payload.get("id"):
                    raw = _to_bronze(self._settings, payload, [])
                    logger.debug("Successfully fetched historical page id=%s version=%d", page_id, version)
                    return PageFetchResult("ok", None, raw["page_id"], raw["space_key"], raw["title"], raw)

            query_ver = urllib.parse.urlencode({
                "expand": "content.body.storage,content.version,content.space,content.history,content.metadata.labels"
            })
            response_ver = self._request(self._url(f"/rest/api/content/{page_id}/version/{version}?{query_ver}"))
            if response_ver.status == 200:
                payload_ver = response_ver.json()
                if isinstance(payload_ver, dict):
                    content = payload_ver.get("content")
                    if isinstance(content, dict):
                        content.setdefault("id", page_id)
                        content.setdefault("version", {
                            "number": payload_ver.get("number") or version,
                            "when": payload_ver.get("when"),
                            "by": payload_ver.get("by"),
                        })
                        raw = _to_bronze(self._settings, content, [])
                        logger.debug("Successfully fetched historical version via /version/ endpoint id=%s version=%d", page_id, version)
                        return PageFetchResult("ok", None, raw["page_id"], raw["space_key"], raw["title"], raw)

            # Check if current version matches requested version
            current = self._fetch_by_id(page_id)
            if current.status == "ok" and current.raw and int(current.raw.get("version") or 0) == version:
                logger.debug("Current version for page id=%s matches requested version=%d", page_id, version)
                return current

            logger.debug("Page id=%s version=%d not found", page_id, version)
            return PageFetchResult("failed", f"version_{version}_not_found", page_id, None, None, None)
        except Exception as exc:
            logger.debug("Exception fetching page id=%s version=%d: %s", page_id, version, exc)
            return PageFetchResult("failed", str(exc), page_id, None, None, None)

    def fetch_entry(self, entry: AcceptedEntry) -> PageFetchResult:
        try:
            if entry.needs_title_lookup:
                return self._fetch_display(entry)
            assert entry.page_id is not None
            return self._fetch_by_id(entry.page_id)
        except Exception as exc:
            logger.debug("Exception fetching page %s: %s", entry.raw, exc)
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
        url = self._url(f"/rest/api/content?{query}")
        logger.debug("Fetching page by title space=%s title=%r from %s", space, title, url)
        response = self._request(url)
        if response.status == 403:
            logger.debug("Forbidden accessing display page %s/%s", space, title)
            return PageFetchResult("failed", "forbidden", None, space, title, None)
        if response.status in {401, 404}:
            error = "unauthorized" if response.status == 401 else "not_found"
            status = "failed" if response.status == 401 else "skipped"
            logger.debug("Display page %s/%s returned HTTP %d (%s)", space, title, response.status, error)
            return PageFetchResult(status, error, None, space, title, None)
        payload = response.json() or {}
        results = payload.get("results") or []
        if not results:
            logger.debug("Display page %s/%s returned no results", space, title)
            return PageFetchResult("skipped", "not_found", None, space, title, None)
        found_id = str(results[0]["id"])
        logger.debug("Resolved display page %s/%s to id=%s", space, title, found_id)
        return self._fetch_by_id(found_id)

    def _fetch_by_id(self, page_id: str) -> PageFetchResult:
        query = urllib.parse.urlencode({"expand": EXPAND})
        url = self._url(f"/rest/api/content/{page_id}?{query}")
        logger.debug("Fetching page content id=%s from %s", page_id, url)
        response = self._request(url)
        if response.status == 403:
            logger.debug("Forbidden fetching page id=%s", page_id)
            return PageFetchResult("failed", "forbidden", page_id, None, None, None)
        if response.status == 401:
            logger.debug("Unauthorized fetching page id=%s", page_id)
            return PageFetchResult("failed", "unauthorized", page_id, None, None, None)
        if response.status == 404:
            logger.debug("Not found page id=%s", page_id)
            return PageFetchResult("skipped", "not_found", page_id, None, None, None)
        payload = response.json()
        if not isinstance(payload, dict):
            return PageFetchResult("failed", "invalid_json", page_id, None, None, None)
        status = str(payload.get("status") or "")
        if status == "trashed":
            logger.debug("Page id=%s is trashed, skipping", page_id)
            return PageFetchResult("skipped", "trashed", page_id, None, None, None)
        if payload.get("type") != "page":
            logger.debug("Page id=%s has unsupported type %s", page_id, payload.get("type"))
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
        logger.debug("Successfully fetched page id=%s title=%r (version=%s, %d attachment(s))", page_id, raw["title"], raw["version"], len(attachments))
        return PageFetchResult("ok", None, raw["page_id"], raw["space_key"], raw["title"], raw)

    def _list_attachments(self, page_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url = self._url(f"/rest/api/content/{page_id}/child/attachment")
        logger.debug("Listing attachments for page id=%s from %s", page_id, url)
        while url:
            response = self._request(url)
            if response.status >= 400:
                logger.debug("Failed listing attachments from %s: HTTP %d", url, response.status)
                break
            payload = response.json() or {}
            for item in payload.get("results") or []:
                items.append(_attachment_meta(item))
            next_link = (payload.get("_links") or {}).get("next")
            url = self._absolute(next_link) if next_link else ""
        logger.debug("Total attachments found for page id=%s: %d", page_id, len(items))
        return items

    def _request(self, url: str, *, accept: str = "application/json") -> HttpResponse:
        headers = self._headers(accept=accept)
        attempts = 1 + self._settings.confluence_max_retries
        last: HttpResponse | None = None
        for attempt in range(attempts):
            logger.debug("HTTP GET %s (attempt %d/%d)", url, attempt + 1, attempts)
            last = self._transport(url, headers)
            logger.debug("HTTP %d %s (size=%d bytes)", last.status, url, len(last.body))
            if last.status not in RETRY_STATUSES or attempt >= attempts - 1:
                return last
            delay = _retry_delay(last.headers, attempt)
            logger.debug("HTTP status %d is retriable; backing off for %.2fs", last.status, delay)
            self._sleep(delay)
        assert last is not None
        return last

    def attachment_download_url(self, attachment: Mapping[str, Any]) -> str:
        given = str(attachment.get("download_path") or "")
        if given and "/download/attachments/" not in given and "/rest/api/" in given:
            return self._absolute(given)
        attachment_id = str(attachment.get("id") or "")
        return self._url(f"/rest/api/content/{attachment_id}")

    def download(self, url: str) -> HttpResponse:
        logger.debug("Downloading attachment binary from %s", url)
        return self._request(url, accept="*/*")

    def _headers(self, *, accept: str = "application/json") -> dict[str, str]:
        settings = self._settings
        headers = {"Accept": accept}
        if settings.confluence_auth_type == "anonymous" or not settings.confluence_token:
            return headers
        if settings.confluence_auth_type == "bearer":
            headers["Authorization"] = f"Bearer {settings.confluence_token}"
        else:
            raw = f"{settings.confluence_username}:{settings.confluence_token}".encode("utf-8")
            headers["Authorization"] = f"Basic {base64.b64encode(raw).decode('ascii')}"
        return headers

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


_USER_IDENTITY_KEYS = ("username", "userKey", "accountId")


def _probe_failure_reason(response: HttpResponse) -> str | None:
    if response.status != 200:
        return f"auth probe failed: HTTP {response.status}"
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return "auth probe failed: response is not JSON"
    if not isinstance(payload, dict):
        return "auth probe failed: response is not JSON"
    if not any(payload.get(key) for key in _USER_IDENTITY_KEYS):
        return "auth probe failed: no user identity"
    return None


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
    page_id = str(payload.get("id") or "")
    space = payload.get("space") or {}
    version = payload.get("version") or {}
    history = payload.get("history") or {}
    author = version.get("by") or history.get("createdBy") or {}
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
        "created_by": str(author.get("displayName") or author.get("username") or author.get("accountId") or ""),
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
