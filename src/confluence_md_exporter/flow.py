"""Export run: isolate pages, support diff URLs, write catalog/report, log progress."""

from __future__ import annotations

import difflib
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from confluence_md_exporter.assets import sync_page_assets
from confluence_md_exporter.client import ConfluenceClient, PageFetchResult
from confluence_md_exporter.disk_skip import sync_page
from confluence_md_exporter.layout import asset_sidecar_path, assets_dir_path, slugify
from confluence_md_exporter.output import (
    write_bronze,
    write_diff_markdown,
    write_gold_markdown,
    write_interim,
    write_manifest,
    write_run_report,
)
from confluence_md_exporter.settings import Settings
from confluence_md_exporter.transform import BatchPage, TransformContext, transform_storage
from confluence_md_exporter.url_resolver import AcceptedEntry, resolve_input_file

PREVIEW_LIMIT = 8000
PublishFn = Callable[..., Any]
logger = logging.getLogger(__name__)


@dataclass
class PageOutcome:
    status: str
    error: str | None
    page_id: str | None
    title: str | None
    space_key: str | None
    version: int | None
    source_url: str | None
    md_path: str | None
    assets_dir: str | None
    labels: list[str] = field(default_factory=list)
    markdown: str | None = None


def run_export(
    settings: Settings,
    *,
    client: ConfluenceClient | None = None,
    publish: PublishFn | None = None,
    clean: bool = False,
) -> int:
    started = _now()
    started_mono = time.monotonic()
    output_dir = Path(settings.export_output_dir)
    logger.debug("Starting export run. Output directory: %s, Clean: %s", output_dir, clean)
    if clean and output_dir.exists():
        logger.debug("Wiping output directory %s before export", output_dir)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resolved = resolve_input_file(settings.export_input_file, settings.confluence_base_url)
    http = client or ConfluenceClient(settings)
    publisher = publish if publish is not None else _noop_publish
    total = len(resolved.entries)
    logger.info(
        "Export %s page(s), %s invalid URL(s) from %s -> %s%s",
        total,
        len(resolved.invalid_urls),
        settings.export_input_file,
        settings.export_output_dir,
        ", force-refresh" if settings.export_force_refresh else "",
    )
    logger.debug("Resolved %d page entries for processing", total)

    fetches = _fetch_all(http, output_dir, resolved.entries, settings)
    batch_pages = _batch_pages(fetches)
    outcomes: list[PageOutcome] = []
    for index, (entry, fetch) in enumerate(zip(resolved.entries, fetches), start=1):
        if entry.is_diff and entry.diff_versions:
            logger.debug("[%s/%s] Processing diff page: %s", index, total, entry.raw)
            outcome = _finish_diff_page(output_dir, settings, http, entry, publisher)
        else:
            logger.debug("[%s/%s] Processing page: %s", index, total, _entry_ref(entry))
            outcome = _finish_page(output_dir, settings, fetch, batch_pages, publisher)
        logger.info("[%s/%s] write %s -> %s%s", index, total, _entry_ref(entry), outcome.status, _outcome_extra(outcome))
        outcomes.append(outcome)

    records = [_manifest_row(item) for item in outcomes]
    logger.debug("Writing manifest (%d records) to %s", len(records), output_dir)
    write_manifest(output_dir, records)
    errors = [
        {"page_id": item.page_id, "error": item.error}
        for item in outcomes
        if item.error and item.status in {"failed", "skipped"}
    ]
    ok = sum(1 for item in outcomes if item.status == "ok")
    failed = sum(1 for item in outcomes if item.status == "failed")
    skipped = sum(1 for item in outcomes if item.status == "skipped")
    invalid_urls = [item.as_report() for item in resolved.invalid_urls]
    logger.debug("Writing run report with %d errors and %d invalid URLs", len(errors), len(invalid_urls))
    write_run_report(
        output_dir,
        {
            "started_at": started,
            "finished_at": _now(),
            "pages_total": resolved.pages_total,
            "ok": ok,
            "failed": failed,
            "skipped": skipped,
            "invalid_urls": invalid_urls,
            "force_refresh": settings.export_force_refresh,
            "errors": errors,
        },
    )
    publisher(
        markdown=_summary_markdown(ok, failed, skipped, invalid_urls, settings.export_force_refresh, errors),
        key="run-summary",
        description="Export run summary",
    )
    elapsed = time.monotonic() - started_mono
    logger.debug("Export completed in %.2fs. ok=%d failed=%d skipped=%d invalid=%d", elapsed, ok, failed, skipped, len(invalid_urls))
    logger.info(
        "Done ok=%s failed=%s skipped=%s invalid=%s in %.1fs",
        ok,
        failed,
        skipped,
        len(invalid_urls),
        elapsed,
    )
    return 1 if failed else 0


