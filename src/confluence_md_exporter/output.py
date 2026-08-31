"""Serialize bronze, sidecar, interim, gold Markdown, manifest, and run report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from confluence_md_exporter.layout import (
    asset_sidecar_path,
    gold_markdown_path,
    interim_html_path,
    manifest_path,
    raw_json_path,
    run_report_path,
    slugify,
)

PAGE_STATUSES = frozenset({"ok", "failed", "skipped"})
EDITION = "datacenter"

BRONZE_KEYS = (
    "page_id",
    "edition",
    "title",
    "space_key",
    "version",
    "status",
    "created_by",
    "updated_at",
    "source_url",
    "labels",
    "ancestors",
    "body_storage",
    "attachments",
    "fetched_at",
)

FRONTMATTER_KEYS = (
    "id",
    "title",
    "space_key",
    "version",
    "status",
    "created_by",
    "updated_at",
    "source_url",
    "labels",
    "breadcrumbs",
    "attachments_count",
    "unsupported_macros",
)

MANIFEST_KEYS = (
    "id",
    "title",
    "space_key",
    "version",
    "source_url",
    "md_path",
    "assets_dir",
    "labels",
    "status",
    "error",
)

RUN_REPORT_KEYS = (
    "started_at",
    "finished_at",
    "pages_total",
    "ok",
    "failed",
    "skipped",
    "invalid_urls",
    "force_refresh",
    "errors",
)

_FORBIDDEN_BODY = frozenset({"view", "export_view", "atlas_doc_format", "body_view"})


def build_source_url(base_url: str, page_id: str, webui: str | None) -> str:
    if not webui:
        return f"{base_url}/pages/viewpage.action?pageId={page_id}"
    if webui.startswith("http://") or webui.startswith("https://"):
        return webui
    prefix = "" if webui.startswith("/") else "/"
    return f"{base_url}{prefix}{webui}"


def write_bronze(output_dir: Path, raw: Mapping[str, Any]) -> Path:
    payload = _without_forbidden_bodies(dict(raw))
    _require_keys(payload, BRONZE_KEYS)
    page_id = payload["page_id"]
    if not isinstance(page_id, str):
        raise ValueError("page_id must be a string")
    if payload.get("edition") != EDITION:
        raise ValueError("edition must be 'datacenter'")
    path = output_dir / raw_json_path(page_id)
    _write_json(path, payload)
    return path


def write_asset_sidecar(
    output_dir: Path, page_id: str, original_to_safe: Mapping[str, str]
) -> Path | None:
    if not original_to_safe:
        return None
    path = output_dir / asset_sidecar_path(page_id)
    _write_json(path, dict(original_to_safe))
    return path


def write_interim(output_dir: Path, page_id: str, html: str) -> Path:
    path = output_dir / interim_html_path(page_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def write_gold_markdown(
    output_dir: Path,
    page_id: str,
    frontmatter: Mapping[str, Any],
    body: str,
) -> Path:
    data = dict(frontmatter)
    _require_keys(data, FRONTMATTER_KEYS)
    if data["id"] != page_id:
        raise ValueError("frontmatter id must match page_id")
    slug = slugify(str(data["title"]))
    path = output_dir / gold_markdown_path(page_id, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump_frontmatter(data) + body, encoding="utf-8")
    return path


def write_manifest(output_dir: Path, records: Sequence[Mapping[str, Any]]) -> Path:
    payload: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        _require_keys(item, MANIFEST_KEYS)
        if item["status"] not in PAGE_STATUSES:
            raise ValueError(f"invalid page status: {item['status']!r}")
        if item["id"] is not None and not isinstance(item["id"], str):
            raise ValueError("manifest id must be a string or null")
        payload.append(item)
    path = output_dir / manifest_path()
    _write_json(path, payload)
    return path


def write_run_report(output_dir: Path, report: Mapping[str, Any]) -> Path:
    payload = dict(report)
    _require_keys(payload, RUN_REPORT_KEYS)
    path = output_dir / run_report_path()
    _write_json(path, payload)
    return path


def _require_keys(data: Mapping[str, Any], keys: Sequence[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise ValueError(f"missing keys: {missing}")


def _without_forbidden_bodies(raw: dict[str, Any]) -> dict[str, Any]:
    out = {key: value for key, value in raw.items() if key not in _FORBIDDEN_BODY}
    body = out.get("body")
    if isinstance(body, dict):
        out["body"] = {key: value for key, value in body.items() if key not in _FORBIDDEN_BODY}
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dump_frontmatter(data: Mapping[str, Any]) -> str:
    lines = ["---"]
    for key in FRONTMATTER_KEYS:
        lines.extend(_yaml_lines(key, data[key]))
    lines.append("---")
    return "\n".join(lines) + "\n"


def _yaml_lines(key: str, value: Any) -> list[str]:
    if isinstance(value, list):
        if not value:
            return [f"{key}: []"]
        lines = [f"{key}:"]
        lines.extend(f"  - {_yaml_scalar(item)}" for item in value)
        return lines
    return [f"{key}: {_yaml_scalar(value)}"]


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)
