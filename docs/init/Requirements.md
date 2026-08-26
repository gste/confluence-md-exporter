# ТЕХНИЧЕСКОЕ ЗАДАНИЕ
## Подготовка SDD-ready спецификации проекта `confluence-md-exporter`

**Версия ТЗ:** 1.1  
**Оркестратор:** Prefect 3.x  
**Назначение документа:** исходное задание для ИИ-агента, который должен выпустить SDD. SDD должен быть достаточно полным, чтобы второй (локальный) агент реализовал проект без дополнительных уточнений продукта.

---

## 0. Что должен сделать агент по этому ТЗ

Агент **не пишет production-код** на этом шаге.

Агент обязан выпустить один артефакт:

`SDD.md` — System Design Document проекта `confluence-md-exporter`.

SDD считается принятым только если по нему можно однозначно реализовать:

- клиент Confluence REST (Cloud и Server/DC);
- выгрузку страниц по списку URL;
- выгрузку вложений и связанных бинарников;
- трансформацию Storage Format → Markdown + YAML frontmatter;
- Prefect 3.x flow/tasks с ретраями, изоляцией ошибок, дисковым идемпотентным слоем и артефактами UI;
- unit-тесты на резолвер URL и макросы.

Запрещено оставлять в SDD формулировки вида «уточнить позже», «на усмотрение разработчика», «примерно так». Если есть развилка — агент фиксирует выбранное решение и причину.

Язык SDD: русский. Идентификаторы кода, имена файлов, ключи YAML, имена тасок — английский.

---

## 1. Оценка исходного черновика ТЗ (обязательный контекст для автора SDD)

Черновик в целом правильный по форме (bronze/silver/gold, Prefect tasks, frontmatter, таблица макросов). Его нельзя копировать как есть. Автор SDD обязан устранить следующие дефекты.

### 1.1. Критические дефекты

1. **Сломанные относительные пути медиа.**  
   Каталог на диске: `data/03_assets/<page_id>/file`.  
   В таблице трансформации ссылки указаны как `../assets/<page_id>/file`.  
   Из `data/04_markdown/` корректный относительный путь: `../03_assets/<page_id>/file`.  
   SDD обязан выбрать **одну** схему путей и использовать её везде (layout, макросы, тесты, примеры).

2. **Prefect cache ≠ идемпотентность на диске.**  
   `cache_policy=TASK_SOURCE + INPUTS` кэширует результат таски в Prefect result store. Это не заменяет проверку «файл уже есть и version страницы не изменилась».  
   Для сетевых тасок нужна **явная disk-skip политика**: читать `version.number` / `history.lastUpdated` из raw JSON и пропускать download, если локальный артефакт актуален. Prefect cache — дополнительный слой, не основной.

3. **Скачивание вложений через UI-URL часто даёт 401.**  
   Путь `/download/attachments/...` — браузерный. Для автоматизации использовать REST:  
   - Cloud/DC v1: `GET /rest/api/content/{id}/child/attachment` + download по attachment id;  
   - Cloud v2: `GET /wiki/api/v2/pages/{id}/attachments`.  
   Клиент обязан ходить с тем же Authorization, follow redirects, не полагаться на cookie-сессию.

4. **Auth-модель неполная.**  
   Недостаточно `CONFLUENCE_TOKEN` без username для BASIC.  
   Обязательные режимы:
   - Cloud BASIC: email + API token;
   - Server/DC BEARER: PAT;
   - Server/DC BASIC: username + password/token.  
   Нужны `CONFLUENCE_USERNAME` (опционально) и `CONFLUENCE_EDITION=cloud|datacenter`.

5. **Смешение Cloud и Server API без адаптера.**  
   Base path, pagination, типы id отличаются. SDD обязан описать тонкий адаптер (`ConfluenceClient` + strategy `CloudApi` / `DataCenterApi`), а не один набор URL.

### 1.2. Существенные пробелы

6. Нет контракта на **неизвестные макросы** (toc, jira, include, children, excerpt, widget, roadmap, layout/column, mentions). Нужен fallback: HTML-комментарий `<!-- unsupported-macro: name -->` + сохранение текстового содержимого, без падения пайплайна.

