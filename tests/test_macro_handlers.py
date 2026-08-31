from __future__ import annotations

import pytest

from confluence_md_exporter.transform import transform_storage


def test_ordinary_html_to_gfm() -> None:
    result = transform_storage(
        """
<h1>Title</h1>
<p>Hello <strong>bold</strong> and <em>em</em> and <code>x</code>.</p>
<ul><li>one</li><li>two</li></ul>
<ol><li>first</li></ol>
<table>
  <thead><tr><th>A</th><th>B</th></tr></thead>
  <tbody><tr><td>1</td><td>2</td></tr></tbody>
</table>
<pre><code>line</code></pre>
<p>see <a href="https://example.com">ex</a></p>
<hr/>
<p>line<br/>break</p>
"""
    )
    assert result.error is None
    md = result.markdown
    assert md.startswith("# Title\n")
    assert "**bold**" in md
    assert "*em*" in md
    assert "`x`" in md
    assert "- one" in md
    assert "1. first" in md
    assert "| A | B |" in md
    assert "| --- | --- |" in md
    assert "| 1 | 2 |" in md
    assert "```text\nline\n```" in md
    assert "[ex](https://example.com)" in md
    assert "---" in md
    assert "line  \nbreak" in md


def test_code_macro_fenced_language() -> None:
    result = transform_storage(
        """
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">python</ac:parameter>
  <ac:plain-text-body><![CDATA[print(1)]]></ac:plain-text-body>
</ac:structured-macro>
"""
    )
    assert result.error is None
    assert result.markdown == "```python\nprint(1)\n```\n"


def test_code_macro_default_language_text() -> None:
    result = transform_storage(
        """
<ac:structured-macro ac:name="code">
  <ac:plain-text-body><![CDATA[plain]]></ac:plain-text-body>
</ac:structured-macro>
"""
    )
    assert result.markdown == "```text\nplain\n```\n"


def test_code_macro_lengthens_fence() -> None:
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
    assert result.error is None
    assert result.markdown.startswith("`````text\n")
    assert result.markdown.endswith("`````\n")
    assert "```\ninside\n````" in result.markdown


@pytest.mark.parametrize("name", ["plantuml", "plantumlcloud"])
def test_plantuml_is_fenced_without_raster(name: str) -> None:
    result = transform_storage(
        f"""
<ac:structured-macro ac:name="{name}">
  <ac:plain-text-body><![CDATA[@startuml
A -> B
@enduml]]></ac:plain-text-body>
</ac:structured-macro>
"""
    )
    assert result.error is None
    md = result.markdown
    assert md.startswith("```plantuml\n")
    assert "@startuml" in md
    assert "A -> B" in md
    assert "@enduml" in md
    assert "![" not in md
    assert "<img" not in md.lower()
    assert ".png" not in md
    assert ".svg" not in md


@pytest.mark.parametrize(
    ("macro", "kind"),
    [
        ("info", "NOTE"),
        ("note", "NOTE"),
        ("panel", "NOTE"),
        ("warning", "WARNING"),
        ("error", "WARNING"),
        ("tip", "TIP"),
        ("success", "TIP"),
    ],
)
def test_callouts(macro: str, kind: str) -> None:
    result = transform_storage(
        f"""
<ac:structured-macro ac:name="{macro}">
  <ac:rich-text-body><p>Watch this</p></ac:rich-text-body>
</ac:structured-macro>
"""
    )
    assert result.error is None
    assert result.markdown == f"> [!{kind}]\n> Watch this\n"


def test_expand_uses_title_or_details() -> None:
    titled = transform_storage(
        """
<ac:structured-macro ac:name="expand">
  <ac:parameter ac:name="title">More</ac:parameter>
  <ac:rich-text-body><p>hidden</p></ac:rich-text-body>
</ac:structured-macro>
"""
    )
    assert titled.markdown == (
        "<details>\n<summary>More</summary>\n\nhidden\n</details>\n"
    )
    untitled = transform_storage(
        """
<ac:structured-macro ac:name="expand">
  <ac:rich-text-body><p>hidden</p></ac:rich-text-body>
</ac:structured-macro>
"""
    )
    assert "<summary>Details</summary>" in untitled.markdown


def test_status_uses_text_and_ignores_colour() -> None:
    result = transform_storage(
        """
<p>State <ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">Red</ac:parameter>
  <ac:parameter ac:name="title">Blocked</ac:parameter>
</ac:structured-macro> now</p>
"""
    )
    assert result.error is None
    assert "`Blocked`" in result.markdown
    assert "Red" not in result.markdown
    assert "colour" not in result.markdown


def test_task_list() -> None:
    result = transform_storage(
        """
<ac:task-list>
  <ac:task>
    <ac:task-id>1</ac:task-id>
    <ac:task-status>complete</ac:task-status>
    <ac:task-body>Done item</ac:task-body>
  </ac:task>
  <ac:task>
    <ac:task-status>incomplete</ac:task-status>
    <ac:task-body>Todo item</ac:task-body>
  </ac:task>
</ac:task-list>
"""
    )
    assert result.markdown == "- [x] Done item\n- [ ] Todo item\n"


def test_emoticon() -> None:
    named = transform_storage('<p>hi <ac:emoticon ac:name="smile"/></p>')
    assert named.markdown.strip() == "hi :smile:"
    short = transform_storage('<p><ac:emoticon ac:emoji-shortname="grin"/></p>')
    assert short.markdown.strip() == ":grin:"
    missing = transform_storage("<p><ac:emoticon/></p>")
    assert missing.markdown.strip() == "emoticon"


def test_user_mention() -> None:
    named = transform_storage(
        """
<p><ac:link><ri:user ri:display-name="Ada Lovelace" ri:account-id="99"/></ac:link></p>
"""
    )
    assert named.markdown.strip() == "@Ada Lovelace"
    by_id = transform_storage(
        """
<p><ac:link><ri:user ri:account-id="99"/></ac:link></p>
"""
    )
    assert by_id.markdown.strip() == "@99"


def test_time_iso_date() -> None:
    result = transform_storage('<p>on <time datetime="2026-08-31T12:00:00Z">31 Aug</time></p>')
    assert result.markdown.strip() == "on 2026-08-31"


def test_broken_xml_fails_page() -> None:
    result = transform_storage("<p>unclosed")
    assert result.failed
    assert result.error == "invalid_xml"
    assert result.markdown == ""
