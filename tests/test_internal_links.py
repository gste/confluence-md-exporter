from __future__ import annotations

from confluence_md_exporter.layout import slugify
from confluence_md_exporter.transform import BatchPage, TransformContext, transform_storage

BASE = "https://confluence.example.com"


def _ctx(pages: list[BatchPage]) -> TransformContext:
    return TransformContext(
        page_id="42",
        batch_pages=tuple(pages),
        base_url=BASE,
    )


def test_in_batch_page_becomes_relative_markdown() -> None:
    target = BatchPage(page_id="99", title="Other Page", space_key="DEV")
    result = transform_storage(
        """
<p><ac:link>
  <ri:page ri:content-title="Other Page" ri:space-key="DEV"/>
  <ac:plain-text-link-body>Other</ac:plain-text-link-body>
</ac:link></p>
""",
        context=_ctx([target]),
    )
    href = f"{target.page_id}_{slugify(target.title)}.md"
    assert href == "99_other-page.md"
    assert f"[Other]({href})" in result.markdown
    assert "http" not in result.markdown


def test_out_of_batch_page_with_id_uses_viewpage_url() -> None:
    result = transform_storage(
        """
<p><ac:link>
  <ri:page ri:content-title="Outside" ri:content-id="55"/>
</ac:link></p>
""",
        context=_ctx([]),
    )
    assert (
        "[Outside](https://confluence.example.com/pages/viewpage.action?pageId=55)"
        in result.markdown
    )


def test_out_of_batch_page_without_id_uses_display_url() -> None:
    result = transform_storage(
        """
<p><ac:link>
  <ri:page ri:content-title="Out Page" ri:space-key="DEV"/>
</ac:link></p>
""",
        context=_ctx([]),
    )
    assert "[Out Page](https://confluence.example.com/display/DEV/Out%20Page)" in result.markdown


def test_anchor_is_preserved_in_and_out_of_batch() -> None:
    target = BatchPage(page_id="99", title="Other Page", space_key="DEV")
    in_batch = transform_storage(
        """
<p><ac:link ac:anchor="sec">
  <ri:page ri:content-title="Other Page" ri:space-key="DEV"/>
</ac:link></p>
""",
        context=_ctx([target]),
    )
    assert "[Other Page](99_other-page.md#sec)" in in_batch.markdown

    out = transform_storage(
        """
<p><ac:link ac:anchor="sec">
  <ri:page ri:content-title="Outside" ri:content-id="55"/>
</ac:link></p>
""",
        context=_ctx([]),
    )
    assert "pageId=55#sec" in out.markdown
