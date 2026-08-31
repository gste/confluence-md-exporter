# 09 — Transform core

## Goal

Переводить Storage Format в GFM для известных конструкций, которые не требуют локальных ассетов и внутренних ссылок на `.md`.

## Spec

- [`docs/spec/05-transform.md#known-constructs`](../../spec/05-transform.md#known-constructs)

## In scope

- обычный HTML → GFM
- макросы `code`, `plantuml` / `plantumlcloud`, callouts, `expand`, `status`, task list, emoticon, пользователь, дата/time
- разбор XML с пространствами `ac` / `ri` из того же модуля

## Out of scope

- `ac:image`, вложение в ссылке, `drawio` / `draw.io` (задача 10)
- внутренние `ac:link` + `ri:page` (задача 10)
- unknown-macro fallback и таблица edge cases (задача 11)
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [04-slug-and-layout.md](./04-slug-and-layout.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_macro_handlers.py` без сети: отдельный кейс на каждую конструкцию из in scope; fenced `code` с удлинением ограды; PlantUML без растра; цвет `status` игнорируется.
- Битый XML тела → страница `failed`, не молчаливый пустой файл (согласовано с вводным абзацем [`05-transform.md`](../../spec/05-transform.md)).
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (каталог макросов).
