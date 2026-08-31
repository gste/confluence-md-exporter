# 12 — Orchestration

## Goal

Собрать Prefect 3.x flow: параллельная обработка страниц с изоляцией ошибок, запись каталога и отчёта, артефакты UI, коды выхода `0`/`1`, только GET.

## Spec

- [`docs/spec/06-orchestration.md#flow`](../../spec/06-orchestration.md#flow)
- [`docs/spec/06-orchestration.md#page-isolation`](../../spec/06-orchestration.md#page-isolation)
- [`docs/spec/06-orchestration.md#run-success`](../../spec/06-orchestration.md#run-success)
- [`docs/spec/06-orchestration.md#prefect-artifacts`](../../spec/06-orchestration.md#prefect-artifacts)
- [`docs/spec/06-orchestration.md#read-only`](../../spec/06-orchestration.md#read-only)
- [`docs/spec/01-configuration.md#exit-codes`](../../spec/01-configuration.md#exit-codes)
- [`docs/spec/01-configuration.md#cli`](../../spec/01-configuration.md#cli)
- [`docs/spec/00-context.md#in-scope`](../../spec/00-context.md#in-scope) (локальный запуск flow)

## In scope

- один flow на запуск, `EXPORT_CONCURRENCY`
- обход всех валидных id при ошибке одной страницы
- код `0` если нет `failed` (в том числе все `skipped`); код `1` если есть `failed`
- markdown-артефакт на `ok` и сводка на запуск
- вход CLI стартует тот же flow

## Out of scope

- деплой Prefect в кластер
- запись в Confluence
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [03-url-resolver.md](./03-url-resolver.md)
- [05-output-contracts.md](./05-output-contracts.md)
- [08-disk-skip.md](./08-disk-skip.md)
- [10-transform-media-and-links.md](./10-transform-media-and-links.md)
- [11-transform-fallback.md](./11-transform-fallback.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_flow_isolation.py` на моках: одна страница `failed` не отменяет остальные; каталог и отчёт пишутся в конце.
- `tests/test_exit_codes.py::test_exit_0_all_ok_or_skipped`, `::test_exit_0_all_skipped`, `::test_exit_1_partial_failure`.
- `tests/test_prefect_artifacts.py`: на `ok` есть markdown-превью; на запуск — сводка счётчиков; токены в артефакты не попадают.
- Статический или тестовый запрет: flow не вызывает API записи Confluence.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (границы scope / read-only).
