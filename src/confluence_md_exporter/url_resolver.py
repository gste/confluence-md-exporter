"""Resolve the input URL list into unique pages and invalid lines. No network."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote_plus, urlparse

from confluence_md_exporter.settings import ConfigError

logger = logging.getLogger(__name__)

_VIEWPAGE_PATH = "/pages/viewpage.action"
_DIFFPAGE_PATH = "/pages/diffpagesbyversion.action"
_DISPLAY = re.compile(r"^/display/([^/]+)/(.+)$")
_WIKI_PAGE = re.compile(r"^/wiki/spaces/([^/]+)/pages/(\d+)(?:/.*)?$")
_BARE_PAGE_ID = re.compile(r"^\d+$")
_TINY_LINK = re.compile(r"(?:^|/)x/[^/]+$")
_BASE_MARKERS = (
    "/pages/viewpage.action",
    "/pages/diffpagesbyversion.action",
    "/display/",
    "/wiki/spaces/",
)

REASON_TINY_LINK = "tiny_link"
REASON_ORIGIN_MISMATCH = "origin_mismatch"
REASON_MALFORMED = "malformed"
REASON_UNRECOGNIZED = "unrecognized_form"


@dataclass(frozen=True)
class AcceptedEntry:
    raw: str
    page_id: str | None
    space_key: str | None
    title: str | None
    needs_title_lookup: bool
    is_diff: bool = False
    diff_versions: tuple[int, int] | None = None


@dataclass(frozen=True)
class InvalidUrl:
    url: str
    reason: str

    def as_report(self) -> dict[str, str]:
        return {"url": self.url, "reason": self.reason}


@dataclass(frozen=True)
class ResolveResult:
    entries: tuple[AcceptedEntry, ...]
    invalid_urls: tuple[InvalidUrl, ...]
    pages_total: int


def infer_base_url(path: str | Path) -> str:
    """Derive the application base from absolute URLs in the input list."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"input file does not exist: {path}")

    logger.debug("Inferring base URL from input file: %s", path)
    found: list[str] = []
    for raw in file_path.read_text(encoding="utf-8").splitlines():
        if _is_blank_or_comment(raw):
            continue
        base = _base_from_absolute(raw.strip())
        if base is not None:
            found.append(base)

    unique = list(dict.fromkeys(found))
    if not unique:
        raise ConfigError(
            "cannot infer CONFLUENCE_BASE_URL from input; add a full page URL or pass --base-url"
        )
    if len(unique) > 1:
        raise ConfigError("input URLs point to different Confluence bases: " + ", ".join(unique))
    logger.debug("Successfully inferred base URL: %s", unique[0])
    return unique[0]


def resolve_input_file(path: str | Path, base_url: str) -> ResolveResult:
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"input file does not exist: {path}")

    logger.debug("Resolving input URL list from %s against base %s", path, base_url)
    text = file_path.read_text(encoding="utf-8")
    accepted: list[AcceptedEntry] = []
    invalid: list[InvalidUrl] = []
    seen: dict[str, AcceptedEntry] = {}

    for raw in text.splitlines():
        if _is_blank_or_comment(raw):
            continue
        parsed = _parse_line(raw, base_url)
        if isinstance(parsed, InvalidUrl):
            logger.warning("invalid url rejected: %s reason=%s", parsed.url, parsed.reason)
            invalid.append(parsed)
            continue
        key = _dedup_key(parsed)
        if key in seen:
            logger.warning("duplicate page collapsed: %s", raw)
            continue
        seen[key] = parsed
        accepted.append(parsed)
        logger.debug("Accepted entry: %s (page_id=%s, space_key=%s, title=%s)", raw, parsed.page_id, parsed.space_key, parsed.title)

    logger.debug("Resolved input summary: %d accepted, %d invalid", len(accepted), len(invalid))
    return ResolveResult(
        entries=tuple(accepted),
        invalid_urls=tuple(invalid),
        pages_total=len(accepted),
    )


def _is_blank_or_comment(raw: str) -> bool:
    stripped = raw.lstrip()
    return not stripped or stripped.startswith("#")


