from __future__ import annotations

from pathlib import Path

import pytest

from confluence_md_exporter.settings import ConfigError
from confluence_md_exporter.url_resolver import InvalidUrl, infer_base_url, resolve_input_file

BASE = "https://confluence.example.com"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "urls.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_viewpage_action_page_id(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/pages/viewpage.action?pageId=101\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "101"
    assert result.invalid_urls == ()


def test_viewpage_action_with_extra_query(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/pages/viewpage.action?src=email&pageId=102\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "102"


def test_display_space_title(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/display/DEV/My+Page\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    entry = result.entries[0]
    assert entry.page_id is None
    assert entry.needs_title_lookup is True
    assert entry.space_key == "DEV"
    assert entry.title == "My Page"
    assert result.invalid_urls == ()


def test_wiki_spaces_page_id_title(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/wiki/spaces/DEV/pages/103/Some+Title\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "103"


def test_wiki_personal_space_page_id(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/wiki/spaces/~jdoe/pages/104/Home\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "104"
    assert result.entries[0].space_key == "~jdoe"


def test_bare_page_id(tmp_path: Path) -> None:
    path = _write(tmp_path, "105\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "105"


def test_relative_path_resolved_against_base(tmp_path: Path) -> None:
    path = _write(tmp_path, "/pages/viewpage.action?pageId=106\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "106"


def test_diff_page_url_with_selected_versions(tmp_path: Path) -> None:
    url = f"{BASE}/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42"
    path = _write(tmp_path, f"{url}\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    entry = result.entries[0]
    assert entry.page_id == "607636678"
    assert entry.is_diff is True
    assert entry.diff_versions == (41, 42)
    assert result.invalid_urls == ()


def test_diff_page_url_with_original_and_revised_version(tmp_path: Path) -> None:
    url = f"{BASE}/pages/diffpagesbyversion.action?pageId=607636678&originalVersion=41&revisedVersion=42"
    path = _write(tmp_path, f"{url}\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    entry = result.entries[0]
    assert entry.page_id == "607636678"
    assert entry.is_diff is True
    assert entry.diff_versions == (41, 42)


def test_diff_page_url_malformed_missing_version(tmp_path: Path) -> None:
    url = f"{BASE}/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41"
    path = _write(tmp_path, f"{url}\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 0
    assert result.invalid_urls == (InvalidUrl(url=url, reason="malformed"),)


def test_tiny_link_is_invalid_with_reason(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _write(tmp_path, f"{BASE}/x/AbCdEf\n")
    with caplog.at_level("WARNING"):
        result = resolve_input_file(path, BASE)
    assert result.pages_total == 0
    assert result.entries == ()
    assert result.invalid_urls == (InvalidUrl(url=f"{BASE}/x/AbCdEf", reason="tiny_link"),)
    assert "tiny_link" in caplog.text
    assert f"{BASE}/x/AbCdEf" in caplog.text


def test_tiny_link_is_not_resolved_to_page_id(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/x/AbCdEf\n/x/AbCdEf\n")
    result = resolve_input_file(path, BASE)
    assert all(item.reason == "tiny_link" for item in result.invalid_urls)
    assert result.entries == ()


def test_foreign_origin_is_origin_mismatch(tmp_path: Path) -> None:
    raw = "https://other.example.com/pages/viewpage.action?pageId=1"
    path = _write(tmp_path, raw + "\n")
    result = resolve_input_file(path, BASE)
    assert result.invalid_urls == (InvalidUrl(url=raw, reason="origin_mismatch"),)


def test_viewpage_without_page_id_is_malformed(tmp_path: Path) -> None:
    raw = f"{BASE}/pages/viewpage.action"
    path = _write(tmp_path, raw + "\n")
    result = resolve_input_file(path, BASE)
    assert result.invalid_urls == (InvalidUrl(url=raw, reason="malformed"),)


def test_garbage_line_is_unrecognized_form(tmp_path: Path) -> None:
    path = _write(tmp_path, "not-a-url\n")
    result = resolve_input_file(path, BASE)
    assert result.invalid_urls == (InvalidUrl(url="not-a-url", reason="unrecognized_form"),)


def test_duplicates_collapse_with_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = _write(
        tmp_path,
        "\n".join(
            [
                f"{BASE}/pages/viewpage.action?pageId=200",
                "200",
                f"{BASE}/wiki/spaces/DEV/pages/200/Title",
            ]
        )
        + "\n",
    )
    with caplog.at_level("WARNING"):
        result = resolve_input_file(path, BASE)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "200"
    assert "duplicate" in caplog.text.lower()


def test_empty_file_after_comments_pages_total_zero(tmp_path: Path) -> None:
    path = _write(tmp_path, "# just a comment\n\n  \n  # another\n")
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 0
    assert result.entries == ()
    assert result.invalid_urls == ()


def test_missing_file_is_impossible_start(tmp_path: Path) -> None:
    missing = tmp_path / "nope.txt"
    with pytest.raises(ConfigError, match="does not exist"):
        resolve_input_file(missing, BASE)


CONTEXT = "https://confluence.example.com/confluence"


def test_context_path_viewpage_is_accepted(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{CONTEXT}/pages/viewpage.action?pageId=201\n")
    result = resolve_input_file(path, CONTEXT)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "201"
    assert result.invalid_urls == ()


def test_origin_without_context_path_is_invalid(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/pages/viewpage.action?pageId=202\n")
    result = resolve_input_file(path, CONTEXT)
    assert result.pages_total == 0
    assert result.invalid_urls == (
        InvalidUrl(url=f"{BASE}/pages/viewpage.action?pageId=202", reason="unrecognized_form"),
    )


def test_context_path_relative_from_origin(tmp_path: Path) -> None:
    path = _write(tmp_path, "/confluence/pages/viewpage.action?pageId=203\n")
    result = resolve_input_file(path, CONTEXT)
    assert result.pages_total == 1
    assert result.entries[0].page_id == "203"


def test_root_relative_rejected_when_base_has_context(tmp_path: Path) -> None:
    path = _write(tmp_path, "/pages/viewpage.action?pageId=204\n")
    result = resolve_input_file(path, CONTEXT)
    assert result.pages_total == 0
    assert result.invalid_urls == (
        InvalidUrl(url="/pages/viewpage.action?pageId=204", reason="unrecognized_form"),
    )


def test_infer_base_url_from_viewpage(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/pages/viewpage.action?pageId=11\n")
    assert infer_base_url(path) == BASE


def test_infer_base_url_with_context_path(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/confluence/pages/viewpage.action?pageId=11\n")
    assert infer_base_url(path) == f"{BASE}/confluence"


def test_infer_base_url_from_wiki_form(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{BASE}/wiki/spaces/DEV/pages/11/Title\n")
    assert infer_base_url(path) == BASE


def test_infer_base_url_rejects_mixed_bases(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"{BASE}/pages/viewpage.action?pageId=11\n"
        f"{BASE}/confluence/pages/viewpage.action?pageId=12\n",
    )
    with pytest.raises(ConfigError, match="different Confluence bases"):
        infer_base_url(path)


def test_infer_base_url_fails_on_bare_ids_only(tmp_path: Path) -> None:
    path = _write(tmp_path, "123456\n")
    with pytest.raises(ConfigError, match="cannot infer CONFLUENCE_BASE_URL"):
        infer_base_url(path)