7. Нет правил **внутренних ссылок** Confluence (`ri:page`, `ac:link`). Решение по умолчанию: сохранять абсолютный `source_url` страницы-цели, если цель не входит в текущий батч; если входит — относительная ссылка на локальный `.md`.

8. Нет **каталога выгрузки** (`data/04_markdown/manifest.json`) — обязателен для последующих AI/RAG пайплайнов.

9. Нет **rate limit / backoff** (429, 503, Retry-After).

10. Нет правил **slug / безопасных имён файлов** (кириллица, `/ \ : * ? " < > |`, длина).

11. Нет CLI-контракта и кодов выхода.

12. Нет явной границы MVP vs out of scope (потомки страниц, комментарии, PDF-export, запись обратно в Confluence).

13. Смешение `cache_key_fn` и `cache_policy` без указания Prefect 3 API. В SDD использовать только Prefect 3: `from prefect.cache_policies import INPUTS, TASK_SOURCE` и `create_markdown_artifact` из `prefect.artifacts`.

14. Не зафиксированы Python, пакетный менеджер, линтеры.

### 1.3. Что из черновика сохранить

- Слои `01_raw / 02_interim / 03_assets / 04_markdown`.
- Список URL как единственный вход MVP.
- YAML frontmatter как обязательный контракт Gold-слоя.
- Изоляцию ошибок по страницам.
- Prefect artifacts для UI.
- Обработку code / plantuml / drawio / panels / images / attachments / expand / status / task-list.

---

## 2. Цель продукта

Модульный CLI + Prefect 3.x pipeline, который:

1. Читает список URL страниц Confluence.
2. Выгружает raw JSON (metadata + `body.storage`) в bronze-слой.
3. Выгружает вложения и встроенные медиа в media-слой.
4. Нормализует Storage Format (макросы `ac:*`, `ri:*`) в промежуточный HTML.
5. Собирает GFM Markdown с YAML frontmatter, локальными ссылками на медиа и манифестом батча.
6. Готовит выход, пригодный для Obsidian и последующих RAG/LLM пайплайнов (стабильные id, source_url, labels, путь к md и assets).

Не цели MVP: двусторонняя синхронизация, UI, Kubernetes deploy, эмбеддинги, векторная БД.

---

## 3. Границы MVP

### In scope

- Confluence Cloud и Confluence Server/Data Center.
- Страницы типа `page` (не blogpost, не whiteboards, не databases).
- Вход: `input/urls.txt`.
- Выход: четыре слоя + `manifest.json` + `run_report.json`.
- Макросы из раздела 6 + безопасный fallback.
- Prefect flow, запускаемый локально (`python -m src` или `prefect flow run` / прямой вызов `@flow`).
- Unit-тесты без живого Confluence (фикстуры XML/JSON).

### Out of scope (явно запрещено реализовывать в первой версии)

- Рекурсивная выгрузка descendants, если URL не перечислен (можно заложить расширение в SDD, но не в MVP-контракт).
- Комментарии, likes, restrictions, page history dump всех версий.
- Запись/обновление страниц в Confluence.
- Рендер PlantUML/Draw.io в растр собственным движком.
- Docker/K8s/CI production deploy (достаточно описания, как запустить локально).

---

## 4. Входы, конфигурация, выходы

### 4.1. Входной файл

`input/urls.txt`

- UTF-8.
- Одна запись на строку.
- Игнорировать пустые строки и строки, начинающиеся с `#`.
- Допустимые формы URL (после нормализации base):
  - `.../pages/viewpage.action?pageId=123456`
  - `.../pages/viewpage.action?pageId=123456&src=...`
  - `.../display/SPACE/Page+Title`
  - `.../wiki/spaces/SPACE/pages/123456/Title`
  - `.../wiki/spaces/~user/pages/123456/Title`
  - голый numeric `pageId` (опционально, если строка состоит только из цифр).
- Дубликаты URL/pageId схлопываются с WARNING в лог.

Невалидный URL не валит весь батч: попадает в `run_report.json` со статусом `invalid_url`.

### 4.2. Переменные окружения

Файл `.env.example` обязан содержать все ключи. Валидация через `pydantic-settings`.

