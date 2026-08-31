# 01 — Explicit invalid URL reasons

## Kind

`bug`

## Goal

Каждая отклонённая строка входа классифицируется кодом причины. Причина пишется явно: WARNING в лог (строка + код), элемент `invalid_urls` в `run_report.json`, перечень в сводке Prefect. Tiny-link остаётся невалидным.

## Spec

- [`docs/spec/01-configuration.md#logging`](../../spec/01-configuration.md#logging)
- [`docs/spec/02-input.md#rejected-forms`](../../spec/02-input.md#rejected-forms)
- [`docs/spec/03-output.md#run-report`](../../spec/03-output.md#run-report)
- [`docs/spec/06-orchestration.md#prefect-artifacts`](../../spec/06-orchestration.md#prefect-artifacts)
- [`docs/spec/07-testing.md#coverage`](../../spec/07-testing.md#coverage)
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope) (tiny-link не становится успешным резолвом)

## In scope

- коды: `tiny_link`, `origin_mismatch`, `malformed`, `unrecognized_form`
- WARNING на каждую отклонённую строку
- `invalid_urls` как массив объектов `{ "url", "reason" }`
- сводка Prefect перечисляет каждую пару url/reason, не только счётчик
- код выхода при пустом множестве валидных id без `failed` остаётся `0`

## Out of scope

- резолв tiny-link в `page_id`
- контекст-путь инстанса
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

none

## Spec delta

- ADDED: `docs/spec/02-input.md#rejection-reasons`
- MODIFIED: `docs/spec/01-configuration.md#logging`, `docs/spec/02-input.md#rejected-forms`, `docs/spec/03-output.md#run-report`, `docs/spec/06-orchestration.md#prefect-artifacts`, `docs/spec/07-testing.md#coverage`
- REMOVED: none

## Spec edits allowed

yes (только якоря дельты)

## Definition of Done

- Спека внутри дельты: причина отклонённой строки обязательна в отчёте и в логе; `invalid_urls` — объекты, не голые строки.
- `tests/test_url_resolver.py`: tiny-link → `tiny_link`; чужой origin → `origin_mismatch`; `viewpage.action` без одного `pageId` → `malformed`; прочий мусор → `unrecognized_form`; успешный резолв tiny-link отсутствует.
- `tests/test_manifest_and_report.py`: `invalid_urls` — `{url, reason}`; в манифест по-прежнему не входят.
- Лог содержит WARNING с исходной строкой и кодом; сводка Prefect — тот же перечень.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (публичный контракт `run_report.json`).
