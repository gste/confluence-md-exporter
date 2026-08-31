# 17 — Named HTML entities in Storage Format

## Kind

`bug`

## Opened

`2026-08-31`

## Goal

Именованная HTML-сущность в `body_storage` (например `&ldquo;`), которую XML 1.0 не определяет, не делает страницу `failed`. Тело разбирается, страница `ok`, сущность в Markdown — соответствующий символ. По-настоящему неразбираемая разметка по-прежнему `invalid_xml`.

## Spec

- [`docs/spec/05-transform.md#edge-cases`](../../../spec/05-transform.md#edge-cases)
- [`docs/spec/07-testing.md#coverage`](../../../spec/07-testing.md#coverage)
- [`docs/spec/00-context.md#human-gated-areas`](../../../spec/00-context.md#human-gated-areas) (каталог трансформа и fallback)

## In scope

- именованные HTML-сущности в теле Storage Format
- страница остаётся `ok`, Markdown записан
- реально битая разметка (незакрытый тег и т.п.) — по-прежнему `failed` / `invalid_xml`

## Out of scope

- смена парсера на полный HTML5, если достаточно декодирования сущностей
- [`docs/spec/00-context.md#out-of-scope`](../../../spec/00-context.md#out-of-scope)

## Depends on

none

## Spec delta

- ADDED: none
- MODIFIED: `docs/spec/05-transform.md#edge-cases`
- REMOVED: none

## Spec edits allowed

yes (только якоря дельты)

## Run

`uv run --env-file .env confluence-md-exporter`. Код выхода `1`. `pages_total=4`, `ok=3`, `failed=1`. У `failed`: `page_id=607635537`, `error=invalid_xml`. Разбор тела: `undefined entity` на `&ldquo;`. Тел страниц и живых URL в этой записи нет.

## Definition of Done

- Спека внутри дельты: именованные HTML-сущности в теле — краевой случай, страница не `failed`.
- `tests/test_macro_handlers.py`: `test_named_html_entities_in_storage_keep_page_ok` — тело с `&ldquo;` даёт `ok` и символ в Markdown; `test_broken_xml_fails_page` по-прежнему `invalid_xml` на незакрытом теге.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../../spec/00-context.md#human-gated-areas) (каталог известных макросов и fallback).