| Ключ | Обязательность | Описание |
|---|---|---|
| `CONFLUENCE_BASE_URL` | да | Origin без хвоста `/wiki`, без завершающего `/` |
| `CONFLUENCE_EDITION` | да | `cloud` \| `datacenter` |
| `CONFLUENCE_AUTH_TYPE` | да | `basic` \| `bearer` |
| `CONFLUENCE_TOKEN` | да | API token или PAT или password |
| `CONFLUENCE_USERNAME` | да, если `basic` | email (Cloud) или username (DC) |
| `CONFLUENCE_VERIFY_SSL` | нет, default `true` | `true`/`false` |
| `CONFLUENCE_TIMEOUT_SECONDS` | нет, default `30` | HTTP timeout |
| `CONFLUENCE_MAX_RETRIES` | нет, default `3` | HTTP retries на 429/5xx |
| `EXPORT_OUTPUT_DIR` | нет, default `data` | корень слоёв |
| `EXPORT_INPUT_FILE` | нет, default `input/urls.txt` | |
| `EXPORT_CONCURRENCY` | нет, default `4` | параллелизм страниц |
| `EXPORT_FORCE_REFRESH` | нет, default `false` | игнорировать disk-skip |
| `LOG_LEVEL` | нет, default `INFO` | |

Запрещено коммитить `.env`.

### 4.3. Выходной layout (канонический)

```text
data/
├── 01_raw/<page_id>.json
├── 02_interim/<page_id>.html
├── 03_assets/<page_id>/<safe_filename>
├── 04_markdown/<page_id>_<slug>.md
├── 04_markdown/manifest.json
└── run_report.json
```

Канонические относительные ссылки из Markdown:

```text
../03_assets/<page_id>/<safe_filename>
```

`slug`: нижний регистр, NFKC, пробелы и пунктуация → `-`, только `[a-z0-9-]`, кириллица транслитерируется (алгоритм указать в SDD, например `unidecode` или явное отображение), обрезка до 60 символов, пустой slug → `page`.

Имена вложений: сохранить исходное имя, если оно безопасно для Windows/POSIX; иначе заменить опасные символы на `_` и вести карту `original → safe` в raw sidecar.

---

## 5. Контракты данных

### 5.1. Bronze `01_raw/<page_id>.json`

Минимальный JSON, который обязан сохранить клиент (поля можно расширять, но эти ключи стабильны):

```json
{
  "page_id": "109847231",
  "edition": "datacenter",
  "title": "Архитектура интеграционного шлюза",
  "space_key": "ARCH",
  "version": 5,
  "status": "current",
  "created_by": "v.petrov",
  "updated_at": "2026-04-12T14:32:00Z",
  "source_url": "https://confluence.example/pages/viewpage.action?pageId=109847231",
  "labels": ["kafka", "architecture"],
  "ancestors": [{"id": "1", "title": "Главная"}, {"id": "2", "title": "Проекты 2026"}],
  "body_storage": "<ac:...>",
  "attachments": [
    {
      "id": "att123",
      "title": "ArchSchema.png",
      "media_type": "image/png",
      "file_size": 18420,
      "download_api_path": "/rest/api/content/109847231/child/attachment/att123/download"
    }
  ],
  "fetched_at": "2026-08-26T10:00:00Z"
}
```

`body_storage` — именно Storage Format, не `view` и не `export_view`.

### 5.2. Gold frontmatter

Обязательные ключи:

```yaml
---
id: "109847231"
title: "Архитектура интеграционного шлюза"
space_key: "ARCH"
version: 5
status: current
created_by: "v.petrov"
updated_at: "2026-04-12T14:32:00Z"
source_url: "https://confluence.example/pages/viewpage.action?pageId=109847231"
labels:
  - kafka
breadcrumbs:
  - "Главная"
  - "Проекты 2026"
  - "Архитектура интеграционного шлюза"
attachments_count: 3
unsupported_macros:
  - toc
---
```

`id` всегда строка. `breadcrumbs` = titles ancestors + текущий title.

### 5.3. `manifest.json`

Массив объектов:

- `id`, `title`, `space_key`, `version`, `source_url`, `md_path`, `assets_dir`, `labels`, `status` (`ok` | `failed` | `skipped`), `error` (nullable).

### 5.4. `run_report.json`

