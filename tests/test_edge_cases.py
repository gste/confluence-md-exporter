from __future__ import annotations

from pathlib import Path

from confluence_md_exporter.layout import slugify
from confluence_md_exporter.output import write_gold_markdown
from confluence_md_exporter.transform import transform_storage

_FRONTMATTER = {
    "id": "42",
    "title": "Empty",
    "space_key": "DEV",
    "version": 1,
    "status": "current",
    "created_by": "jdoe",
    "updated_at": "2026-01-01T00:00:00Z",
    "source_url": "https://confluence.example.com/pages/viewpage.action?pageId=42",
    "labels": [],
    "breadcrumbs": ["Root"],
    "attachments_count": 0,
    "unsupported_macros": [],
}


def test_empty_body_is_ok_with_frontmatter_only(tmp_path: Path) -> None:
    result = transform_storage("")
    assert not result.failed
    assert result.markdown == ""
    path = write_gold_markdown(tmp_path, "42", _FRONTMATTER, result.markdown)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, _, body = text.split("---", 2)
    assert body.strip() == ""


def test_macro_without_body_writes_wrapper_only() -> None:
    note = transform_storage('<ac:structured-macro ac:name="info"/>')
    assert not note.failed
    assert note.markdown == "> [!NOTE]\n"
    expand = transform_storage('<ac:structured-macro ac:name="expand"/>')
    assert "<summary>Details</summary>" in expand.markdown
    assert expand.markdown.count("<p>") == 0
    code = transform_storage('<ac:structured-macro ac:name="code"/>')
    assert code.markdown.startswith("```text\n")
    assert code.markdown.endswith("```\n")


def test_triple_backticks_inside_code_lengthen_fence() -> None:
    result = transform_storage(
        """
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">text</ac:parameter>
  <ac:plain-text-body><![CDATA[```
inside
````]]></ac:plain-text-body>
</ac:structured-macro>
"""
    )
    assert not result.failed
    assert result.markdown.startswith("`````text\n")
    assert result.markdown.endswith("`````\n")


def test_colspan_rowspan_become_rectangular_gfm() -> None:
    result = transform_storage(
        """
<table>
  <tr><th>A</th><th>B</th><th>C</th></tr>
  <tr><td colspan="2">xy</td><td>z</td></tr>
  <tr><td>1</td><td rowspan="2">2</td></tr>
</table>
"""
    )
    assert not result.failed
    rows = [line for line in result.markdown.splitlines() if line.startswith("|")]
    assert rows[0] == "| A | B | C |"
    assert rows[1] == "| --- | --- | --- |"
    assert rows[2] == "| xy | z |  |"
    assert rows[3] == "| 1 | 2 |  |"
    widths = [line.count("|") - 1 for line in rows]
    assert len(set(widths)) == 1
    assert "colspan" not in result.markdown
    assert "rowspan" not in result.markdown


def test_html_entities_decoded_for_slug_frontmatter_and_breadcrumbs(tmp_path: Path) -> None:
    title = "Hello &amp; World"
    assert slugify(title) == "hello-world"
    path = write_gold_markdown(
        tmp_path,
        "42",
        {
            **_FRONTMATTER,
            "title": title,
            "breadcrumbs": ["Root &amp; Co", "Hello &amp; World"],
        },
        "",
    )
    assert path.name == "42_hello-world.md"
    text = path.read_text(encoding="utf-8")
    assert "Hello &amp; World" not in text
    assert "Root &amp; Co" not in text
    assert "Hello & World" in text
    assert "Root & Co" in text
