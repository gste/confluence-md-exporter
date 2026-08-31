# Изменения в сервисе

## Unreleased

- процесс: тесты слайса сначала красные на текущем коде, затем фиксация; красное не коммитить
- процесс: в конце реализации явно `spec unchanged`, если `docs/spec/**` не менялся
- 15 проба идентичности fail-closed: любой не-успех (в т.ч. 404, HTML) — выход `2`
- 14 явные причины отклонения URL (`invalid_urls` как `{url, reason}`)
- процесс: фреймворк DeltaFuse (`delta-fuse`), гайд `docs/process/using.md`
- процесс: сквозной NN inbox, auto-commit шага, таблица Closed в docs/todo/README.md
