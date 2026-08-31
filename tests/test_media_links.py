from __future__ import annotations

import re
from pathlib import Path

from confluence_md_exporter.assets import missing_attachment_placeholder
from confluence_md_exporter.transform import TransformContext, transform_storage

PAGE_ID = "42"
ASSET_HREF = re.compile(r"\[[^\]]*\]\((../03_assets/[^)]+)\)")


def _ctx(**overrides: object) -> TransformContext:
    values: dict[str, object] = {
        "page_id": PAGE_ID,
        "original_to_safe": {"diagram.png": "diagram.png"},
        "attachments": [{"title": "diagram.png"}],
        "batch_pages": (),
        "base_url": "https://confluence.example.com",
    }
    values.update(overrides)
    return TransformContext(**values)  # type: ignore[arg-type]


def _write_asset(root: Path, name: str, data: bytes = b"png") -> Path:
    path = root / "03_assets" / PAGE_ID / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _assert_canonical_assets_exist(root: Path, markdown: str) -> None:
    md_dir = root / "04_markdown"
    md_dir.mkdir(parents=True, exist_ok=True)
    (md_dir / f"{PAGE_ID}_page.md").write_text(markdown, encoding="utf-8")
    hrefs = ASSET_HREF.findall(markdown)
    assert hrefs
    for href in hrefs:
        assert href.startswith("../03_assets/")
        assert not href.startswith("../assets/")
        target = (md_dir / href).resolve()
        assert target.is_file(), href


def test_attachment_image_canonical_path_resolves(tmp_path: Path) -> None:
    _write_asset(tmp_path, "diagram.png")
    result = transform_storage(
        '<p><ac:image ac:alt="diagram"><ri:attachment ri:filename="diagram.png"/></ac:image></p>',
        context=_ctx(),
    )
    assert result.error is None
    assert "![diagram](../03_assets/42/diagram.png)" in result.markdown
    _assert_canonical_assets_exist(tmp_path, result.markdown)


def test_external_image_url_is_not_rewritten() -> None:
    remote = "https://cdn.example.com/pic.png"
    result = transform_storage(
        f'<p><ac:image ac:alt="remote"><ri:url ri:value="{remote}"/></ac:image></p>',
        context=_ctx(),
    )
    assert f"![remote]({remote})" in result.markdown
    assert "../03_assets/" not in result.markdown


def test_attachment_file_link_resolves(tmp_path: Path) -> None:
    _write_asset(tmp_path, "spec.pdf", b"%PDF")
    result = transform_storage(
        """
<p><ac:link>
  <ri:attachment ri:filename="spec.pdf"/>
  <ac:plain-text-link-body>spec</ac:plain-text-link-body>
</ac:link></p>
""",
        context=_ctx(original_to_safe={"spec.pdf": "spec.pdf"}, attachments=[{"title": "spec.pdf"}]),
    )
    assert "[spec](../03_assets/42/spec.pdf)" in result.markdown
    _assert_canonical_assets_exist(tmp_path, result.markdown)


def test_drawio_preview_and_source_links(tmp_path: Path) -> None:
    _write_asset(tmp_path, "flow.png")
    _write_asset(tmp_path, "flow.drawio", b"<mxfile/>")
    result = transform_storage(
        """
<ac:structured-macro ac:name="drawio">
  <ac:parameter ac:name="diagramName">flow</ac:parameter>
</ac:structured-macro>
""",
        context=_ctx(
            original_to_safe={"flow.png": "flow.png", "flow.drawio": "flow.drawio"},
            attachments=[{"title": "flow.png"}, {"title": "flow.drawio"}],
        ),
    )
    assert "![flow](../03_assets/42/flow.png)" in result.markdown
    assert "[source](../03_assets/42/flow.drawio)" in result.markdown
    _assert_canonical_assets_exist(tmp_path, result.markdown)


def test_drawio_alias_draw_dot_io(tmp_path: Path) -> None:
    _write_asset(tmp_path, "flow.svg", b"<svg/>")
    _write_asset(tmp_path, "flow.xml", b"<xml/>")
    result = transform_storage(
        """
<ac:structured-macro ac:name="draw.io">
  <ac:parameter ac:name="diagramName">flow</ac:parameter>
</ac:structured-macro>
""",
        context=_ctx(
            original_to_safe={"flow.svg": "flow.svg", "flow.xml": "flow.xml"},
            attachments=[{"title": "flow.svg"}, {"title": "flow.xml"}],
        ),
    )
    assert "![flow](../03_assets/42/flow.svg)" in result.markdown
    assert "[source](../03_assets/42/flow.xml)" in result.markdown
    _assert_canonical_assets_exist(tmp_path, result.markdown)


def test_missing_attachment_is_placeholder_not_asset_path() -> None:
    result = transform_storage(
        '<p><ac:image><ri:attachment ri:filename="gone.png"/></ac:image></p>',
        context=_ctx(original_to_safe={}, attachments=[]),
    )
    assert result.markdown.strip() == missing_attachment_placeholder("gone.png")
    assert "../03_assets/" not in result.markdown
    assert "gone.png" in result.markdown
