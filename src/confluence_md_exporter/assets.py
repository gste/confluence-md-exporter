"""Download page attachments over REST and write them under 03_assets."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from confluence_md_exporter.client import ConfluenceClient
from confluence_md_exporter.layout import asset_file_path, unique_safe_filenames
from confluence_md_exporter.output import write_asset_sidecar

logger = logging.getLogger(__name__)


def missing_attachment_placeholder(original: str) -> str:
    return f"[missing-attachment: {original}]"


@dataclass
class AssetSyncResult:
    original_to_safe: dict[str, str]
    missing_placeholders: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sidecar_path: Path | None = None

    @property
    def page_failed(self) -> bool:
        return False


def sync_page_assets(
    client: ConfluenceClient,
    output_dir: Path,
    page_id: str,
    attachments: Sequence[Mapping[str, Any]],
) -> AssetSyncResult:
    originals = [str(item.get("title") or "") for item in attachments]
    names = unique_safe_filenames(originals)
    downloaded: dict[str, str] = {}
    missing: list[str] = []
    warnings: list[str] = []

    for item in attachments:
        original = str(item.get("title") or "")
        safe = names[original]
        url = client.attachment_download_url(item)
        if "/download/attachments/" in url:
            raise RuntimeError("UI attachment path must not be used as the primary download")
        response = client.download(url)
        if response.status >= 400:
            placeholder = missing_attachment_placeholder(original)
            warning = f"attachment not downloaded: {original}"
            missing.append(placeholder)
            warnings.append(warning)
            logger.warning(warning)
            continue
        path = output_dir / asset_file_path(page_id, safe)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.body)
        downloaded[original] = safe

    sidecar = write_asset_sidecar(output_dir, page_id, downloaded)
    return AssetSyncResult(
        original_to_safe=downloaded,
        missing_placeholders=missing,
        warnings=warnings,
        sidecar_path=sidecar,
    )