- `started_at`, `finished_at`, `pages_total`, `ok`, `failed`, `skipped`, `invalid_urls`, `force_refresh`, список ошибок по `page_id`.

---

## 6. Правила трансформации контента

Парсер работает по Storage XHTML с namespaces `ac:` и `ri:`. Рекомендуемый стек: `lxml` + `BeautifulSoup("lxml")` либо чистый `lxml`. Решение фиксируется в SDD.

Порядок обработки **строго**:

1. Собрать карту вложений страницы (и `ri:page` вложений с другой страницы — если download доступен; иначе placeholder + WARNING).
2. Заменить макросы и `ac:image` на промежуточный HTML.
3. Заменить внутренние ссылки.
4. Прогнать clean HTML → GFM.
5. Инжектить frontmatter.

### 6.1. Обязательные макросы

| Источник | Правило |
|---|---|
| HTML `p,h1-h6,ul,ol,li,table,thead,tbody,tr,th,td,em,strong,code,pre,br,hr,a` | GFM / ATX / pipe-tables |
| `ac:structured-macro[ac:name=code]` | fenced block; language из `language`/`lang`; тело из `ac:plain-text-body` CDATA; если language пустой — `text` |
| `plantuml` / `plantumlcloud` | fenced ` ```plantuml `; не рендерить картинку |
| `drawio` / `draw.io` | найти preview (`<diagramName>.png/.svg`) среди attachments; вставить image link; если есть `.drawio`/`.xml` — вторая markdown-ссылка `[source](...)` |
| `info`, `note`, `panel` | `> [!NOTE]` + содержимое rich-text |
| `warning`, `error` | `> [!WARNING]` |
| `tip`, `success` | `> [!TIP]` |
| `ac:image` + `ri:attachment` | local image `![alt](../03_assets/<page_id>/<file>)`; alt = filename или `ac:alt-text` |
| `ac:image` + `ri:url` | оставить внешний URL как есть |
| `ri:attachment` в ссылке / макросе files | local file link |
| `expand` | `<details><summary>title</summary>…</details>` |
| `status` | `` `TITLE` `` ; цвет игнорировать в MVP |
| `ac:task-list` / `ac:task` | `- [x]` / `- [ ]` по `ac:task-status` |
| `ac:emoticon` | `:smile:` или unicode fallback, список в SDD |
| `ac:link` + `ri:page` | см. 6.2 |
| `ac:link` + `ri:user` | `@displayName` или `@accountId` |
| `time` / `ac:structured-macro[ac:name=date]` | ISO-дата текстом |

### 6.2. Внутренние ссылки

- Если `ri:page` резолвится в `page_id` текущего батча → `[title](./<page_id>_<slug>.md)`.
- Иначе → абсолютный URL вида `{BASE}/pages/viewpage.action?pageId={id}` или Cloud webui из API.
- Якоря (`ri:page` + anchor) сохранять суффиксом `#anchor`, если известен.

### 6.3. Fallback неизвестного макроса

```html
<!-- unsupported-macro: jira -->
<p>…извлечённый текст rich-text-body / plain-text-body…</p>
```

Имя макроса добавить в `unsupported_macros` frontmatter. Пайплайн не падает.

### 6.4. Краевые случаи (обязаны быть в SDD и в тестах)

- Пустое тело страницы.
- Макрос без body.
- CDATA с тройными бэктиками внутри code-блока (экранирование fence).
- Одинаковые filename у двух attachments разных версий — брать current.
- Вложение на другой странице (`ri:attachment ri:content-title` / `ri:page`).
- Таблица с colspan — упростить до GFM без объединения, не падать.
- HTML-entities в title.
- Страница `status=trashed` или 404 — запись в report, skip.
- 403 — report `forbidden`, не ретраить бесконечно.

---

## 7. Клиент Confluence

### 7.1. Транспорт

- `httpx.Client` (sync) в MVP. Async допустим только если весь flow согласован; не смешивать.
- Headers: `Accept: application/json`, `X-Atlassian-Token: no-check` для DC.
- SSL: `verify` из настроек.
- Retries: 429/502/503/504, экспоненциальный backoff, уважать `Retry-After`.
- Timeout connect/read из настроек.

### 7.2. Auth

