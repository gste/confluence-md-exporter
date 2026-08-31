# Fetch and disk-skip

Интеграция с Confluence Server/Data Center: REST, вложения, пропуск неизменённых страниц. Клиент только читает.

## REST base

Все API-запросы идут на `CONFLUENCE_BASE_URL` без префикса `/wiki`. Префикс `/wiki` — признак Cloud и в первой версии не используется.

Авторизация, таймаут, TLS, ретраи и запрет cookie — [01-configuration.md#http-transport](./01-configuration.md#http-transport).

## Page fetch

Страница по `page_id`:

```text
GET /rest/api/content/{page_id}?expand=body.storage,version,space,history,metadata.labels,ancestors
```

Тело запрашивается только как `body.storage`. Expand `body.view`, `body.export_view`, `body.atlas_doc_format` не используется.

Поиск по пространству и заголовку (форма display URL):

```text
GET /rest/api/content?spaceKey={space}&title={title}&type=page
```

Список вложений страницы:

```text
GET /rest/api/content/{page_id}/child/attachment
```

Пагинация — по `_links.next`, пока коллекция не исчерпана.

Ответ `404` или статус контента `trashed` — страница `skipped`, причина в отчёте. Ответ `403` — страница `failed`, причина `forbidden`, без ретраев. Иной тип контента, чем `page` — `failed`, причина `unsupported_content_type`.

## Canonical page URL

Правило `source_url` — [03-output.md#bronze](./03-output.md#bronze).

## Attachments

Скачивание через браузерный путь `/download/attachments/...` как основной способ запрещено.

Основной путь: ссылка REST `_links.download` вложения (или эквивалентный REST download по id вложения) с тем же заголовком `Authorization`, follow redirects, без cookie-сессии.

Вложение с другой страницы: скачать, если REST отдаёт его с тем же Authorization; если недоступно — в Markdown ставится текстовый плейсхолдер `[missing-attachment: <original_name>]`, в лог и в `error`/предупреждение отчёта пишется, что вложение не скачано. Страница из‑за этого не переходит в `failed`.

Бинарник пишется в `03_assets/<page_id>/<safe_filename>`. Имена и sidecar — [03-output.md#safe-filename](./03-output.md#safe-filename).

## Disk-skip

Когда `EXPORT_FORCE_REFRESH` ложно и файл `01_raw/<page_id>.json` уже есть:

1. Запросить у сервера текущий номер версии страницы (достаточно `version.number`; полное тело можно не тянуть, если инстанс отдаёт версию отдельным запросом; иначе — тот же GET content).
2. Сравнить с `version` в локальном raw.
3. Если номер совпал, для каждого вложения из локального raw (или sidecar) локальный файл существует и `file_size` совпадает с размером на диске — страницу не выгружать заново: не перезаписывать raw, не качать вложения, не перезаписывать interim и Markdown. Статус — `skipped`.

Если версия изменилась, raw отсутствует, любой учтённый ассет отсутствует или размер на диске не совпал — disk-skip не применяется, страница обрабатывается полностью.

Пробы через ETag и прочие условные GET не требуются. Кэш Prefect не заменяет это правило: пропуск смотрит на локальные файлы и версию страницы в Confluence.

`EXPORT_FORCE_REFRESH` / `--force-refresh` отключает disk-skip для всех страниц запуска.

Перезапись `manifest.json` и `run_report.json` выполняется каждый запуск и не нарушает disk-skip: запрет перезаписи относится к `03_assets/<page_id>/**` и к `04_markdown/<page_id>_*.md` пропущенной страницы.

## Isolation at fetch

Ошибка одной страницы (403, 404, битый JSON, сбой скачивания тела) не отменяет запросы остальных страниц батча. Параллелизм страниц — `EXPORT_CONCURRENCY`.
