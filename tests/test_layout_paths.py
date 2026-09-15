from __future__ import annotations

from confluence_md_exporter.layout import (
    asset_relative_path,
    gold_markdown_path,
    raw_json_path,
    slugify,
)


def test_canonical_asset_relative_path() -> None:
    path = asset_relative_path("42", "diagram.png")
    assert path == "../03_assets/42/diagram.png"
    assert not path.startswith("../assets/")
    assert "\\" not in path


def test_gold_markdown_filename() -> None:
    slug = slugify("Hello World")
    path = gold_markdown_path("99", slug)
    assert path == "04_markdown/99_hello-world.md"


def test_raw_json_uses_string_page_id() -> None:
    assert raw_json_path("100") == "01_raw/100.json"