def _fetch_all(
    client: ConfluenceClient,
    output_dir: Path,
    entries: Sequence[AcceptedEntry],
    settings: Settings,
) -> list[PageFetchResult]:
    total = len(entries)
    results: list[PageFetchResult] = []
    logger.debug("Starting fetch phase for %d entries...", total)
    for index, entry in enumerate(entries, start=1):
        fetch = _fetch_one(client, output_dir, entry, settings.export_force_refresh)
        logger.info(
            "[%s/%s] fetch %s -> %s%s",
            index,
            total,
            _entry_ref(entry),
            fetch.status,
            _fetch_extra(fetch),
        )
        results.append(fetch)
    logger.debug("Fetch phase complete.")
    return results


def _fetch_one(
    client: ConfluenceClient,
    output_dir: Path,
    entry: AcceptedEntry,
    force_refresh: bool,
) -> PageFetchResult:
    try:
        if entry.is_diff:
            logger.debug("Entry is diff, skipping pre-fetch: %s", entry.raw)
            return PageFetchResult("ok", None, entry.page_id, None, None, None)
        if entry.page_id and not entry.needs_title_lookup:
            logger.debug("Syncing page id=%s (force_refresh=%s)", entry.page_id, force_refresh)
            return sync_page(client, output_dir, entry.page_id, force_refresh=force_refresh)
        logger.debug("Fetching entry by title/raw: %s", entry.raw)
        result = client.fetch_entry(entry)
        if result.status == "ok" and result.raw is not None and result.page_id:
            logger.debug("Writing bronze for page id=%s", result.page_id)
            write_bronze(output_dir, result.raw)
            sync_page_assets(client, output_dir, result.page_id, result.raw.get("attachments") or [])
        return result
    except Exception as exc:
        logger.debug("Exception fetching entry %s: %s", entry.raw, exc)
        return PageFetchResult("failed", str(exc), entry.page_id, entry.space_key, entry.title, None)


def _finish_page(
    output_dir: Path,
    settings: Settings,
    fetch: PageFetchResult,
    batch_pages: Sequence[BatchPage],
    publish: PublishFn,
) -> PageOutcome:
    if fetch.status != "ok" or fetch.raw is None or fetch.page_id is None:
        logger.debug("Page id=%s fetch status is %s; bypassing gold transformation", fetch.page_id, fetch.status)
        return _outcome_from_fetch(output_dir, fetch)
    try:
        return _write_ok_page(output_dir, settings, fetch, batch_pages, publish)
    except Exception as exc:
        logger.debug("Exception writing page id=%s: %s", fetch.page_id, exc)
        return PageOutcome(
            status="failed",
            error=str(exc),
            page_id=fetch.page_id,
            title=fetch.title,
            space_key=fetch.space_key,
            version=_raw_version(fetch.raw),
            source_url=(fetch.raw or {}).get("source_url"),
            md_path=None,
            assets_dir=assets_dir_path(fetch.page_id) if fetch.page_id else None,
            labels=list((fetch.raw or {}).get("labels") or []),
        )


