# Epic: `live-run-bugs`

`change type: epic` (внутри — `spec-patch` и один `adr+spec`).

Исправления после живого прогона `uv run --env-file .env confluence-md-exporter` против DC с контекст-путём `/confluence`. Цель: оператор видит, почему вход отклонён и почему старт «зелёный», а страниц нет.

## Run

`opened` эпика: `2026-08-31`. Команда: `uv run --env-file .env confluence-md-exporter`.

- CLI завершился кодом `0`, Prefect: `Completed()`, в stdout не было предупреждений по строкам входа.
- `run_report.json`: `pages_total` 0; `invalid_urls` — четыре исходные строки `/confluence/x/<hash>` без причины.
- Сводка Prefect: только счётчик `invalid_urls: 4`, без URL и без причины.
- Проба `GET /rest/api/user/current` на origin — HTTP 404 (HTML). CLI не остановился: невозможный старт только на 401.
- Тот же PAT: `GET /confluence/rest/api/user/current` — HTTP 200.
- Tiny-link с Bearer уходит на `tinyurl.action` с 401 (HTML-сессия, не REST).

Tiny-link как успешный резолв — не баг: он в [out of scope](../../spec/00-context.md#out-of-scope). Баг — молчаливое отклонение.

## In scope

- Классификация отклонённой строки и явная запись причины (лог, отчёт, сводка).
- Проба идентичности до страниц: не-успех (в том числе 404) — невозможный старт.
- Контекст-путь DC (не `/wiki`) — только после принятого ADR.

## Out of scope

- Успешный резолв tiny-link `/x/<hash>`.
- Cloud, запись в Confluence, descendants, RAG.
- Живой Confluence в автотестах.

## Spec modules

- [`01-configuration.md`](../../spec/01-configuration.md)
- [`02-input.md`](../../spec/02-input.md)
- [`03-output.md`](../../spec/03-output.md)
- [`04-fetch.md`](../../spec/04-fetch.md)
- [`06-orchestration.md`](../../spec/06-orchestration.md)
- [`07-testing.md`](../../spec/07-testing.md)

## Bug

| # | Файл | Opened | Тип | Зависит от |
|---|---|---|---|---|
| 01 | [01-invalid-url-reasons.md](./bug/01-invalid-url-reasons.md) | `2026-08-31` | `spec-patch` | — |
| 02 | [02-auth-probe-non-success.md](./bug/02-auth-probe-non-success.md) | `2026-08-31` | `spec-patch` | — |

01 и 02 независимы. Вести по одному через `/fix-bug`.

## Done

Каталог `docs/todo/live-run-bugs/` удалён после merge последней задачи, которую человек разрешил делать.