def _dedup_key(entry: AcceptedEntry) -> str:
    if entry.is_diff and entry.diff_versions:
        return f"diff:{entry.page_id}:{entry.diff_versions[0]}:{entry.diff_versions[1]}"
    if entry.page_id is not None:
        return f"id:{entry.page_id}"
    return f"display:{entry.space_key}:{entry.title}"


def _parse_line(raw: str, base_url: str) -> AcceptedEntry | InvalidUrl:
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
        return InvalidUrl(url=raw, reason=REASON_UNRECOGNIZED)
    if _origin(absolute) != _origin(base_url):
        return InvalidUrl(url=raw, reason=REASON_ORIGIN_MISMATCH)
    path = _path_relative_to_base(absolute, base_url)
    if path is None:
        return InvalidUrl(url=raw, reason=REASON_UNRECOGNIZED)
    query = parse_qs(urlparse(absolute).query)

    if path == _VIEWPAGE_PATH:
        page_ids = query.get("pageId") or []
        if len(page_ids) != 1 or not _BARE_PAGE_ID.fullmatch(page_ids[0]):
            return InvalidUrl(url=raw, reason=REASON_MALFORMED)
        return AcceptedEntry(
            raw=raw,
            page_id=page_ids[0],
            space_key=None,
            title=None,
            needs_title_lookup=False,
        )

    if path == _DIFFPAGE_PATH:
        page_ids = query.get("pageId") or query.get("originalId") or []
        selected_pages = query.get("selectedPageVersions") or []
        orig_ver = query.get("originalVersion") or []
        rev_ver = query.get("revisedVersion") or []

        diff_pair: tuple[int, int] | None = None
        if selected_pages and len(selected_pages) == 2:
            try:
                diff_pair = (int(selected_pages[0]), int(selected_pages[1]))
            except ValueError:
                pass
        elif orig_ver and rev_ver:
            try:
                diff_pair = (int(orig_ver[0]), int(rev_ver[0]))
            except ValueError:
                pass

        if len(page_ids) != 1 or not _BARE_PAGE_ID.fullmatch(page_ids[0]) or diff_pair is None:
            return InvalidUrl(url=raw, reason=REASON_MALFORMED)

        return AcceptedEntry(
            raw=raw,
            page_id=page_ids[0],
            space_key=None,
            title=None,
            needs_title_lookup=False,
            is_diff=True,
            diff_versions=diff_pair,
        )

    display_match = _DISPLAY.match(path)
    if display_match:
        space_key, raw_title = display_match.groups()
        title = unquote_plus(raw_title)
        return AcceptedEntry(
            raw=raw,
            page_id=None,
            space_key=space_key,
            title=title,
            needs_title_lookup=True,
        )

    wiki_match = _WIKI_PAGE.match(path)
    if wiki_match:
        space_key, page_id = wiki_match.groups()
        return AcceptedEntry(
            raw=raw,
            page_id=page_id,
            space_key=space_key,
            title=None,
            needs_title_lookup=False,
        )

    if _TINY_LINK.search(path):
        return InvalidUrl(url=raw, reason=REASON_TINY_LINK)

    return InvalidUrl(url=raw, reason=REASON_UNRECOGNIZED)


def _to_absolute(raw: str, base_url: str) -> str | None:
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{raw}"
    return None


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _path_relative_to_base(url: str, base_url: str) -> str | None:
    parsed = urlparse(url)
    base_parsed = urlparse(base_url)
    base_prefix = (base_parsed.path or "").rstrip("/")
    path = parsed.path or ""
    if base_prefix and not path.startswith(base_prefix):
        return None
    trimmed = path[len(base_prefix):]
    return trimmed if trimmed.startswith("/") or not trimmed else "/" + trimmed


def _base_from_absolute(url: str) -> str | None:
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    parsed = urlparse(url)
    path = parsed.path or ""
    for marker in _BASE_MARKERS:
        idx = path.find(marker)
        if idx != -1:
            context = path[:idx].rstrip("/")
            return f"{parsed.scheme}://{parsed.netloc}{context}".rstrip("/")
    return None
