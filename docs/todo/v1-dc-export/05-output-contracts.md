# 05 — Output contracts

## Goal

Писать bronze, sidecar, interim, gold с frontmatter, `manifest.json` и `run_report.json` по контракту слоёв.

## Spec

- [`docs/spec/03-output.md#bronze`](../../spec/03-output.md#bronze)
- [`docs/spec/03-output.md#asset-sidecar`](../../spec/03-output.md#asset-sidecar)
- [`docs/spec/03-output.md#interim`](../../spec/03-output.md#interim)
- [`docs/spec/03-output.md#gold-markdown`](../../spec/03-output.md#gold-markdown)
- [`docs/spec/03-output.md#manifest`](../../spec/03-output.md#manifest)
- [`docs/spec/03-output.md#run-report`](../../spec/03-output.md#run-report)
- [`docs/spec/03-output.md#page-status`](../../spec/03-output.md#page-status)

## In scope

- сериализация перечисленных артефактов из уже готовых структур данных
- стабильные ключи; `page_id` строка; `id` манифеста допускается `null`

## Out of scope

- HTTP, макро-движок, Prefect artifacts
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [04-slug-and-layout.md](./04-slug-and-layout.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_manifest_and_report.py` — обязательные ключи манифеста и отчёта; невалидные URL в манифест не входят; статусы `ok` / `failed` / `skipped`.
- `tests/test_bronze_and_frontmatter.py` — обязательные ключи bronze и YAML frontmatter; `edition` = `datacenter`; `body_storage` есть, тел `view` / `export_view` / `atlas_doc_format` нет.
- Sidecar `01_raw/<page_id>.assets.json` пишется при наличии вложений и не пишется, если вложений нет.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (публичные контракты).
