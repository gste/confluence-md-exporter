# 13 — Fixture coverage

## Goal

Закрыть обязательное фикстурное покрытие без сети: все паттерны URL, все известные конструкции, fallback, краевые случаи, disk-skip, ссылки на медиа, коды выхода.

## Spec

- [`docs/spec/07-testing.md#coverage`](../../spec/07-testing.md#coverage)
- [`docs/spec/07-testing.md#fixtures`](../../spec/07-testing.md#fixtures)
- [`docs/spec/07-testing.md#secrets`](../../spec/07-testing.md#secrets)
- [`docs/spec/07-testing.md#product-acceptance`](../../spec/07-testing.md#product-acceptance)
- [`docs/spec/00-context.md#goals`](../../spec/00-context.md#goals)
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## In scope

- сквозной фикстурный прогон (моки транспорта), который стыкует результаты задач 03–12
- проверка, что out of scope не всплыл в CLI и контрактах

## Out of scope

- обязательный прогон против живого DC (допустим как ручной, не как CI)
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [12-orchestration.md](./12-orchestration.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_fixture_pipeline.py` (или набор с тем же смыслом) без сети зелёный и покрывает все пункты [`07-testing.md#coverage`](../../spec/07-testing.md#coverage): URL-паттерны, known-constructs, fallback, edge cases, disk-skip + force-refresh, manifest/report, exit `0`/`1`/`2`, edition ≠ `datacenter`, резолв `../03_assets/...`.
- Повторный прогон без force-refresh на неизменённых страницах: `skipped` и неизменные байты page Markdown и ассетов.
- Фикстуры синтетические; токенов и корпоративных страниц в git нет.
- CLI/тесты не содержат Cloud, запись в Confluence, descendants, RAG, успешный tiny-link.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (секреты; границы scope).
