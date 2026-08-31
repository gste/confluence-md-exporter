# 03 — DC context path

## Kind

`bug`

## Goal

REST и разбор входных URL работают, когда приложение DC смонтировано не в корне origin (типично `/confluence`), без префикса Cloud `/wiki`. Формулировка — только зеркало принятого [ADR 0001](../../decisions/0001-dc-context-path.md).

## Spec

- [`docs/spec/01-configuration.md#instance`](../../spec/01-configuration.md#instance)
- [`docs/spec/01-configuration.md#environment-keys`](../../spec/01-configuration.md#environment-keys)
- [`docs/spec/02-input.md#accepted-url-forms`](../../spec/02-input.md#accepted-url-forms)
- [`docs/spec/04-fetch.md#rest-base`](../../spec/04-fetch.md#rest-base)
- [`docs/spec/00-context.md#external-constraints`](../../spec/00-context.md#external-constraints)

## In scope

- зеркало принятого ADR 0001 в перечисленных якорях
- тесты без сети на выбранный контракт base URL / префикса путей

## Out of scope

- реализация при ADR `proposed` или `rejected`
- tiny-link как успешный резолв
- Cloud `/wiki`
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- человек: `status: accepted` у [ADR 0001](../../decisions/0001-dc-context-path.md)
- затем merge спеки по дельте ниже (человек)

## Spec delta

Черновик до принятия ADR (уточнить после `accepted`, если выбрали другой вариант):

- ADDED: none
- MODIFIED: `docs/spec/01-configuration.md#instance`, `docs/spec/01-configuration.md#environment-keys`, `docs/spec/02-input.md#accepted-url-forms`, `docs/spec/04-fetch.md#rest-base`, `docs/spec/00-context.md#external-constraints`
- REMOVED: none

## Spec edits allowed

yes (только якоря дельты, и только после `accepted`)

## Definition of Done

- Не начинать код, пока ADR не `accepted` и спека не смержена.
- После этого: фикстурные тесты, что API и формы URL считаются от базы приложения, а `/wiki` по-прежнему запрещён.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (аутентификация / границы instance).
