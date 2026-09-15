# Specification — `confluence-md-exporter`

Единственный закон реализации. Код, тесты и задачи читают только этот пакет: не чат, не Init Requirements, не архив, не текст ADR сами по себе. Принятый ADR обязан быть отражён здесь императивом.

| Параметр | Значение |
|---|---|
| Статус пакета | `draft` — ожидает приёмки человеком |
| Стадия репозитория | [`docs/process/STATUS.md`](../process/STATUS.md) |
| Human-gated зоны | [00-context.md#human-gated-areas](./00-context.md#human-gated-areas) |
| Обязательства по тестам | [07-testing.md](./07-testing.md) |

Монолита `docs/spec/SDD.md` нет. Процесс работы — [`AGENTS.md`](../../AGENTS.md) и [`docs/process/`](../process/README.md).

## TOC

| Модуль | Назначение |
|---|---|
| [00-context.md](./00-context.md) | цели, акторы, in/out of scope, внешние ограничения, human-gated зоны |
| [01-configuration.md](./01-configuration.md) | Python/uv, env, auth, HTTP, CLI, коды выхода |
| [02-input.md](./02-input.md) | входной файл, допустимые URL, дедупликация, невалидные строки |
| [03-output.md](./03-output.md) | layout слоёв, bronze/gold, manifest, report, slug, безопасные имена |
| [04-fetch.md](./04-fetch.md) | REST DC, вложения, disk-skip, изоляция на выгрузке |
| [05-transform.md](./05-transform.md) | Storage Format → GFM, известные макросы, fallback, краевые случаи |
| [06-orchestration.md](./06-orchestration.md) | однопоточный запуск, изоляция батча, прогресс в консоли, read-only |
| [07-testing.md](./07-testing.md) | обязательное покрытие тестами и критерии приёмки продукта |

## Review tour

Читать в этом порядке. Пакет принимается целиком из этого файла; второго входа нет.

1. **00-context** — границы первой версии: DC-only, только `page`, нет Cloud, нет записи в Confluence, нет RAG/UI/деплоя. Сверить human-gated таблицу.
2. **01-configuration** — ключи окружения, `CONFLUENCE_EDITION=datacenter`, auth basic/bearer, коды `0`/`1`/`2`.
3. **02-input** — шесть форм URL и только они; tiny-link и прочее → `invalid_urls`, не манифест.
4. **03-output** — дерево `01_raw`…`04_markdown`, канон `../03_assets/...`, обязательные ключи frontmatter/manifest/report, таблица транслитерации slug.
5. **04-fetch** — REST без `/wiki`, запрет UI-download, disk-skip по `version` + size ассетов.
6. **05-transform** — таблица известных конструкций и HTML-комментарий fallback; страница не `failed` из‑за неизвестного макроса.
7. **06-orchestration** — батч не падает на одной странице; все-`skipped` — успешный запуск; прогресс в консоли.
8. **07-testing** — фикстуры без сети покрывают каждый URL-паттерн и каждую конструкцию; секретов в фикстурах нет.

## Coverage

Каждое требование Init отражено ниже. После приёмки пакета этот блок можно перенести в `docs/archive/`.

| Init | Куда |
|---|---|
| IR-P-1, IR-P-2, IR-P-3 | [00-context.md#problem](./00-context.md#problem), [00-context.md#what-the-system-does](./00-context.md#what-the-system-does) |
| IR-A-1, IR-A-2, IR-A-3, IR-A-4 | [00-context.md#actors](./00-context.md#actors) |
| IR-G-1 … IR-G-6 | [00-context.md#goals](./00-context.md#goals) |
| IR-NG-1 … IR-NG-8, IR-OUT-1 … IR-OUT-5 | [00-context.md#out-of-scope](./00-context.md#out-of-scope) |
| IR-IN-1, IR-IN-2, IR-IN-4, IR-IN-5, IR-IN-6, IR-IN-7, IR-IN-8 | [00-context.md#in-scope](./00-context.md#in-scope) и модули 02–06 |
| IR-IN-3, IR-D-1 | [02-input.md](./02-input.md) |
| IR-X-1, IR-X-2, IR-X-3, IR-X-4, IR-X-6, IR-X-9, IR-X-10 | [01-configuration.md](./01-configuration.md) |
| IR-X-5 | [04-fetch.md#attachments](./04-fetch.md#attachments) |
| IR-X-7, IR-D-2, IR-D-3, IR-D-4, IR-D-8, IR-D-9, IR-D-10 | [03-output.md](./03-output.md) |
| IR-X-8, IR-ACC-6 | [07-testing.md#secrets](./07-testing.md#secrets) |
| IR-D-5, IR-D-6, IR-D-7, IR-IN-8 | [05-transform.md](./05-transform.md) |
| IR-D-11 | [04-fetch.md#disk-skip](./04-fetch.md#disk-skip) |
| IR-D-12, IR-G-4, IR-G-6 | [06-orchestration.md](./06-orchestration.md) |
| IR-ACC-1 … IR-ACC-5 | [07-testing.md#product-acceptance](./07-testing.md#product-acceptance) |

## Deviations from Init

Init открытых развилок не содержал. Ниже — уточнения, без которых императив был бы неполным.

| Тема | Что зафиксировано | Зачем |
|---|---|---|
| IR-D-8 slug | таблица кириллицы в [03-output.md#cyrillic-transliteration-table](./03-output.md#cyrillic-transliteration-table) | Init делегировал выбор алгоритма спеке |
| IR-D-3 sidecar | файл `01_raw/<page_id>.assets.json` | Init требовал карту «рядом с raw», не имя файла |
| IR-D-10 список ошибок | ключ `errors` | Init задал состав, не имя поля |
| IR-D-12 vs IR-G-3 | запуск из одних `skipped` успешен, код `0` | иначе повторная актуализация без изменений была бы провалом |
| IR-D-5 emoticon | токен `:name:` из `ac:name` | Init требовал «короткий текстовый эквивалент» без таблицы |
| IR-D-3 `source_url` | `webui` относительно base, иначе `viewpage.action?pageId=` | Init требовал стабильный URL, не шаблон |
| IR-D-9 `id` | в манифесте допускается `null`, если display-URL не резолвился в id | иначе 404 по title некуда записать |
| IR-X-10 CLI | флаги `--input`, `--output`, `--force-refresh` | Init задал смысл, не имена флагов |

Сознательного сужения или расширения scope нет: Cloud, UI, RAG, запись в Confluence остаются out of scope.

## OPEN DECISION

Нет. Черновики ADR не заводились: принятых ADR нет, развилок, которые нельзя было закрыть уточнением контракта, нет.

Модуль с пометкой `OPEN DECISION` не является законом для реализации, пока ADR не принят и не отражён императивом. Таких модулей в пакете нет.
