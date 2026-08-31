"""Convert Confluence Storage Format XML to GFM for known constructs."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import escape as html_escape
from xml.etree.ElementTree import Element

AC = "http://www.atlassian.com/schema/confluence/4/ac/"
RI = "http://www.atlassian.com/schema/confluence/4/ri/"

CALLOUT_TYPE = {
    "info": "NOTE",
    "note": "NOTE",
    "panel": "NOTE",
    "warning": "WARNING",
    "error": "WARNING",
    "tip": "TIP",
    "success": "TIP",
}

HEADINGS = {f"h{i}": i for i in range(1, 7)}


@dataclass
class TransformResult:
    markdown: str
    unsupported_macros: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None


def transform_storage(body_storage: str) -> TransformResult:
    try:
        root = _parse(body_storage)
    except ET.ParseError:
        return TransformResult(markdown="", error="invalid_xml")
    text = _blocks(root).strip()
    if text:
        text += "\n"
    return TransformResult(markdown=text)


def _parse(body: str) -> Element:
    prepared = body.replace("&nbsp;", "&#160;")
    wrapped = f'<root xmlns:ac="{AC}" xmlns:ri="{RI}">{prepared}</root>'
    return ET.fromstring(wrapped)


def _local(tag: str) -> str:
    if tag.startswith("{"):
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def _attr(el: Element, name: str) -> str:
    return el.get(f"{{{AC}}}{name}") or el.get(f"{{{RI}}}{name}") or el.get(name) or ""


def _blocks(parent: Element) -> str:
    parts = [_block(child) for child in parent]
    chunks = [part.strip("\n") for part in parts if part and part.strip()]
    return "\n\n".join(chunks)


def _block(el: Element) -> str:
    name = _local(el.tag)
    if name in HEADINGS:
        return f"{'#' * HEADINGS[name]} {_inline(el).strip()}"
    if name == "p":
        return _inline(el).strip()
    if name == "ul":
        return _list(el, ordered=False)
    if name == "ol":
        return _list(el, ordered=True)
    if name == "table":
        return _table(el)
    if name == "pre":
        return _pre(el)
    if name == "hr":
        return "---"
    if name == "blockquote":
        inner = _blocks(el).strip()
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if name == "structured-macro":
        return _macro(el)
    if name == "task-list":
        return _task_list(el)
    if name in {"emoticon", "time", "link", "user"}:
        return _inline_element(el)
    if name in {"div", "span", "tbody", "thead", "tfoot"}:
        return _blocks(el) if _has_block_child(el) else _inline(el).strip()
    if name in {"br"}:
        return ""
    if _has_block_child(el):
        return _blocks(el)
    return _inline(el).strip()


def _has_block_child(el: Element) -> bool:
    blockish = {
        "p",
        "ul",
        "ol",
        "table",
        "pre",
        "hr",
        "blockquote",
        "structured-macro",
        "task-list",
        *HEADINGS,
    }
    return any(_local(child.tag) in blockish for child in el)


def _inline(el: Element) -> str:
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(_inline_element(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _inline_element(el: Element) -> str:
    name = _local(el.tag)
    if name in {"em", "i"}:
        inner = _inline(el).strip()
        return f"*{inner}*" if inner else ""
    if name in {"strong", "b"}:
        inner = _inline(el).strip()
        return f"**{inner}**" if inner else ""
    if name == "code":
        return _inline_code(_inline(el))
    if name == "br":
        return "  \n"
    if name == "a":
        text = _inline(el).strip()
        href = el.get("href") or ""
        return f"[{text}]({href})"
    if name == "emoticon":
        return _emoticon(el)
    if name == "time":
        return _time(el)
    if name == "structured-macro":
        return _macro(el)
    if name == "link":
        user = _find_named(el, "user")
        if user is not None:
            return _user(el, user)
        return _inline(el)
    if name == "user":
        return _user(el, el)
    return _inline(el)


def _inline_code(text: str) -> str:
    ticks = "`"
    while ticks in text:
        ticks += "`"
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def _emoticon(el: Element) -> str:
    raw = _attr(el, "name") or _attr(el, "emoji-shortname")
    if not raw:
        return "emoticon"
    return f":{raw.strip(':')}:"


def _time(el: Element) -> str:
    dt = el.get("datetime") or _attr(el, "datetime")
    if dt:
        return dt.split("T", 1)[0]
    return "".join(el.itertext()).strip()


def _user(container: Element, user: Element) -> str:
    display = _attr(user, "display-name") or _link_body(container)
    account = _attr(user, "account-id") or _attr(user, "accountId") or _attr(user, "userkey")
    if display.strip():
        return f"@{display.strip()}"
    if account.strip():
        return f"@{account.strip()}"
    return "@"


def _link_body(el: Element) -> str:
    for child in el:
        if _local(child.tag) in {"plain-text-link-body", "link-body"}:
            return "".join(child.itertext())
    return ""


def _find_named(el: Element, local: str) -> Element | None:
    for child in el.iter():
        if _local(child.tag) == local:
            return child
    return None


def _macro(el: Element) -> str:
    name = _attr(el, "name")
    params = _params(el)
    if name == "code":
        lang = params.get("language") or params.get("lang") or "text"
        return _fenced(_plain_body(el), lang)
    if name in {"plantuml", "plantumlcloud"}:
        return _fenced(_plain_body(el), "plantuml")
    if name in CALLOUT_TYPE:
        return _callout(CALLOUT_TYPE[name], _rich_md(el))
    if name == "expand":
        title = params.get("title") or "Details"
        inner = _rich_md(el).strip()
        body = f"\n\n{inner}\n" if inner else "\n"
        return f"<details>\n<summary>{html_escape(title)}</summary>{body}</details>"
    if name == "status":
        text = params.get("title") or ""
        return f"`{text}`"
    rich = _rich(el)
    if rich is not None:
        return _blocks(rich)
    return _plain_body(el)


def _params(el: Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for child in el:
        if _local(child.tag) == "parameter":
            out[_attr(child, "name")] = "".join(child.itertext())
    return out


def _plain_body(el: Element) -> str:
    for child in el:
        if _local(child.tag) in {"plain-text-body", "cdata-body"}:
            return child.text if child.text is not None else "".join(child.itertext())
    return ""


def _rich(el: Element) -> Element | None:
    for child in el:
        if _local(child.tag) == "rich-text-body":
            return child
    return None


def _rich_md(el: Element) -> str:
    rich = _rich(el)
    if rich is None:
        return ""
    return _blocks(rich)


def _fenced(content: str, lang: str) -> str:
    content = content.replace("\r\n", "\n").strip("\n")
    longest = max((len(match.group()) for match in re.finditer(r"`+", content)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{content}\n{fence}"


def _callout(kind: str, body: str) -> str:
    lines = [f"> [!{kind}]"]
    body = body.strip()
    if body:
        for line in body.split("\n"):
            lines.append(f"> {line}" if line else ">")
    return "\n".join(lines)


def _task_list(el: Element) -> str:
    lines: list[str] = []
    for task in el:
        if _local(task.tag) != "task":
            continue
        status = ""
        body_el: Element | None = None
        for child in task:
            loc = _local(child.tag)
            if loc == "task-status":
                status = "".join(child.itertext()).strip().lower()
            elif loc == "task-body":
                body_el = child
        mark = "[x]" if status in {"complete", "completed", "checked"} else "[ ]"
        text = _inline(body_el).strip() if body_el is not None else ""
        line = f"- {mark}"
        if text:
            line = f"{line} {text}"
        lines.append(line)
    return "\n".join(lines)


def _list(el: Element, *, ordered: bool) -> str:
    lines: list[str] = []
    index = 1
    for child in el:
        if _local(child.tag) != "li":
            continue
        prefix = f"{index}. " if ordered else "- "
        index += 1
        lines.append(prefix + _li_text(child))
    return "\n".join(lines)


def _li_text(li: Element) -> str:
    nested: list[str] = []
    texts: list[str] = []
    if li.text and li.text.strip():
        texts.append(li.text.strip())
    for child in li:
        loc = _local(child.tag)
        if loc == "p":
            texts.append(_inline(child).strip())
        elif loc in {"ul", "ol"}:
            nested.append(_block(child))
        else:
            texts.append(_inline_element(child).strip())
        if child.tail and child.tail.strip():
            texts.append(child.tail.strip())
    text = " ".join(part for part in texts if part)
    if not nested:
        return text
    indented = "\n".join(
        "  " + line for block in nested for line in block.split("\n")
    )
    return f"{text}\n{indented}" if text else indented


def _table(el: Element) -> str:
    rows: list[list[str]] = []
    for section in list(el) or [el]:
        loc = _local(section.tag)
        if loc == "tr":
            _append_row(rows, section)
        elif loc in {"thead", "tbody", "tfoot"}:
            for row in section:
                if _local(row.tag) == "tr":
                    _append_row(rows, row)
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header, *body = normalized
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _append_row(rows: list[list[str]], tr: Element) -> None:
    cells = [
        _cell_text(cell)
        for cell in tr
        if _local(cell.tag) in {"th", "td"}
    ]
    if cells:
        rows.append(cells)


def _cell_text(cell: Element) -> str:
    text = _inline(cell).strip()
    if not text:
        text = _blocks(cell).strip()
    return text.replace("|", "\\|").replace("\n", " ")


def _pre(el: Element) -> str:
    target = next((child for child in el if _local(child.tag) == "code"), el)
    return _fenced("".join(target.itertext()), "text")
