"""Resolve the input URL list into unique pages and invalid lines. No network."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urljoin, urlparse

from confluence_md_exporter.settings import ConfigError

logger = logging.getLogger(__name__)

_VIEWPAGE_PATH = "/pages/viewpage.action"
_DISPLAY = re.compile(r"^/display/([^/]+)/(.+)$")
_WIKI_PAGE = re.compile(r"^/wiki/spaces/([^/]+)/pages/(\d+)(?:/.*)?$")
_BARE_PAGE_ID = re.compile(r"^\d+$")


@dataclass(frozen=True)
class AcceptedEntry:
    raw: str
    page_id: str | None
    space_key: str | None
    title: str | None
    needs_title_lookup: bool


@dataclass(frozen=True)
class ResolveResult:
    entries: tuple[AcceptedEntry, ...]
    invalid_urls: tuple[str, ...]
    pages_total: int


def resolve_input_file(path: str | Path, base_url: str) -> ResolveResult:
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"input file does not exist: {path}")

    text = file_path.read_text(encoding="utf-8")
    accepted: list[AcceptedEntry] = []
    invalid: list[str] = []
    seen: dict[str, AcceptedEntry] = {}

    for raw in text.splitlines():
        if _is_blank_or_comment(raw):
            continue
        entry = _parse_line(raw, base_url)
        if entry is None:
            invalid.append(raw)
            continue
        key = _dedup_key(entry)
        if key in seen:
            logger.warning("duplicate page collapsed: %s", raw)
            continue
        seen[key] = entry
        accepted.append(entry)

    return ResolveResult(
        entries=tuple(accepted),
        invalid_urls=tuple(invalid),
        pages_total=len(accepted),
    )


def _is_blank_or_comment(raw: str) -> bool:
    stripped = raw.lstrip()
    return not stripped or stripped.startswith("#")


def _dedup_key(entry: AcceptedEntry) -> str:
    if entry.page_id is not None:
        return f"id:{entry.page_id}"
    return f"display:{entry.space_key}:{entry.title}"


def _parse_line(raw: str, base_url: str) -> AcceptedEntry | None:
    stripped = raw.strip()
    if _BARE_PAGE_ID.fullmatch(stripped):
        return AcceptedEntry(
            raw=raw,
            page_id=stripped,
            space_key=None,
            title=None,
            needs_title_lookup=False,
        )

    absolute = _to_absolute(stripped, base_url)
    if absolute is None:
        return None
    if _origin(absolute) != base_url:
        return None

    parsed = urlparse(absolute)
    path = parsed.path or ""
    query = parse_qs(parsed.query)

    if path == _VIEWPAGE_PATH:
        page_ids = query.get("pageId") or []
        if len(page_ids) != 1 or not _BARE_PAGE_ID.fullmatch(page_ids[0]):
            return None
        return AcceptedEntry(
            raw=raw,
            page_id=page_ids[0],
            space_key=None,
            title=None,
            needs_title_lookup=False,
        )

    display = _DISPLAY.fullmatch(path)
    if display:
        space_key = unquote_plus(display.group(1))
        title = unquote_plus(display.group(2))
        if not space_key or not title:
            return None
        return AcceptedEntry(
            raw=raw,
            page_id=None,
            space_key=space_key,
            title=title,
            needs_title_lookup=True,
        )

    wiki = _WIKI_PAGE.fullmatch(path)
    if wiki:
        return AcceptedEntry(
            raw=raw,
            page_id=wiki.group(2),
            space_key=unquote_plus(wiki.group(1)),
            title=None,
            needs_title_lookup=False,
        )

    return None


def _to_absolute(stripped: str, base_url: str) -> str | None:
    if stripped.startswith("/"):
        return urljoin(base_url + "/", stripped)
    parsed = urlparse(stripped)
    if parsed.scheme and parsed.netloc:
        return stripped
    return None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
