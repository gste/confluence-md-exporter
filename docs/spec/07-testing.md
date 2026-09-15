# Testing obligations

Автоматические тесты обязательны для перечисленного ниже. Живой Confluence в CI и в локальном `pytest`/`uv run` не требуется: достаточно фикстур XML/JSON. Сетевые вызовы в этих тестах запрещены (моки транспорта допустимы).

## Coverage

Фикстурный прогон без сети покрывает:

- каждый допустимый URL-паттерн из [02-input.md#accepted-url-forms](./02-input.md#accepted-url-forms);
- каждую конструкцию из [05-transform.md#known-constructs](./05-transform.md#known-constructs);
- fallback неизвестного макроса из [05-transform.md#unknown-macros](./05-transform.md#unknown-macros);
- каждый краевой случай из [05-transform.md#edge-cases](./05-transform.md#edge-cases);
- disk-skip и `--force-refresh` из [04-fetch.md#disk-skip](./04-fetch.md#disk-skip);
- сборку `manifest.json` и `run_report.json` из [03-output.md](./03-output.md);
- коды причины отклонённых URL из [02-input.md#rejection-reasons](./02-input.md#rejection-reasons);
- коды выхода `0` / `1` / `2` из [01-configuration.md#exit-codes](./01-configuration.md#exit-codes);
- отказ стартовать при `CONFLUENCE_EDITION`, отличном от `datacenter`;
- канонические ссылки `../03_assets/...`: каждая такая ссылка в сгенерированном Markdown резолвится в существующий файл.

Повторный прогон без force-refresh на неизменённых страницах даёт `skipped` и не меняет байты актуальных файлов в `03_assets/` и `04_markdown/<page_id>_*.md`. Это проверяется тестом, не только ручным прогоном.

Out of scope не появляется в CLI, выходных контрактах и тестах первой версии: нет флагов и фикстур, которые реализуют Cloud, запись в Confluence, descendants, RAG, tiny-link как успешный резолв.

## Fixtures

Фикстуры — синтетические. В репозитории нет реальных корпоративных страниц, токенов, паролей и персональных данных.

## Secrets

Тесты, логи и коммиты не содержат реальных кред. Содержимое страниц на диске оператора и в Prefect preview не маскируется — это не требование тестов, а запрет добавлять маскирование как фичу первой версии.

## Product acceptance

Первая версия принята, когда одновременно верно:

1. Цели [00-context.md#goals](./00-context.md#goals) наблюдаются на прогоне (фикстурном и, если доступен инстанс DC, на нём).
2. Обязательное покрытие этого файла зелёное без сети.
3. Все ссылки `../03_assets/...` в сгенерированных Markdown резолвятся в существующий файл.
4. Повторный прогон без force-refresh на неизменённых страницах даёт `skipped` и не меняет байты актуальных медиа и Markdown страниц.
5. Out of scope из [00-context.md#out-of-scope](./00-context.md#out-of-scope) не появляется в CLI, контрактах и тестах.
6. Файлы кредов и токены не коммитятся и не кладутся в фикстуры.
