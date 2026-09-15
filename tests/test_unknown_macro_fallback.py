from __future__ import annotations

from confluence_md_exporter.transform import transform_storage


def test_unknown_macro_comment_text_and_frontmatter_list() -> None:
    result = transform_storage(
        """
<ac:structured-macro ac:name="jira">
  <ac:parameter ac:name="key">ABC-1</ac:parameter>
  <ac:rich-text-body><p>See ticket</p></ac:rich-text-body>
</ac:structured-macro>
"""
    )
    assert not result.failed
    assert result.error is None
    assert "<!-- unsupported-macro: jira -->" in result.markdown
    assert "See ticket" in result.markdown
    assert "ABC-1" not in result.markdown
    assert result.unsupported_macros == ["jira"]


def test_unknown_macros_deduped_in_first_seen_order() -> None:
    result = transform_storage(
        """
<ac:structured-macro ac:name="jira">
  <ac:rich-text-body><p>one</p></ac:rich-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="toc">
  <ac:rich-text-body><p>two</p></ac:rich-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="jira">
  <ac:rich-text-body><p>three</p></ac:rich-text-body>
</ac:structured-macro>
"""
    )
    assert not result.failed
    assert result.unsupported_macros == ["jira", "toc"]
    assert result.markdown.count("<!-- unsupported-macro: jira -->") == 2
    assert "<!-- unsupported-macro: toc -->" in result.markdown


def test_unknown_macro_equivalent_ac_macro_tag() -> None:
    result = transform_storage(
        """
<ac:macro ac:name="gallery">
  <ac:rich-text-body><p>photos</p></ac:rich-text-body>
</ac:macro>
"""
    )
    assert not result.failed
    assert "<!-- unsupported-macro: gallery -->" in result.markdown
    assert "photos" in result.markdown
    assert result.unsupported_macros == ["gallery"]