def _finish_diff_page(
    output_dir: Path,
    settings: Settings,
    client: ConfluenceClient,
    entry: AcceptedEntry,
    publish: PublishFn,
) -> PageOutcome:
    page_id = entry.page_id or ""
    if not entry.diff_versions:
        return PageOutcome("failed", "invalid_diff_versions", page_id, None, None, None, None, None, None)
    v1, v2 = entry.diff_versions
    logger.debug("Building diff for page id=%s (v%d -> v%d)", page_id, v1, v2)
    fetch_v1 = client.fetch_page_version(page_id, v1)
    fetch_v2 = client.fetch_page_version(page_id, v2)

    if fetch_v1.status != "ok" or not fetch_v1.raw:
        logger.debug("Diff fetch failed for v%d of page id=%s", v1, page_id)
        return PageOutcome("failed", fetch_v1.error or f"version_{v1}_failed", page_id, None, None, None, None, None, None)
    if fetch_v2.status != "ok" or not fetch_v2.raw:
        logger.debug("Diff fetch failed for v%d of page id=%s", v2, page_id)
        return PageOutcome("failed", fetch_v2.error or f"version_{v2}_failed", page_id, None, None, None, None, None, None)

    raw1 = fetch_v1.raw
    raw2 = fetch_v2.raw
    title = str(raw2.get("title") or raw1.get("title") or f"page_{page_id}")
    space_key = str(raw2.get("space_key") or raw1.get("space_key") or "")
    slug = slugify(title)

    ctx1 = TransformContext(page_id=page_id, original_to_safe={}, attachments=[], batch_pages=(), base_url=settings.confluence_base_url)
    ctx2 = TransformContext(page_id=page_id, original_to_safe={}, attachments=[], batch_pages=(), base_url=settings.confluence_base_url)
    t1 = transform_storage(str(raw1.get("body_storage") or ""), context=ctx1)
    t2 = transform_storage(str(raw2.get("body_storage") or ""), context=ctx2)

    lines1 = (t1.markdown or "").splitlines(keepends=True)
    lines2 = (t2.markdown or "").splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        lines1,
        lines2,
        fromfile=f"v{v1}.md",
        tofile=f"v{v2}.md",
        lineterm="",
    ))
    diff_text = "".join(line if line.endswith("\n") else line + "\n" for line in diff_lines)

    lines_added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    lines_removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

    frontmatter = {
        "id": page_id,
        "title": title,
        "space_key": space_key,
        "version_from": v1,
        "version_to": v2,
        "created_by_from": str(raw1.get("created_by") or ""),
        "updated_at_from": str(raw1.get("updated_at") or ""),
        "created_by_to": str(raw2.get("created_by") or ""),
        "updated_at_to": str(raw2.get("updated_at") or ""),
        "source_url": entry.raw,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
    }

    body = (
        f"\n# Diff: {title} (v{v1} -> v{v2})\n\n"
        f"- **Page ID**: {page_id}\n"
        f"- **Space**: {space_key}\n"
        f"- **From**: Version {v1} by *{frontmatter['created_by_from']}* ({frontmatter['updated_at_from']})\n"
        f"- **To**: Version {v2} by *{frontmatter['created_by_to']}* ({frontmatter['updated_at_to']})\n"
        f"- **Changes**: +{lines_added} / -{lines_removed} lines\n\n"
        f"## Unified Diff\n\n"
        f"```diff\n{diff_text}```\n"
    )

    path = write_diff_markdown(output_dir, page_id, slug, v1, v2, frontmatter, body)
    logger.debug("Saved diff markdown: %s", path)
    publish(
        markdown=f"# Diff v{v1} -> v{v2} for {page_id}\n\n+{lines_added} / -{lines_removed} lines\n",
        key=f"diff-{page_id}-v{v1}-v{v2}",
        description=f"Diff v{v1}->v{v2} preview for {page_id}",
    )
    return PageOutcome(
        status="ok",
        error=None,
        page_id=page_id,
        title=title,
        space_key=space_key,
        version=v2,
        source_url=entry.raw,
        md_path=path.relative_to(output_dir).as_posix(),
        assets_dir=None,
        labels=list(raw2.get("labels") or []),
        markdown=body,
    )


