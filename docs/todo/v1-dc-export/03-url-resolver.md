# 03 — URL resolver

## Goal

Читать входной файл и резолвить строки в `page_id` либо в `invalid_urls` / `skipped` по правилам входа.

## Spec

- [`docs/spec/02-input.md#input-file`](../../spec/02-input.md#input-file)
- [`docs/spec/02-input.md#accepted-url-forms`](../../spec/02-input.md#accepted-url-forms)
- [`docs/spec/02-input.md#rejected-forms`](../../spec/02-input.md#rejected-forms)
- [`docs/spec/02-input.md#deduplication`](../../spec/02-input.md#deduplication)

## In scope

- UTF-8 список, комментарии, пустые строки, отсутствующий файл vs пустой список
- шесть допустимых форм, origin check, дедупликация
- невалидные строки не попадают в манифест (достаточно структуры результата резолва)

## Out of scope

- GET content, трансформация, запись слоёв
- успешный резолв tiny-link
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [02-settings-and-cli.md](./02-settings-and-cli.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_url_resolver.py` без сети покрывает каждый паттерн из [`02-input.md#accepted-url-forms`](../../spec/02-input.md#accepted-url-forms).
- Отдельные случаи: tiny-link и прочие отвергнутые формы → невалидная строка; дубликаты схлопываются; пустой файл после разбора → `pages_total` 0.
- Отсутствующий файл — невозможный старт (согласовано с [`01-configuration.md#exit-codes`](../../spec/01-configuration.md#exit-codes)).
- Форма display без найденной страницы не помечается как невалидный URL (мок поиска — в задаче 06, здесь достаточно контракта «форма принята»).
