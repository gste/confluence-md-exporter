from __future__ import annotations

from pathlib import Path

import pytest

from confluence_md_exporter.settings import ConfigError
from confluence_md_exporter.url_resolver import resolve_input_file

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


def test_tiny_link_and_foreign_origin_are_invalid(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "\n".join(
            [
                f"{BASE}/x/AbCdEf",
                "/x/AbCdEf",
                "https://other.example.com/pages/viewpage.action?pageId=1",
                "not-a-url",
            ]
        )
        + "\n",
    )
    result = resolve_input_file(path, BASE)
    assert result.pages_total == 0
    assert result.entries == ()
    assert len(result.invalid_urls) == 4


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
