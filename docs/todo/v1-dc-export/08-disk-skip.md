# 08 — Disk-skip

## Goal

Пропускать неизменённые страницы по локальной `version` и size ассетов; `--force-refresh` отключает пропуск.

## Spec

- [`docs/spec/04-fetch.md#disk-skip`](../../spec/04-fetch.md#disk-skip)
- [`docs/spec/03-output.md#page-status`](../../spec/03-output.md#page-status)
- [`docs/spec/01-configuration.md#cli`](../../spec/01-configuration.md#cli) (`--force-refresh`)

## In scope

- сравнение версии и размеров локальных ассетов
- запрет перезаписи raw / assets / interim / page Markdown при skip
- перезапись `manifest.json` и `run_report.json` каждый запуск

## Out of scope

- ETag / условные GET
- кэш Prefect как замена этому правилу
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [05-output-contracts.md](./05-output-contracts.md)
- [06-http-and-page-fetch.md](./06-http-and-page-fetch.md)
- [07-attachment-download.md](./07-attachment-download.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_disk_skip.py` без сети: совпавшая версия и size → `skipped`, байты `03_assets/<page_id>/**` и `04_markdown/<page_id>_*.md` не меняются; изменившаяся версия / дырка в ассетах / `--force-refresh` → полная обработка.
- Кэш Prefect в тесте не подменяет проверку диска.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (disk-skip).