- `basic`: `httpx.BasicAuth(username, token)`.
- `bearer`: `Authorization: Bearer {token}`.
- Запрещено логировать token.

### 7.3. Операции клиента

Интерфейс (имена можно уточнить, семантика нет):

- `resolve_url(url) -> PageTarget`
- `get_page(page_id) -> raw dict`
- `list_attachments(page_id) -> list[Attachment]`
- `download_attachment(attachment, dest_path) -> Path`
- `get_labels(page_id) -> list[str]`
- `get_ancestors(page_id) -> list[Ancestor]`

Expand для DC/Cloud v1 минимум:  
`body.storage,version,space,history,history.lastUpdated,ancestors,metadata.labels`.

Для Cloud v2 — эквивалентные query params; маппинг в единый raw JSON из 5.1 делается в адаптере.

### 7.4. Disk-skip

Перед `get_page`, если `EXPORT_FORCE_REFRESH=false` и существует `01_raw/<id>.json`:

1. Выполнить лёгкий запрос метаданных version (без body) либо сравнить ETag/version, если дешево.
2. Если version совпал — не перезаписывать raw и не качать attachments заново, если все файлы на месте и size совпадает.
3. Иначе — полная перевыгрузка страницы и ассетов.

SDD обязан расписать точный алгоритм (какие запросы, какие поля).

---

## 8. Prefect 3.x

### 8.1. Граф

```text
export_confluence_batch (flow)
  parse_and_validate_urls (task) -> list[PageTarget]
  for each target (concurrency = EXPORT_CONCURRENCY):
    process_page (task or subflow)  # изоляция ошибок
      fetch_page_raw
      sync_page_assets
      transform_storage_to_clean_html
      render_final_markdown
  write_manifest_and_report (task)
```

Предпочтительная изоляция: отдельный `@task process_page` с `return_state=True` на уровне map/loop **или** внутренний try/except, который возвращает `PageResult(status=failed)`. Весь батч не падает из-за одной страницы. Flow завершается успешно, если обработан ≥1 ok; если все failed — flow failed.

### 8.2. Политики тасок

| Task | retries | retry_delay | persist | cache |
|---|---|---|---|---|
| parse_and_validate_urls | 0 | — | нет | нет |
| fetch_page_raw | 3 | 5, 15, 45 | да | INPUTS+TASK_SOURCE, но skip логика на диске первична |
| sync_page_assets | 2 | 5, 20 | да | аналогично |
| transform_* / render_* | 1 | 5 | нет необходимости | нет (детерминированы от raw) |
| write_manifest | 0 | — | нет | нет |

Не передавать в task input живой `httpx.Client` (не сериализуется для cache). Клиент создавать внутри task или через тонкую фабрику.

### 8.3. Artifacts

После успешного `render_final_markdown` вызывать:

```python
from prefect.artifacts import create_markdown_artifact
create_markdown_artifact(
    key=f"page-{page_id}",
    markdown=preview,  # title + frontmatter + first 500 chars
    description=title,
)
```

Ключ — slug-safe `[a-z0-9-]+`.

Логи только через `get_run_logger()`.

### 8.4. CLI

```text
python -m src.flows.export_flow
python -m src.flows.export_flow --input input/urls.txt --output data --force-refresh
```

Коды выхода: `0` все ok/skipped; `1` частичный failure; `2` конфигурация/auth/невозможный старт.

---

## 9. Структура репозитория (канон)

```text
confluence-md-exporter/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── input/urls.txt
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── models.py
│   ├── logging.py
│   ├── client/
│   │   ├── confluence.py
│   │   ├── cloud.py
│   │   ├── datacenter.py
│   │   └── resolver.py
│   ├── transformers/
│   │   ├── macro_handlers.py
│   │   ├── html_cleaner.py
│   │   └── md_converter.py
│   └── flows/
│       ├── tasks.py
│       └── export_flow.py
└── tests/
    ├── test_url_resolver.py
    ├── test_macro_handlers.py
    ├── test_md_converter.py
    ├── test_disk_skip.py
    └── fixtures/
        ├── sample_storage.xml
        ├── sample_page.json
        └── urls.txt
```

Пакетный менеджер: `uv` + `pyproject.toml`. Python `>=3.11,<3.14`.

