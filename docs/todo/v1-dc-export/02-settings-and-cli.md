# 02 — Settings and CLI

## Goal

Читать окружение и флаги CLI, отклонять невозможный старт кодом `2`, не выгружая страницы.

## Spec

- [`docs/spec/01-configuration.md#instance`](../../spec/01-configuration.md#instance)
- [`docs/spec/01-configuration.md#authentication`](../../spec/01-configuration.md#authentication)
- [`docs/spec/01-configuration.md#environment-keys`](../../spec/01-configuration.md#environment-keys)
- [`docs/spec/01-configuration.md#cli`](../../spec/01-configuration.md#cli)
- [`docs/spec/01-configuration.md#exit-codes`](../../spec/01-configuration.md#exit-codes)
- [`docs/spec/01-configuration.md#logging`](../../spec/01-configuration.md#logging)

## In scope

- overlay CLI над env
- валидация edition, origin, auth
- коды выхода `2` для невозможного старта
- отсутствие CLI-флагов из out of scope

## Out of scope

- разбор URL, HTTP к инстансу, запись слоёв
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [01-project-skeleton.md](./01-project-skeleton.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- Тесты без сети: `tests/test_settings.py` — отказ при `CONFLUENCE_EDITION` ≠ `datacenter`; невалидный `CONFLUENCE_AUTH_TYPE`; `basic` без username; отсутствующий обязательный ключ; CLI `--input` / `--output` / `--force-refresh` перекрывают env.
- Тест кода выхода `2` (процесс не начинает выгрузку страниц): `tests/test_exit_codes.py::test_exit_2_on_bad_config`.
- Нет флагов Cloud / descendants / записи в Confluence.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (аутентификация, `CONFLUENCE_VERIFY_SSL`).
