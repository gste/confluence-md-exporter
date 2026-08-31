# 11 — Transform fallback and edges

## Goal

Обрабатывать неизвестные макросы и краевые случаи так, чтобы страница не оставалась в неопределённом состоянии и не падала только из‑за fallback.

## Spec

- [`docs/spec/05-transform.md#unknown-macros`](../../spec/05-transform.md#unknown-macros)
- [`docs/spec/05-transform.md#edge-cases`](../../spec/05-transform.md#edge-cases)

## In scope

- комментарий `unsupported-macro`, сохранённый текст, список во frontmatter
- все строки таблицы edge cases, кроме тех, что уже закрыты задачами 06–07 (404/`trashed`/403, скачивание чужого вложения)

## Out of scope

- новые известные макросы вне таблицы known-constructs
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [09-transform-core.md](./09-transform-core.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_unknown_macro_fallback.py`: неизвестный макрос → HTML-комментарий с именем, текст сохранён, имя в `unsupported_macros`, статус страницы не `failed` только из‑за этого.
- `tests/test_edge_cases.py`: пустое тело; макрос без body; тройные бэктики в code; таблица colspan/rowspan → прямоугольный GFM; HTML-entities в title до slug/frontmatter.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (fallback неизвестных макросов).