Зависимости минимум: `prefect>=3,<4`, `httpx`, `pydantic>=2`, `pydantic-settings`, `beautifulsoup4`, `lxml`, `markdownify`, `python-dotenv`, `unidecode` (если выбран для slug).

Dev: `pytest`, `ruff`, `mypy`.

---

## 10. Нефункциональные требования

- Идемпотентность: повторный запуск без `--force-refresh` не портит актуальные файлы.
- Никаких секретов в логах и Prefect artifacts.
- Типизация: публичные функции с аннотациями, mypy strict по возможности, не ниже `--check-untyped-defs`.
- Ruff default + py311.
- Unit-тесты покрывают каждый макрос из 6.1 и все URL-паттерны из 4.1.
- Фикстуры не содержат реальных корпоративных данных.

---

## 11. Обязательная структура SDD.md

Автор SDD заполняет разделы ниже **полностью**. Каждый раздел содержит конкретные типы, сигнатуры, алгоритмы и примеры. Псевдокод допустим, «реализуем как удобно» — нет.

1. **Контекст и цели** — 1 страница.
2. **C4 / компонентная схема** — клиент, transformers, flows, filesystem; текстовый diagram ok.
3. **Data flow** — от urls.txt до manifest.json, включая disk-skip ветки.
4. **Pydantic-модели** — `Settings`, `PageTarget`, `PageRaw`, `Attachment`, `PageResult`, `ManifestItem`, enum макросов.
5. **URL resolver** — таблица regex/парсеров и тесты-примеры.
6. **API adapter Cloud vs DC** — конкретные endpoints и маппинг в `PageRaw`.
7. **Asset download protocol** — какой URL, headers, запись файла, карта имён.
8. **Макро-движок** — для каждого макроса: поиск узла, извлечение параметров, выходной HTML/MD, edge cases.
9. **HTML → Markdown** — библиотека, настройки markdownify, post-process.
10. **Prefect graph** — сигнатуры `@flow`/`@task`, параметры декораторов, concurrency, failure policy, artifacts.
11. **CLI и конфигурация**.
12. **Стратегия тестов** — список тест-кейсов, содержимое фикстур (сокращённый XML).
13. **План реализации файлов** — порядок создания, зависимости, Definition of Done по файлу.
14. **Риски и явные решения** — таблица «риск → выбранное решение».
15. **Промпт для агента-реализатора** — самодостаточный prompt на 1–2 экрана, который ссылается на этот SDD как единственный источник правды.

---

## 12. Критерии приёмки SDD

SDD принимается, если:

- [ ] Нет противоречий в путях ассетов.
- [ ] Auth и edition разведены.
- [ ] Download attachments идёт через REST, не через UI path как основной.
- [ ] Disk-skip описан пошагово и не подменён одним только Prefect cache.
- [ ] Каждый макрос из 6.1 имеет алгоритм и fixture-пример.
- [ ] Есть контракт неизвестных макросов, 404/403, пустых страниц.
- [ ] Есть `manifest.json` и `run_report.json`.
- [ ] Prefect 3 API указан корректно (`cache_policies`, `create_markdown_artifact`, `get_run_logger`).
- [ ] Out of scope не просачивается в план реализации MVP.
- [ ] Раздел 15 содержит prompt, по которому локальный агент может сразу писать код.

---

## 13. Промпт для агента — автора SDD

Скопировать агенту вместе с полным текстом этого ТЗ:

```text
Ты — ведущий Python/Data-инженер. Тебе дано ТЗ v1.1 проекта confluence-md-exporter.

Задача: написать только файл SDD.md по разделу 11 ТЗ. Код репозитория не создавать.

Соблюдай все исправления из раздела 1 ТЗ. Не копируй дефекты исходного черновика (неверные пути ../assets, BASIC без username, UI download URL, cache Prefect вместо disk-skip).

Требования к качеству:
- однозначные решения вместо альтернатив;
- сигнатуры функций и поля моделей — полные;
- для каждого макроса — алгоритм и крошечный XML-пример;
- Prefect только 3.x;
- SDD должен быть единственным источником правды для следующего агента-реализатора.

Проверь себя чеклистом раздела 12 перед финальной выдачей.
```
