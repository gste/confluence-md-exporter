"""Skip unchanged pages using local raw version and on-disk asset sizes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from confluence_md_exporter.assets import sync_page_assets
from confluence_md_exporter.client import ConfluenceClient, PageFetchResult
from confluence_md_exporter.layout import (
    asset_file_path,
    asset_sidecar_path,
    raw_json_path,
    unique_safe_filenames,
)
from confluence_md_exporter.output import write_bronze
from confluence_md_exporter.url_resolver import AcceptedEntry


def load_local_raw(output_dir: Path, page_id: str) -> dict[str, Any] | None:
    path = output_dir / raw_json_path(page_id)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def assets_match_local(output_dir: Path, page_id: str, raw: Mapping[str, Any]) -> bool:
    sidecar = _load_sidecar(output_dir, page_id)
    attachments = raw.get("attachments") or []
    originals = [str(item.get("title") or "") for item in attachments]
    derived = unique_safe_filenames(originals)
    for item in attachments:
        original = str(item.get("title") or "")
        safe = sidecar.get(original) or derived.get(original)
        if not safe:
            return False
        path = output_dir / asset_file_path(page_id, safe)
        if not path.is_file():
            return False
        expected = int(item.get("file_size") or 0)
        if path.stat().st_size != expected:
            return False
    return True


def should_skip_page(
    output_dir: Path,
    page_id: str,
    remote_version: int,
    *,
    force_refresh: bool,
) -> bool:
    if force_refresh:
        return False
    raw = load_local_raw(output_dir, page_id)
    if raw is None:
        return False
    if int(raw.get("version") or -1) != remote_version:
        return False
    return assets_match_local(output_dir, page_id, raw)


def sync_page(
    client: ConfluenceClient,
    output_dir: Path,
    page_id: str,
    *,
    force_refresh: bool,
) -> PageFetchResult:
    if not force_refresh:
        raw = load_local_raw(output_dir, page_id)
        if raw is not None:
            remote_version = client.fetch_version(page_id)
            if remote_version is not None and should_skip_page(
                output_dir, page_id, remote_version, force_refresh=False
            ):
                return PageFetchResult(
                    status="skipped",
                    error="disk_skip",
                    page_id=page_id,
                    space_key=str(raw.get("space_key") or "") or None,
                    title=str(raw.get("title") or "") or None,
                    raw=raw,
                )
    result = client.fetch_entry(AcceptedEntry(page_id, page_id, None, None, False))
    if result.status == "ok" and result.raw is not None:
        write_bronze(output_dir, result.raw)
        sync_page_assets(client, output_dir, page_id, result.raw.get("attachments") or [])
    return result


def _load_sidecar(output_dir: Path, page_id: str) -> dict[str, str]:
    path = output_dir / asset_sidecar_path(page_id)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}
