# Epic: `v1-dc-export`

Локальный read-only конвейер первой версии: список URL → Markdown, медиа, каталог батча и отчёт, запуск через Prefect 3.x. Объём — весь принятый пакет `docs/spec/`, кроме того, что спека объявила out of scope.

## In scope

Первая версия продукта по модулям ниже. Одна задача — один PR, порядок не нарушает зависимости.

## Out of scope

Всё из [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope). Правки `docs/spec/**`. Живой Confluence в автоматических тестах.

## Spec modules

- [`00-context.md`](../../spec/00-context.md) — границы, цели, human-gated
- [`01-configuration.md`](../../spec/01-configuration.md)
- [`02-input.md`](../../spec/02-input.md)
- [`03-output.md`](../../spec/03-output.md)
- [`04-fetch.md`](../../spec/04-fetch.md)
- [`05-transform.md`](../../spec/05-transform.md)
- [`06-orchestration.md`](../../spec/06-orchestration.md)
- [`07-testing.md`](../../spec/07-testing.md)

## Tasks

| # | Файл | Зависит от |
|---|---|---|
| 01 | [01-project-skeleton.md](./01-project-skeleton.md) | — |
| 02 | [02-settings-and-cli.md](./02-settings-and-cli.md) | 01 |
| 03 | [03-url-resolver.md](./03-url-resolver.md) | 02 |
| 04 | [04-slug-and-layout.md](./04-slug-and-layout.md) | 01 |
| 05 | [05-output-contracts.md](./05-output-contracts.md) | 04 |
| 06 | [06-http-and-page-fetch.md](./06-http-and-page-fetch.md) | 02 |
| 07 | [07-attachment-download.md](./07-attachment-download.md) | 04, 06 |
| 08 | [08-disk-skip.md](./08-disk-skip.md) | 05, 06, 07 |
| 09 | [09-transform-core.md](./09-transform-core.md) | 04 |
| 10 | [10-transform-media-and-links.md](./10-transform-media-and-links.md) | 07, 09 |
| 11 | [11-transform-fallback.md](./11-transform-fallback.md) | 09 |
| 12 | [12-orchestration.md](./12-orchestration.md) | 03, 05, 08, 10, 11 |
| 13 | [13-fixture-coverage.md](./13-fixture-coverage.md) | 12 |

04 можно делать параллельно с 02–03. 06 — параллельно с 03–05 после 02. 09 — параллельно с 06–08 после 04.

## Done

Все 13 задач смержены. Каталог `docs/todo/v1-dc-export/` удалён. Покрытие [`07-testing.md#coverage`](../../spec/07-testing.md#coverage) зелёное без сети.
