# Configuration and CLI

Контракт запуска: окружение, CLI, коды выхода. Это не схема кода.

## Runtime

- Python `>=3.11,<3.14`.
- Пакетный менеджер — `uv`; манифест проекта — `pyproject.toml`.
- Выгрузка однопоточная: один процесс, страницы строго последовательно.
- HTTP-клиент синхронный на весь конвейер.

## Instance

`CONFLUENCE_BASE_URL` — база приложения Server/Data Center: схема + хост + опционально порт + опционально контекст-путь, без завершающего `/`. Путь `/wiki` и путь, содержащий `/wiki`, запрещены (маркер Cloud). Пример: `https://host/confluence`. Монтирование в корне origin (путь пуст) допустимо.

База не обязательна во флаге и в окружении. Если она не задана, процесс выводит её из абсолютных URL входного списка ([02-input.md#base-url-inference](./02-input.md#base-url-inference)). Явный `--base-url` / `CONFLUENCE_BASE_URL` перекрывает вывод. Если базу нельзя определить — невозможный старт, код выхода `2`.

`CONFLUENCE_EDITION` по умолчанию `datacenter`. Единственное допустимое значение — `datacenter`. Любое другое значение, включая `cloud`, — невозможный старт, код выхода `2`.

## Authentication

По умолчанию доступ анонимный: заголовок `Authorization` не отправляется. Креды не обязательны.

Если `CONFLUENCE_AUTH_TYPE` не задан, тип выводится из кредов:

| Креды | Тип | Заголовки |
|---|---|---|
| нет username и нет token | `anonymous` | без `Authorization` |
| только token | `bearer` | `Authorization: Bearer <token>` |
| username и token | `basic` | HTTP Basic: username + token как пароль |
| только username | невозможный старт, код `2` | |

Явное `CONFLUENCE_AUTH_TYPE`:

| Значение | Заголовки | Обязательные ключи |
|---|---|---|
| `anonymous` | без `Authorization` | нет |
| `bearer` | `Authorization: Bearer <token>` | token |
| `basic` | HTTP Basic: username + token как пароль | username и token |

Иное значение `CONFLUENCE_AUTH_TYPE` — невозможный старт, код выхода `2`.

CLI-флаги `--user` и `--token` перекрывают соответствующие ключи окружения на время запуска. Файл `.env` не обязателен; если используется, в git не коммитится. Токен в лог и stderr не пишется.

## Environment keys

Имена стабильны. CLI-флаги, где они есть, перекрывают соответствующие ключи на время запуска.

| Ключ | Обязательность | Смысл |
|---|---|---|
| `CONFLUENCE_BASE_URL` | нет | база приложения; иначе выводится из входных URL |
| `CONFLUENCE_EDITION` | нет, default `datacenter` | только `datacenter` |
| `CONFLUENCE_AUTH_TYPE` | нет | `anonymous` \| `basic` \| `bearer`; иначе выводится из кредов |
| `CONFLUENCE_TOKEN` | нет | PAT или password; без него доступ анонимный |
| `CONFLUENCE_USERNAME` | нет | username DC; вместе с token даёт `basic` |
| `CONFLUENCE_VERIFY_SSL` | нет, default `true` | проверка TLS |
| `CONFLUENCE_TIMEOUT_SECONDS` | нет, default `30` | HTTP timeout, секунды |
| `CONFLUENCE_MAX_RETRIES` | нет, default `3` | ретраи на 429/502/503/504 |
| `EXPORT_OUTPUT_DIR` | нет, default `output` | корень слоёв |
| `EXPORT_INPUT_FILE` | нет, default `input/urls.txt` | входной список |
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

При `anonymous` проба идентичности не выполняется: процесс сразу обходит страницы. Страница, закрытая для анонима (HTTP `401`/`403`), получает статус `failed` и не валит весь батч.

При `bearer` и `basic` до обработки страниц процесс один раз запрашивает идентичность оператора:

```text
GET /rest/api/user/current
```

относительно базы приложения. Транспорт — [HTTP transport](#http-transport).

Проба пройдена только если ответ — успешный JSON текущего пользователя. Иной исход, в том числе HTTP `401`, `404`, HTML, тело не JSON и JSON без идентичности пользователя, — невозможный старт, код выхода `2`. В stderr — статус или краткая причина; токен и заголовок `Authorization` не пишутся.

При непройденной пробе процесс не пишет слои выгрузки и не обходит страницы. Контекст-путь инстанса по коду ответа не угадывается.

## CLI

CLI принимает как минимум:

| Флаг | Перекрывает | Смысл |
|---|---|---|
| `--input` | `EXPORT_INPUT_FILE` | путь к списку URL, default `input/urls.txt` |
| `--output` | `EXPORT_OUTPUT_DIR` | корень слоёв, default `output` |
| `--user` | `CONFLUENCE_USERNAME` | username; вместе с `--token` даёт basic |
| `--token` | `CONFLUENCE_TOKEN` | PAT или password |
| `--base-url` | `CONFLUENCE_BASE_URL` | база приложения; иначе выводится из входных URL |
| `--force-refresh` | `EXPORT_FORCE_REFRESH=true` | полная перевыгрузка, disk-skip выключен |

Иные флаги первой версии не добавляют out-of-scope возможностей (Cloud, запись в Confluence, descendants, RAG).

Вход в процесс — локальный CLI, который запускает однопоточный скрипт выгрузки.

## Exit codes

| Код | Когда |
|---|---|
| `0` | старт возможен; среди обработанных страниц нет `failed` (все `ok` или `skipped`, либо вход после разбора пуст) |
| `1` | старт возможен; батч завершился; есть хотя бы одна страница `failed` |
| `2` | конфигурация, аутентификация или иной невозможный старт: процесс не выгружает страницы |

Невозможность старта включает: `CONFLUENCE_EDITION` ≠ `datacenter`; невалидный origin или невыводимую базу; невалидный `CONFLUENCE_AUTH_TYPE`; `basic` / username без token; входной файл не существует; непройденную пробу идентичности при `bearer`/`basic` ([#auth-probe](#auth-probe)).

## Logging

Уровень задаёт `LOG_LEVEL`. Дубликаты URL/`pageId` пишут предупреждение в лог. Каждая невалидная строка входа пишет предупреждение в лог: исходная строка и код причины из [02-input.md#rejection-reasons](./02-input.md#rejection-reasons).

На уровне INFO консоль показывает прогресс выгрузки: старт (число страниц, число невалидных URL, пути входа и выхода, `force_refresh`); каждую страницу на выборке и на записи (порядковый номер из общего числа, идентификатор, статус `ok` / `skipped` / `failed`, заголовок если известен, причина ошибки если есть); финиш (`ok` / `failed` / `skipped` / `invalid_urls` и длительность).

Причина `failed` / `skipped` / невалидной строки видна в отчёте запуска; лог не подменяет отчёт.
