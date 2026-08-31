# Configuration and CLI

Контракт запуска: окружение, CLI, коды выхода. Это не схема кода.

## Runtime

- Python `>=3.11,<3.14`.
- Пакетный менеджер — `uv`; манифест проекта — `pyproject.toml`.
- Оркестратор — Prefect 3.x, зависимость `prefect>=3,<4`.
- HTTP-клиент синхронный на весь конвейер.

## Instance

`CONFLUENCE_BASE_URL` — база приложения Server/Data Center: схема + хост + опционально порт + опционально контекст-путь, без завершающего `/`. Путь `/wiki` и путь, содержащий `/wiki`, запрещены (маркер Cloud). Пример: `https://host/confluence`. Монтирование в корне origin (путь пуст) допустимо.

`CONFLUENCE_EDITION` по умолчанию `datacenter`. Единственное допустимое значение — `datacenter`. Любое другое значение, включая `cloud`, — невозможный старт, код выхода `2`.

## Authentication

Тип задаётся явно полем `CONFLUENCE_AUTH_TYPE`:

| Значение | Заголовки | Обязательные ключи |
|---|---|---|
| `bearer` | `Authorization: Bearer <CONFLUENCE_TOKEN>` | `CONFLUENCE_TOKEN` |
| `basic` | HTTP Basic: username + `CONFLUENCE_TOKEN` как пароль | `CONFLUENCE_USERNAME`, `CONFLUENCE_TOKEN` |

Иное значение `CONFLUENCE_AUTH_TYPE` — невозможный старт, код выхода `2`. Для `basic` отсутствие `CONFLUENCE_USERNAME` — невозможный старт, код выхода `2`.

Файл `.env` с кредами не коммитится. В репозитории поставляется пример ключей (имена и пустые/фиктивные значения, без реальных секретов).

## Environment keys

Имена стабильны. CLI-флаги, где они есть, перекрывают соответствующие ключи на время запуска.

| Ключ | Обязательность | Смысл |
|---|---|---|
| `CONFLUENCE_BASE_URL` | да | база приложения: origin и опциональный контекст-путь |
| `CONFLUENCE_EDITION` | нет, default `datacenter` | только `datacenter` |
| `CONFLUENCE_AUTH_TYPE` | да | `basic` \| `bearer` |
| `CONFLUENCE_TOKEN` | да | PAT или password |
| `CONFLUENCE_USERNAME` | да, если `basic` | username DC |
| `CONFLUENCE_VERIFY_SSL` | нет, default `true` | проверка TLS |
| `CONFLUENCE_TIMEOUT_SECONDS` | нет, default `30` | HTTP timeout, секунды |
| `CONFLUENCE_MAX_RETRIES` | нет, default `3` | ретраи на 429/502/503/504 |
| `EXPORT_OUTPUT_DIR` | нет, default `data` | корень слоёв |
| `EXPORT_INPUT_FILE` | нет, default `input/urls.txt` | входной список |
| `EXPORT_CONCURRENCY` | нет, default `2` | параллелизм страниц, целое ≥ 1 |
| `EXPORT_FORCE_REFRESH` | нет, default `false` | игнорировать disk-skip |
| `LOG_LEVEL` | нет, default `INFO` | уровень логов |

Булевы ключи принимают `true`/`false` без учёта регистра. Нераспознанное значение обязательного или булева ключа — невозможный старт, код выхода `2`.

## HTTP transport

На каждый запрос к Confluence:

- таймаут `CONFLUENCE_TIMEOUT_SECONDS`;
- проверка TLS по `CONFLUENCE_VERIFY_SSL` (по умолчанию включена);
- follow redirects;
- cookie-сессия не используется;
- тот же `Authorization`, что и для API, на скачивание вложений.

Ретраи только на HTTP `429`, `502`, `503`, `504`. Число попыток сверх первой — `CONFLUENCE_MAX_RETRIES`. Если ответ содержит `Retry-After`, пауза уважает этот заголовок; иначе — экспоненциальный backoff, начиная с 1 секунды. HTTP `403` не ретраится. HTTP `401` не ретраится.

## Auth probe

До обработки страниц процесс один раз запрашивает идентичность оператора:

```text
GET /rest/api/user/current
```

относительно `CONFLUENCE_BASE_URL`. Транспорт — [HTTP transport](#http-transport).

Проба пройдена только если ответ — успешный JSON текущего пользователя. Иной исход, в том числе HTTP `401`, `404`, HTML, тело не JSON и JSON без идентичности пользователя, — невозможный старт, код выхода `2`. В stderr — статус или краткая причина; токен и заголовок `Authorization` не пишутся.

При непройденной пробе процесс не пишет слои выгрузки и не обходит страницы. Контекст-путь инстанса по коду ответа не угадывается.

## CLI

CLI принимает как минимум:

| Флаг | Перекрывает | Смысл |
|---|---|---|
| `--input` | `EXPORT_INPUT_FILE` | путь к списку URL |
| `--output` | `EXPORT_OUTPUT_DIR` | корень слоёв |
| `--force-refresh` | `EXPORT_FORCE_REFRESH=true` | полная перевыгрузка, disk-skip выключен |

Иные флаги первой версии не добавляют out-of-scope возможностей (Cloud, запись в Confluence, descendants, RAG).

Вход в процесс — локальный запуск Prefect 3.x flow: прямой вызов flow, `prefect flow run` или эквивалентный CLI-вход, который стартует тот же flow.

## Exit codes

| Код | Когда |
|---|---|
| `0` | старт возможен; среди обработанных страниц нет `failed` (все `ok` или `skipped`, либо вход после разбора пуст) |
| `1` | старт возможен; батч завершился; есть хотя бы одна страница `failed` |
| `2` | конфигурация, аутентификация или иной невозможный старт: процесс не выгружает страницы |

Невозможность старта включает: отсутствующий обязательный ключ; `CONFLUENCE_EDITION` ≠ `datacenter`; невалидный origin; невалидный `CONFLUENCE_AUTH_TYPE`; `basic` без username; входной файл не существует; непройденную пробу идентичности ([#auth-probe](#auth-probe)).

## Logging

Уровень задаёт `LOG_LEVEL`. Дубликаты URL/`pageId` пишут предупреждение в лог. Каждая невалидная строка входа пишет предупреждение в лог: исходная строка и код причины из [02-input.md#rejection-reasons](./02-input.md#rejection-reasons). Причина `failed` / `skipped` / невалидной строки видна в отчёте запуска; лог не подменяет отчёт.