def _write_ok_page(
    output_dir: Path,
    settings: Settings,
    fetch: PageFetchResult,
    batch_pages: Sequence[BatchPage],
    publish: PublishFn,
) -> PageOutcome:
    raw = fetch.raw or {}
    page_id = fetch.page_id or ""
    logger.debug("Writing interim storage for page id=%s", page_id)
    write_interim(output_dir, page_id, str(raw.get("body_storage") or ""))
    logger.debug("Transforming storage XHTML to Markdown for page id=%s", page_id)
    transformed = transform_storage(
        str(raw.get("body_storage") or ""),
        context=TransformContext(
            page_id=page_id,
            original_to_safe=_load_sidecar(output_dir, page_id),
            attachments=list(raw.get("attachments") or []),
            batch_pages=tuple(batch_pages),
            base_url=settings.confluence_base_url,
        ),
    )
    if transformed.failed:
        logger.debug("Transformation failed for page id=%s: %s", page_id, transformed.error)
        return PageOutcome(
            status="failed",
            error=transformed.error or "invalid_xml",
            page_id=page_id,
            title=str(raw.get("title") or "") or None,
            space_key=str(raw.get("space_key") or "") or None,
            version=_raw_version(raw),
            source_url=str(raw.get("source_url") or "") or None,
            md_path=None,
            assets_dir=assets_dir_path(page_id),
            labels=list(raw.get("labels") or []),
        )
    frontmatter = _frontmatter(raw, transformed.unsupported_macros)
    path = write_gold_markdown(output_dir, page_id, frontmatter, transformed.markdown)
    logger.debug("Saved gold markdown for page id=%s -> %s", page_id, path)
    gold = path.read_text(encoding="utf-8")
    publish(
        markdown=_preview(gold),
        key=f"page-{page_id}",
        description=f"Markdown preview for page {page_id}",
    )
    return PageOutcome(
        status="ok",
        error=None,
        page_id=page_id,
        title=str(frontmatter["title"]),
        space_key=str(raw.get("space_key") or "") or None,
        version=_raw_version(raw),
        source_url=str(raw.get("source_url") or "") or None,
        md_path=path.relative_to(output_dir).as_posix(),
        assets_dir=assets_dir_path(page_id),
        labels=list(raw.get("labels") or []),
        markdown=gold,
    )


def _outcome_from_fetch(output_dir: Path, fetch: PageFetchResult) -> PageOutcome:
    raw = fetch.raw or {}
    page_id = fetch.page_id
    md_path = _existing_md(output_dir, page_id) if page_id else None
    return PageOutcome(
        status=fetch.status,
        error=fetch.error,
        page_id=page_id,
        title=fetch.title or (str(raw.get("title") or "") or None),
        space_key=fetch.space_key or (str(raw.get("space_key") or "") or None),
        version=_raw_version(raw) if raw else None,
        source_url=str(raw.get("source_url") or "") or None,
        md_path=md_path,
        assets_dir=assets_dir_path(page_id) if page_id else None,
        labels=list(raw.get("labels") or []),
    )


def _batch_pages(fetches: Sequence[PageFetchResult]) -> list[BatchPage]:
    pages: list[BatchPage] = []
    seen: set[str] = set()
    for fetch in fetches:
        raw = fetch.raw or {}
        page_id = fetch.page_id or str(raw.get("page_id") or "")
        title = fetch.title or str(raw.get("title") or "")
        if not page_id or page_id in seen:
            continue
        seen.add(page_id)
        pages.append(
            BatchPage(
                page_id=page_id,
                title=title,
                space_key=fetch.space_key or str(raw.get("space_key") or ""),
            )
        )
    return pages


def _load_sidecar(output_dir: Path, page_id: str) -> dict[str, str]:
    path = output_dir / asset_sidecar_path(page_id)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return {str(k): str(v) for k, v in payload.items()}
    except Exception:
        return {}
    return {}


