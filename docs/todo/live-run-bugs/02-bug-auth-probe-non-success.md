# 02 — Auth probe fails closed

## Kind

`bug`

## Goal

Первый запрос к инстансу до обработки страниц — невозможный старт с кодом `2`, если это не успешная идентичность оператора. HTTP 404, HTML и прочий не-успех не считаются пройденной пробой.

## Spec

- [`docs/spec/01-configuration.md#exit-codes`](../../spec/01-configuration.md#exit-codes)
- [`docs/spec/01-configuration.md#http-transport`](../../spec/01-configuration.md#http-transport)
- [`docs/spec/04-fetch.md#rest-base`](../../spec/04-fetch.md#rest-base)
- [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (аутентификация)

## In scope

- проба идентичности до батча
- exit `2` и сообщение в stderr при статусе, отличном от успешного JSON-ответа текущего пользователя (включая 401 и 404)
- процесс не пишет слои выгрузки и не обходит страницы

## Out of scope

- угадывание контекст-пути `/confluence` при 404
- cookie-сессия, UI login
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

none

## Spec delta

- ADDED: `docs/spec/01-configuration.md#auth-probe`
- MODIFIED: `docs/spec/01-configuration.md#exit-codes`, `docs/spec/04-fetch.md#rest-base`
- REMOVED: none

## Spec edits allowed

yes (только якоря дельты)

## Definition of Done

- Спека внутри дельты: невозможный старт включает любой ответ пробы, который не подтверждает текущего пользователя.
- `tests/test_exit_codes.py`: 401 → `2`; 404 → `2`; не-JSON 200 → `2`; успешный JSON пользователя → проба проходит; страницы при `2` не выгружаются.
- В stderr есть статус (или краткая причина), без токена и заголовка `Authorization`.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (аутентификация).
