# Изменения в сервисе

## Unreleased

- CLI `-h` и README: сценарии запуска с PyPI, дефолты, коды выхода; `-s` скрыт из справки
- README.md на английском, русская версия — `README.ru.md`; CLI `-h` на английском

## 1.0.0 — 2026-09-15

Первый публичный релиз на PyPI.

- запуск без `.env`: аноним по умолчанию, `-u`/`-t` для доступа, база из списка URL
- выгрузка всегда однопоточная, без Prefect; прогресс каждой страницы в консоли; снимок Prefect — тег `history/prefect-orchestration`
- default `EXPORT_OUTPUT_DIR` — `output/` (`01-configuration.md`, `03-output.md#layout`)
- 17 именованные HTML-сущности в Storage Format не валят страницу (`05-transform.md#edge-cases`)
- тест-кейсы живут в `tests/`, не отдельным каталогом в `docs/` (`07-testing.md#test-cases`)
- процесс: `/init-requirements` при непустом `docs/init/` спрашивает архив, сброс или стоп (`01-init-requirements.md#existing-init`)
- процесс: тесты слайса сначала красные на текущем коде, затем фиксация; красное не коммитить
- процесс: в конце реализации явно `spec unchanged`, если `docs/spec/**` не менялся
- 15 проба идентичности fail-closed: любой не-успех (в т.ч. 404, HTML) — выход `2`
- 14 явные причины отклонения URL (`invalid_urls` как `{url, reason}`)
- процесс: фреймворк DeltaFuse (`delta-fuse`), гайд `docs/process/using.md`
- процесс: сквозной NN inbox, auto-commit шага, таблица Closed в docs/todo/README.md
