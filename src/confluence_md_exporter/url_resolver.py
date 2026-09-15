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
    return unique[0]


def resolve_input_file(path: str | Path, base_url: str) -> ResolveResult:
    file_path = Path(path)
    if not file_path.is_file():
        raise ConfigError(f"input file does not exist: {path}")

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
        page_ids = query.get("pageId") or []
        if len(page_ids) != 1 or not _BARE_PAGE_ID.fullmatch(page_ids[0]):
            return InvalidUrl(url=raw, reason=REASON_MALFORMED)
        
        versions_raw: list[str] = []
        if "selectedPageVersions" in query:
            for item in query["selectedPageVersions"]:
                versions_raw.extend(re.split(r"[,;]+", item))
        elif "originalVersion" in query and "revisedVersion" in query:
            versions_raw.extend(query["originalVersion"])
            versions_raw.extend(query["revisedVersion"])

        valid_versions: list[int] = []
        for v in versions_raw:
            v_str = v.strip()
            if _BARE_PAGE_ID.fullmatch(v_str):
                valid_versions.append(int(v_str))

        if len(valid_versions) != 2 or valid_versions[0] == valid_versions[1]:
            return InvalidUrl(url=raw, reason=REASON_MALFORMED)

        v1, v2 = sorted(valid_versions)
        return AcceptedEntry(
            raw=raw,
            page_id=page_ids[0],
            space_key=None,
            title=None,
            needs_title_lookup=False,
            is_diff=True,
            diff_versions=(v1, v2),
        )

    display = _DISPLAY.fullmatch(path)
    if display:
        space_key = unquote_plus(display.group(1))
        title = unquote_plus(display.group(2))
        if not space_key or not title:
            return InvalidUrl(url=raw, reason=REASON_MALFORMED)
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

    if _is_tiny_link(path):
        return InvalidUrl(url=raw, reason=REASON_TINY_LINK)
    return InvalidUrl(url=raw, reason=REASON_UNRECOGNIZED)


def _is_tiny_link(path: str) -> bool:
    return _TINY_LINK.search(path) is not None or "tinyurl.action" in path


def _base_from_absolute(stripped: str) -> str | None:
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    path = parsed.path or ""
    marker_at: int | None = None
    for marker in _BASE_MARKERS:
        idx = path.find(marker)
        if idx == -1:
            continue
        if marker_at is None or idx < marker_at:
            marker_at = idx
    if marker_at is None:
        return None
    prefix = path[:marker_at].rstrip("/")
    if "wiki" in {segment for segment in prefix.split("/") if segment}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{prefix}"


def _to_absolute(stripped: str, base_url: str) -> str | None:
    if stripped.startswith("/"):
        origin = _origin(base_url)
        if not origin:
            return None
        return origin + stripped
    parsed = urlparse(stripped)
    if parsed.scheme and parsed.netloc:
        return stripped
    return None


def _on_base(absolute: str, base_url: str) -> bool:
    parsed_url = urlparse(absolute)
    parsed_base = urlparse(base_url)
    if parsed_url.scheme != parsed_base.scheme or parsed_url.netloc != parsed_base.netloc:
        return False
    base_path = (parsed_base.path or "").rstrip("/")
    url_path = parsed_url.path or ""
    if not base_path:
        return True
    return url_path == base_path or url_path.startswith(base_path + "/")


def _path_relative_to_base(absolute: str, base_url: str) -> str | None:
    if not _on_base(absolute, base_url):
        return None
    base_path = (urlparse(base_url).path or "").rstrip("/")
    url_path = urlparse(absolute).path or ""
    if not base_path:
        return url_path
    remainder = url_path[len(base_path) :]
    return remainder if remainder else "/"


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
