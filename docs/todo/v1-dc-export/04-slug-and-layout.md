# 04 — Slug and layout paths

## Goal

Детерминированно строить slug, безопасные имена вложений и канонические относительные пути медиа.

## Spec

- [`docs/spec/03-output.md#layout`](../../spec/03-output.md#layout)
- [`docs/spec/03-output.md#slug`](../../spec/03-output.md#slug)
- [`docs/spec/03-output.md#cyrillic-transliteration-table`](../../spec/03-output.md#cyrillic-transliteration-table)
- [`docs/spec/03-output.md#safe-filename`](../../spec/03-output.md#safe-filename)

## In scope

- функции путей слоёв относительно корня выгрузки
- slug из title и safe filename с коллизиями на одной странице

## Out of scope

- запись JSON/Markdown на диск
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [01-project-skeleton.md](./01-project-skeleton.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_slug.py` — транслитерация по таблице, обрезка 60, пустой slug → `page`, нет кириллицы в результате.
- `tests/test_safe_filename.py` — Windows/POSIX-опасные символы, коллизии `_2`, current-only не здесь (это fetch).
- `tests/test_layout_paths.py` — единственная форма `../03_assets/<page_id>/<safe_filename>`; имя gold-файла `<page_id>_<slug>.md`.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (layout, имена, slug).
