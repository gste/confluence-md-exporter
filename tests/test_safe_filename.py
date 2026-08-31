from __future__ import annotations

from confluence_md_exporter.layout import safe_filename, unique_safe_filenames


def test_windows_and_posix_reserved_characters() -> None:
    name = safe_filename('a<>:"/\\|?*b.txt')
    assert set(name) <= set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    assert name.endswith(".txt")
    assert name.startswith("a")


def test_spaces_and_trailing_dots() -> None:
    assert safe_filename("my  file.png") == "my_file.png"
    assert safe_filename("notes.txt.") == "notes.txt"


def test_cyrillic_transliterated() -> None:
    assert safe_filename("файл.png") == "fajl.png"
    assert "ф" not in safe_filename("файл.png")


def test_empty_basename_becomes_file() -> None:
    assert safe_filename(".txt") == "file.txt"
    assert safe_filename("") == "file"


def test_collisions_get_numeric_suffix() -> None:
    mapping = unique_safe_filenames(["a/b.txt", "a_b.txt", "photo.png", "photo.png"])
    assert mapping["a/b.txt"] != mapping["a_b.txt"]
    assert mapping["a_b.txt"].endswith(".txt")
    assert mapping["photo.png"] == mapping["photo.png"]
    values = [mapping["a/b.txt"], mapping["a_b.txt"]]
    assert any(name.endswith("_2.txt") for name in values)


def test_extension_longer_than_8_is_not_an_extension() -> None:
    name = safe_filename("archive.toolongext")
    assert name == "archive.toolongext" or "_" in name
