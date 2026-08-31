from __future__ import annotations

import re

from confluence_md_exporter.layout import slugify


def test_transliteration_table_sample() -> None:
    assert slugify("Привет") == "privet"
    assert slugify("ёлка") == "yolka"
    assert slugify("щука") == "shhuka"
    assert slugify("царь") == "czar"
    assert slugify("объект") == "obekt"
    assert slugify("яйцо") == "yajczo"
    assert slugify("Європа") == "yevropa"
    assert slugify("їжак") == "yizhak"


def test_truncation_to_60_and_no_trailing_hyphen() -> None:
    title = "a" * 80
    slug = slugify(title)
    assert len(slug) == 60
    assert slug == "a" * 60
    hyphenated = slugify("word " + ("b" * 70))
    assert len(hyphenated) <= 60
    assert not hyphenated.endswith("-")


def test_empty_slug_becomes_page() -> None:
    assert slugify("") == "page"
    assert slugify("!!!") == "page"
    assert slugify("&nbsp;") == "page"
    assert slugify("ъь") == "page"


def test_no_cyrillic_in_result() -> None:
    slug = slugify("Страница Ёлка — объект №1")
    assert re.search(r"[а-яёіїєґў]", slug, re.IGNORECASE) is None
    assert slug == "stranicza-yolka-obekt-no1"


def test_html_entities_decoded_before_slug() -> None:
    assert slugify("Foo &amp; Bar") == "foo-bar"
    assert slugify("A&nbsp;B") == "a-b"
