# Epic: `live-run-bugs`

`change type: epic` (внутри — `spec-patch`).

Наблюдения с живого прогона `uv run --env-file .env confluence-md-exporter` против DC. Цель: страница, которую Confluence отдаёт как обычный Storage Format, выгружается; именованные HTML-сущности в теле не считаются битым XML.

## In scope

- Именованные HTML-сущности в `body_storage` не переводят страницу в `failed`.

## Out of scope

- Успешный резолв tiny-link `/x/<hash>`.
- Cloud, запись в Confluence, descendants, RAG.
- Живой Confluence в автотестах.

## Spec modules

- [`05-transform.md`](../../spec/05-transform.md)
- [`07-testing.md`](../../spec/07-testing.md)

## Bug

| # | Файл | Opened | Тип | Зависит от |
|---|---|---|---|---|
| 17 | [17-html-entities-in-storage.md](./bug/17-html-entities-in-storage.md) | `2026-08-31` | `spec-patch` | — |

Вести через `/fix-bug`.

## Done

Каталог `docs/todo/live-run-bugs/` удаляется после merge последнего слайса.
