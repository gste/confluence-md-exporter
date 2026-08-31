# 01 — Project skeleton

## Goal

Завести Python-пакет первой версии с `uv` и `pyproject.toml`, зависимостью Prefect 3.x и примером ключей окружения без секретов.

## Spec

- [`docs/spec/01-configuration.md#runtime`](../../spec/01-configuration.md#runtime)
- [`docs/spec/01-configuration.md#environment-keys`](../../spec/01-configuration.md#environment-keys) (имена ключей в примере)
- [`docs/spec/01-configuration.md#authentication`](../../spec/01-configuration.md#authentication) (`.env` не в git)
- [`docs/spec/07-testing.md#secrets`](../../spec/07-testing.md#secrets)
- [`docs/spec/07-testing.md#fixtures`](../../spec/07-testing.md#fixtures)

## In scope

- `pyproject.toml`, диапазон Python, `prefect>=3,<4`, `uv`
- каркас пакета и каталог `tests/`
- пример ключей окружения с пустыми/фиктивными значениями
- игнор файла кредов в VCS

## Out of scope

- загрузка настроек, CLI, HTTP, flow
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

none

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `uv sync` (или эквивалент) ставит окружение на объявленном диапазоне Python.
- В репозитории есть пример ключей; файл с реальными кредами не коммитится.
- `tests/` существует; в фикстурах нет токенов и корпоративных страниц.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (секреты в коммитах).