def _existing_md(output_dir: Path, page_id: str) -> str | None:
    folder = output_dir / "04_markdown"
    if not folder.is_dir():
        return None
    matches = sorted(folder.glob(f"{page_id}_*.md"))
    if not matches:
        return None
    return f"04_markdown/{matches[0].name}"


def _manifest_row(item: PageOutcome) -> dict[str, Any]:
    return {
        "id": item.page_id,
        "title": item.title,
        "space_key": item.space_key,
        "version": item.version,
        "source_url": item.source_url,
        "md_path": item.md_path,
        "assets_dir": item.assets_dir,
        "labels": item.labels,
        "status": item.status,
        "error": item.error,
    }


def _frontmatter(raw: Mapping[str, Any], unsupported: Sequence[str]) -> dict[str, Any]:
    ancestors = raw.get("ancestors") or []
    breadcrumbs = [str(item.get("title") or "") for item in ancestors if isinstance(item, dict)]
    return {
        "id": str(raw.get("page_id") or ""),
        "title": str(raw.get("title") or ""),
        "space_key": str(raw.get("space_key") or ""),
        "version": int(raw.get("version") or 0),
        "status": str(raw.get("status") or ""),
        "created_by": str(raw.get("created_by") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
        "source_url": str(raw.get("source_url") or ""),
        "labels": list(raw.get("labels") or []),
        "breadcrumbs": breadcrumbs,
        "attachments_count": len(raw.get("attachments") or []),
        "unsupported_macros": list(unsupported),
    }


def _raw_version(raw: Mapping[str, Any] | None) -> int | None:
    if not raw or raw.get("version") is None:
        return None
    try:
        return int(raw["version"])
    except (TypeError, ValueError):
        return None


def _summary_markdown(
    ok: int,
    failed: int,
    skipped: int,
    invalid_urls: Sequence[Mapping[str, str]],
    force_refresh: bool,
    errors: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Export summary",
        "",
        f"- ok: {ok}",
        f"- failed: {failed}",
        f"- skipped: {skipped}",
        f"- invalid_urls: {len(invalid_urls)}",
        f"- force_refresh: {force_refresh}",
        "",
        "## Invalid URLs",
    ]
    if not invalid_urls:
        lines.append("none")
    else:
        for item in invalid_urls:
            lines.append(f"- {item.get('url')}: {item.get('reason')}")
    lines.extend(["", "## Errors"])
    if not errors:
        lines.append("none")
    else:
        for item in errors:
            lines.append(f"- {item.get('page_id')}: {item.get('error')}")
    return "\n".join(lines) + "\n"


def _preview(markdown: str) -> str:
    if len(markdown) <= PREVIEW_LIMIT:
        return markdown
    return markdown[:PREVIEW_LIMIT] + "\n…"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry_ref(entry: AcceptedEntry) -> str:
    if entry.is_diff and entry.diff_versions:
        v1, v2 = entry.diff_versions
        return f"diff {entry.page_id} v{v1}->{v2}"
    if entry.page_id:
        return f"page {entry.page_id}"
    if entry.space_key and entry.title:
        return f"{entry.space_key}/{entry.title}"
    return entry.raw


def _fetch_extra(fetch: PageFetchResult) -> str:
    bits: list[str] = []
    if fetch.title:
        bits.append(f"«{fetch.title}»")
    if fetch.status == "ok" and fetch.raw and fetch.raw.get("version") is not None:
        bits.append(f"v{fetch.raw['version']}")
    if fetch.status != "ok" and fetch.error:
        bits.append(f"({fetch.error})")
    return (" " + " ".join(bits)) if bits else ""


def _outcome_extra(outcome: PageOutcome) -> str:
    bits: list[str] = []
    if outcome.title:
        bits.append(f"«{outcome.title}»")
    if outcome.status == "ok" and outcome.md_path:
        bits.append(outcome.md_path)
    if outcome.error:
        bits.append(f"({outcome.error})")
    return (" " + " ".join(bits)) if bits else ""


def _noop_publish(*, markdown: str, key: str | None = None, description: str | None = None) -> None:
    return None
