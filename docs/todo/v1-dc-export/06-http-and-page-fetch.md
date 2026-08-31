# 06 — HTTP and page fetch

## Goal

Синхронно ходить в REST Server/DC: страница, поиск по title, классификация 403/404/`trashed`/типа контента, без скачивания бинарников.

## Spec

- [`docs/spec/01-configuration.md#http-transport`](../../spec/01-configuration.md#http-transport)
- [`docs/spec/04-fetch.md#rest-base`](../../spec/04-fetch.md#rest-base)
- [`docs/spec/04-fetch.md#page-fetch`](../../spec/04-fetch.md#page-fetch)
- [`docs/spec/04-fetch.md#canonical-page-url`](../../spec/04-fetch.md#canonical-page-url)
- [`docs/spec/04-fetch.md#isolation-at-fetch`](../../spec/04-fetch.md#isolation-at-fetch)
- [`docs/spec/02-input.md#page-type`](../../spec/02-input.md#page-type)
- [`docs/spec/02-input.md#accepted-url-forms`](../../spec/02-input.md#accepted-url-forms) (поиск по display-форме)
- [`docs/spec/03-output.md#bronze`](../../spec/03-output.md#bronze) (`source_url`)

## In scope

- таймаут, TLS verify, ретраи 429/502/503/504, без ретраев 401/403
- GET content с `body.storage`; список вложений (метаданные)
- display-URL: пустой поиск → `skipped`, `id` null
- HTTP 401 на первом запросе → невозможный старт

## Out of scope

- скачивание файлов вложений (задача 07)
- disk-skip (задача 08)
- трансформация тела
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [02-settings-and-cli.md](./02-settings-and-cli.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_api_adapter.py` на моках: expand только `body.storage`; нет префикса `/wiki`; 404/`trashed` → `skipped`; 403 → `failed`/`forbidden` без ретрая; тип ≠ `page` → `failed`/`unsupported_content_type`; display-поиск без результатов → `skipped` и `id` null.
- `tests/test_http_retry.py` — ретраи только на 429/502/503/504 с `Retry-After`; 403 не ретраится.
- `tests/test_exit_codes.py::test_exit_2_on_http_401_before_pages`.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (auth, TLS).
