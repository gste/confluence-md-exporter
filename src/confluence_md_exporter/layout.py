"""Deterministic slug, safe attachment names, and export layout paths."""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Sequence

CYRILLIC_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "j",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "cz",
    "ч": "ch",
    "ш": "sh",
    "щ": "shh",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "є": "ye",
    "і": "i",
    "ї": "yi",
    "ґ": "g",
    "ў": "u",
}

_WIN_RESERVED = set('<>:"/\\|?*')
_SAFE_NAME_CHARS = re.compile(r"[A-Za-z0-9._-]")
_EXT = re.compile(r"^[A-Za-z0-9]{1,8}$")
_SLUG_KEEP = re.compile(r"[^a-z0-9-]+")


def slugify(title: str) -> str:
    text = html.unescape(title)
    text = unicodedata.normalize("NFKC", text).lower()
    text = _transliterate_cyrillic(text, drop_unknown=True)
    text = _SLUG_KEEP.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    text = text[:60].rstrip("-")
    return text or "page"


def safe_filename(original: str) -> str:
    text = unicodedata.normalize("NFKC", original)
    text = "".join(_replace_reserved(ch) for ch in text)
    text = re.sub(r" +", "_", text)
    text = text.rstrip(" .")
    stem, ext = _split_extension(text)
    stem = _transliterate_cyrillic(stem, drop_unknown=False)
    stem = "".join(ch if _SAFE_NAME_CHARS.fullmatch(ch) else "_" for ch in stem)
    if not stem:
        stem = "file"
    if ext:
        return f"{stem}.{ext}"
    return stem


def unique_safe_filenames(originals: Sequence[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used_lower: set[str] = set()
    for original in originals:
        if original in mapping:
            continue
        base = safe_filename(original)
        candidate = base
        n = 2
        while candidate.lower() in used_lower:
            candidate = _with_numeric_suffix(base, n)
            n += 1
        mapping[original] = candidate
        used_lower.add(candidate.lower())
    return mapping


def raw_json_path(page_id: str) -> str:
    return f"01_raw/{page_id}.json"


def asset_sidecar_path(page_id: str) -> str:
    return f"01_raw/{page_id}.assets.json"


def interim_html_path(page_id: str) -> str:
    return f"02_interim/{page_id}.html"


def asset_file_path(page_id: str, filename: str) -> str:
    return f"03_assets/{page_id}/{filename}"


def assets_dir_path(page_id: str) -> str:
    return f"03_assets/{page_id}"


def gold_markdown_path(page_id: str, slug: str) -> str:
    return f"04_markdown/{page_id}_{slug}.md"


def manifest_path() -> str:
    return "04_markdown/manifest.json"


def run_report_path() -> str:
    return "run_report.json"


def asset_relative_path(page_id: str, filename: str) -> str:
    return f"../03_assets/{page_id}/{filename}"


def _transliterate_cyrillic(text: str, *, drop_unknown: bool) -> str:
    out: list[str] = []
    for ch in text:
        if ch in CYRILLIC_MAP:
            out.append(CYRILLIC_MAP[ch])
            continue
        if drop_unknown and _is_cyrillic(ch):
            continue
        out.append(ch)
    return "".join(out)


def _is_cyrillic(ch: str) -> bool:
    try:
        return "CYRILLIC" in unicodedata.name(ch)
    except ValueError:
        return False


def _replace_reserved(ch: str) -> str:
    if ch in _WIN_RESERVED or unicodedata.category(ch) == "Cc":
        return "_"
    return ch


def _split_extension(name: str) -> tuple[str, str]:
    if "." not in name:
        return name, ""
    stem, ext = name.rsplit(".", 1)
    if _EXT.fullmatch(ext):
        return stem, ext
    return name, ""


def _with_numeric_suffix(name: str, n: int) -> str:
    stem, ext = _split_extension(name)
    tagged = f"{stem}_{n}"
    if ext:
        return f"{tagged}.{ext}"
    return tagged
