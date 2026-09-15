# Configuration and CLI

Контракт запуска: окружение, CLI, коды выхода. Это не схема кода.

## Runtime

- Python `>=3.11,<3.15`.
- Пакетный менеджер — `uv`; манифест проекта — `pyproject.toml`.
- Выгрузка однопоточная: один процесс, страницы строго последовательно.
- HTTP-клиент синхронный на весь конвейер.

## Instance

`CONFLUENCE_BASE_URL` — база приложения Server/Data Center: схема + хост + опционально порт + опционально контекст-путь, без завершающего `/`. Путь `/wiki` и путь, содержащий `/wiki`, запрещены (маркер Cloud). Пример: `https://host/confluence`. Монтирование в корне origin (путь пуст) допустимо.

База не обязательна во флаге и в окружении. Если она не задана, процесс выводит её из абсолютных URL входного списка ([02-input.md#base-url-inference](./02-input.md#base-url-inference)). Явный `--base-url` / `CONFLUENCE_BASE_URL` перекрывает вывод. Если базу нельзя определить — невозможный старт, код выхода `2`.

`CONFLUENCE_EDITION` по умолчанию `datacenter`. Единственное допустимое значение — `datacenter`. Любое другое значение, включая `cloud`, — невозможный старт, код выхода `2`.

## <a id="authentication"></a>Authentication

По умолчанию доступ анонимный: заголовок `Authorization` не отправляется. Креды не обязательны.

Если `CONFLUENCE_AUTH_TYPE` не задан, тип выводится из кредов:

| Креды | Тип | Заголовки |
|---|---|---|
| нет username, нет password и нет token | `anonymous` | без `Authorization` |
| только token (`-t` / `CONFLUENCE_TOKEN`) | `bearer` | `Authorization: Bearer <token>` |
| username (`-u` / `CONFLUENCE_USERNAME`) и password (`-p` / `CONFLUENCE_PASSWORD`) | `basic` | HTTP Basic: `username:password` |
| username (`-u`) и token (`-t`) одновременно | невозможный старт, код `2` | Ошибка коллизии: токен `-t` используется без `-u`, для пароля используйте `-p` |
| только username (без password) | невозможный старт, код `2` | Ошибка: при указании username обязателен пароль `-p` |

Явное `CONFLUENCE_AUTH_TYPE`:

| Значение | Заголовки | Обязательные ключи |
|---|---|---|
| `anonymous` | без `Authorization` | нет |
| `bearer` | `Authorization: Bearer <token>` | token (`-t` / `CONFLUENCE_TOKEN`) |
| `basic` | HTTP Basic: `username:password` | username (`-u` / `CONFLUENCE_USERNAME`) и password (`-p` / `CONFLUENCE_PASSWORD`) |

Иное значение `CONFLUENCE_AUTH_TYPE` — невозможный старт, код выхода `2`.

CLI-флаги `-u` / `--username`, `-p` / `--password` и `-t` / `--token` перекрывают соответствующие ключи окружения на время запуска. Файл `.env` не обязателен; если используется, в git не коммитится. Токен и пароль в лог и stderr не пишутся.

## Environment keys

Имена стабильны. CLI-флаги, где они есть, перекрывают соответствующие ключи на время запуска.

| Ключ | Обязательность | Смысл |
|---|---|---|
| `CONFLUENCE_BASE_URL` | нет | база приложения; иначе выводится из входных URL |
| `CONFLUENCE_EDITION` | нет, default `datacenter` | только `datacenter` |
| `CONFLUENCE_AUTH_TYPE` | нет | `anonymous` \| `basic` \| `bearer`; иначе выводится из кредов |
| `CONFLUENCE_TOKEN` | нет | PAT (Bearer token); без него и без пароля доступ анонимный |
| `CONFLUENCE_USERNAME` | нет | username DC; вместе с password даёт `basic` |
| `CONFLUENCE_PASSWORD` | нет | пароль для basic auth; используется вместе с `CONFLUENCE_USERNAME` |
| `CONFLUENCE_VERIFY_SSL` | нет, default `true` | проверка TLS |
| `CONFLUENCE_TIMEOUT_SECONDS` | нет, default `30` | HTTP timeout, секунды |
| `CONFLUENCE_MAX_RETRIES` | нет, default `3` | ретраи на 429/502/503/504 |
| `EXPORT_OUTPUT_DIR` | нет, default `output` | корень слоёв |
| `EXPORT_INPUT_FILE` | нет, default `input/urls.txt` | входной список |
| `EXPORT_FORCE_REFRESH` | нет, default `false` | игнорировать disk-skip |
| `LOG_LEVEL` | нет, default `INFO` | уровень логов (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |

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

Проба пройдена только если ответ — успешный JSON текущего пользователя. Иной исход, в том числе HTTP `401`, `404`, HTML, тело не JSON и JSON без идентичности пользователя, — невозможный старт, код выхода `2`. В stderr — статус или краткая причина; токен, пароль и заголовок `Authorization` не пишутся.

При непройденной пробе процесс не пишет слои выгрузки и не обходит страницы. Контекст-путь инстанса по коду ответа не угадывается.

## <a id="cli"></a>CLI

CLI принимает как минимум:

| Флаг | Перекрывает | Смысл |
|---|---|---|
| `-h`, `--help` | — | показать справку и завершить работу (код `0`) |
| `-i`, `--input` | `EXPORT_INPUT_FILE` | путь к списку URL, default `input/urls.txt` |
| `-o`, `--output` | `EXPORT_OUTPUT_DIR` | корень слоёв, default `output` |
| `-u`, `--user`, `--username` | `CONFLUENCE_USERNAME` | username; вместе с `-p` / `--password` даёт basic |
| `-p`, `--password` | `CONFLUENCE_PASSWORD` | пароль для basic authentication |
| `-t`, `--token`, `--api-token` | `CONFLUENCE_TOKEN` | PAT (Bearer token); несовместим с `-u` |
| `-b`, `--base-url` | `CONFLUENCE_BASE_URL` | база приложения; иначе выводится из входных URL |
| `-v`, `--verbose` | `LOG_LEVEL=DEBUG` | подробный вывод логов |
| `--force-refresh` | `EXPORT_FORCE_REFRESH=true` | полная перевыгрузка, disk-skip выключен |

Иные флаги первой версии не добавляют out-of-scope возможностей (Cloud, запись в Confluence, descendants, RAG).

Вход в процесс — локальный CLI, который запускает однопоточный скрипт выгрузки.

## <a id="exit-codes"></a>Exit codes

| Код | Когда |
|---|---|
| `0` | старт возможен; среди обработанных страниц нет `failed` (все `ok` или `skipped`, либо вход после разбора пуст); либо вызваны `-h`/`--help`/`--version` |
| `1` | старт возможен; батч завершился; есть хотя бы одна страница `failed` |
| `2` | конфигурация, аутентификация, коллизия флагов `-u`/`-t` или иной невозможный старт: процесс не выгружает страницы |

Невозможность старта включает: `CONFLUENCE_EDITION` ≠ `datacenter`; невалидный origin или невыводимую базу; невалидный `CONFLUENCE_AUTH_TYPE`; `basic` / username без password (`-p`); одновременную передачу `-u` и `-t`; входной файл не существует; непройденную пробу идентичности при `bearer`/`basic` ([#auth-probe](#auth-probe)).

## <a id="logging"></a>Logging

Уровень задаёт `LOG_LEVEL` или флаг `-v` / `--verbose` (устанавливающий `DEBUG`). Дубликаты URL/`pageId` пишут предупреждение в лог. Каждая невалидная строка входа пишет предупреждение в лог: исходная строка и код причины из [02-input.md#rejection-reasons](./02-input.md#rejection-reasons).

На уровне DEBUG (`-v` / `--verbose`) выводятся подробные сведения о конфигурации (без секретов), отправляемых HTTP-запросах, URL и времени выполнения.

На уровне INFO консоль показывает прогресс выгрузки: старт (число страниц, число невалидных URL, пути входа и выхода, `force_refresh`); каждую страницу на выборке и на записи (порядковый номер из общего числа, идентификатор, статус `ok` / `skipped` / `failed`, заголовок если известен, причина ошибки если есть); финиш (`ok` / `failed` / `skipped` / `invalid_urls` и длительность).

Причина `failed` / `skipped` / невалидной строки видна в отчёте запуска; лог не подменяет отчёт.
