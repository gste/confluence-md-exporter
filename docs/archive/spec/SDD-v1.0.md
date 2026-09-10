# SDD — `confluence-md-exporter`

| Параметр | Значение |
|---|---|
| Документ | Specification (SDD) проекта `confluence-md-exporter` |
| Версия | 1.0 |
| Статус | `draft` — ожидает приёмки человеком; стадия репозитория объявлена в `docs/process/STATUS.md` |
| Место в цепочке закона | Init Requirements + ADR → **этот пакет** → задачи `docs/todo/` → реализация |
| Оркестратор | Prefect 3.x (`prefect>=3.1,<4`) |
| Python | `>=3.11,<3.14` |
| Пакетный менеджер | `uv` |
| Аудитория | ИИ-агенты (Implementer, Planner, Auditor, Spec editor) и ревьюер-человек |

`docs/spec/**` — **единственный закон реализации**. Требования берутся только отсюда: ни чат, ни `init/Requirements.md`, ни `docs/archive/**`, ни текст ADR сами по себе законом не являются. После приёмки пакета Init Requirements становятся необязывающими (`docs/process/workflow.md`, раздел Bootstrapping), поэтому текст ниже самодостаточен и нигде не ссылается на них как на источник нормы. Расхождения с Init Requirements, важные для приёмки, перечислены в §17.

Все развилки закрыты: если реализатору кажется, что есть выбор, — выбора нет, действует буква этого документа. Расхождение кода со спекой — дефект кода, он правится через `spec-patch`, а не «фиксом только в коде».

**Порядок чтения.** Implementer читает файл задачи из `docs/todo/<epic>/` и только те секции, на которые задача ссылается; целиком документ читают Planner и Auditor. До завершения нарезки на модули `docs/spec/NN-*.md` задачи ссылаются на номера разделов этого файла.

Человеко-гейтные зоны — §1.6. Обязательные тесты — §12. Правила работы — `AGENTS.md` и `docs/process/**`.

---

## 0. Соглашения документа (нормативные константы)

Эти константы обязаны существовать в коде как модульные константы и использоваться везде (макросы, тесты, примеры). Дублирование строковых литералов запрещено.

### 0.1. Пути и layout

```text
data/                                  # EXPORT_OUTPUT_DIR, default "data"
├── 01_raw/<page_id>.json              # bronze: PageRaw
├── 01_raw/<page_id>.assets.json       # bronze sidecar: карта original -> safe (AssetSidecar)
├── 01_raw/<page_id>.links.json        # bronze sidecar: индекс внутренних ссылок (LinkIndex)
├── 02_interim/<page_id>.html          # silver: clean HTML
├── 03_assets/<page_id>/<safe_filename># media
├── 04_markdown/<page_id>_<slug>.md    # gold
├── 04_markdown/manifest.json          # каталог батча
└── run_report.json                    # отчёт запуска
```

**Единственная каноническая форма ссылки на медиа из Markdown:**

```text
../03_assets/<page_id>/<safe_filename>
```

Обоснование: файл Markdown лежит в `../../../output/04_markdown/`, ассеты — в `../../../output/03_assets/`; относительный путь от каталога md-файла — ровно `../03_assets/...`. Форма `../assets/...` из исходного черновика **запрещена** и не должна появляться ни в коде, ни в тестах, ни в примерах. В коде путь строится единственной функцией `asset_relative_path(page_id, safe_filename)` (см. §7.6).

Два sidecar-файла (`*.assets.json`, `*.links.json`) — нормативная часть bronze-слоя: карта `original → safe` обязательна (§7.5), индекс внутренних ссылок нужен, чтобы трансформация оставалась без сети (§6.7). Они лежат рядом с `01_raw/<page_id>.json` и никогда не участвуют в frontmatter.

### 0.2. XML namespaces Storage Format

```python
AC_NS = "http://www.atlassian.com/schema/confluence/4/ac/"
RI_NS = "http://www.atlassian.com/schema/confluence/4/ri/"
AT_NS = "http://www.atlassian.com/schema/confluence/4/at/"
NSMAP = {"ac": AC_NS, "ri": RI_NS, "at": AT_NS}
```

Confluence отдаёт `body.storage.value` как **фрагмент** XHTML без объявления префиксов. Парсер обязан обернуть фрагмент в синтетический корень с этими объявлениями (см. §8.1). URI выбраны нами и используются только внутри процесса; их значения не влияют на результат, но обязаны быть едиными во всём коде и фикстурах.

### 0.3. Служебные плейсхолдеры

| Плейсхолдер | Где живёт | Кто снимает |
|---|---|---|
| `cmex://page/<page_id>` | href в interim HTML и в промежуточном Markdown | финальный проход `fixup_internal_links` в `write_manifest_and_report` (§10.6) |
| `@@CMEX_DEFER_<n>@@` | текстовый узел interim HTML | post-process конвертера Markdown (§9.4) |

Регексп плейсхолдера deferred-блока: `r"@@CMEX_DEFER_(\d+)@@"`. Ничего другого в качестве плейсхолдеров не используется.

### 0.4. Терминология статусов

| Статус | Смысл |
|---|---|
| `ok` | страница выгружена и отрендерена в этом запуске |
| `skipped` | версия на сервере совпала с локальной и все артефакты на месте (disk-skip), либо страница `trashed`/`archived`/404 |
| `failed` | страница не обработана из-за ошибки (сеть, 403, парсинг, IO) |
| `invalid_url` | строка входного файла не распознана как ссылка на страницу (в `manifest.json` не попадает, только в `run_report.json`) |

---

## 1. Контекст и цели

### 1.1. Проблема

Корпоративная документация живёт в Confluence (Cloud и Server/Data Center). Для Obsidian-хранилища и для RAG/LLM-пайплайнов нужен воспроизводимый экспорт: Markdown с устойчивыми идентификаторами, локальными медиа и машинно-читаемым каталогом. Ручной экспорт Confluence (PDF/HTML/Word) непригоден: теряет макросы, ломает ссылки на вложения, не даёт метаданных и не идемпотентен.

### 1.2. Что делает система

CLI + Prefect 3.x pipeline `confluence-md-exporter`:

1. читает список URL страниц из `input/urls.txt`;
2. резолвит URL в `page_id` (несколько форм URL, обе редакции Confluence);
3. выгружает raw JSON (`metadata` + `body.storage`) в bronze-слой `../../../output/01_raw/`;
4. выгружает вложения и встроенные медиа через REST в `../../../output/03_assets/<page_id>/`;
5. нормализует Storage Format (`ac:*`, `ri:*`) в clean HTML `../../../output/02_interim/`;
6. собирает GFM Markdown с обязательным YAML frontmatter в `../../../output/04_markdown/`;
7. пишет `manifest.json` и `run_report.json`, публикует Prefect-артефакты в UI.

### 1.3. Цели (измеримые)

| Цель | Критерий приёмки |
|---|---|
| Идемпотентность | повторный запуск без `--force-refresh` на неизменённых страницах даёт `skipped` для всех страниц, ни один байт в `03_assets/` и `04_markdown/` не перезаписан (проверяется по mtime) |
| Изоляция ошибок | одна страница с 403/404/битым XML не мешает остальным; батч завершается, отчёт содержит причину |
| Полнота метаданных | frontmatter содержит все обязательные ключи §4.7 для 100% успешных страниц |
| Работоспособность медиа-ссылок | все ссылки вида `../03_assets/...` из сгенерированных md разрешаются в существующий файл (проверяется тестом `test_manifest_links`) |
| Переносимость | одна и та же кодовая база работает против Cloud и DC, разница инкапсулирована в двух классах-стратегиях |
| Прозрачность | для каждой страницы в Prefect UI есть markdown-артефакт с превью, для запуска — table-артефакт со сводкой |

### 1.4. Границы MVP: in scope и out of scope

**In scope.** MVP обязан уметь ровно это; расширение границ без `spec-patch` запрещено:

- Confluence Cloud и Confluence Server/Data Center;
- страницы типа `page`;
- единственный вход — список URL в `input/urls.txt` (§5);
- выход — четыре слоя `01_raw` / `02_interim` / `03_assets` / `04_markdown` плюс `manifest.json` и `run_report.json` (§0.1);
- макросы из каталога §8.4–§8.19 плюс безопасный fallback для всех остальных (§8.20);
- Prefect 3.x flow, запускаемый локально через CLI (§11.1);
- unit-тесты без живого Confluence, только на фикстурах (§12).

**Out of scope.** Явно **не реализуется** (и не должно появляться ни в коде, ни в тестах, ни в CLI-флагах):

- рекурсивная выгрузка descendants/дерева страниц, если URL не перечислен в `urls.txt`;
- комментарии, likes, restrictions, дамп истории версий;
- запись/обновление страниц в Confluence (pipeline строго read-only);
- собственный рендер PlantUML/Draw.io в растр;
- blogpost, whiteboard, database, Atlas doc format (`atlas_doc_format`);
- tiny-links `/x/<hash>` (см. §5.4 — возвращают `invalid_url`);
- Docker/K8s/CI-деплой, векторные БД, эмбеддинги, UI.

Точки расширения обозначены в §14, но их код в MVP отсутствует.

### 1.5. Пользователи и режим запуска

Единственный пользователь MVP — инженер на локальной машине (Windows/Linux/macOS) с доступом в Confluence. Запуск — из корня репозитория, `uv run python -m src.flows.export_flow [флаги]`. Prefect работает в локальном режиме (ephemeral API либо локальный сервер `prefect server start`), внешний деплой не требуется.

### 1.6. Human-gated зоны (review gates)

`docs/process/roles.md` сознательно не перечисляет продуктовые горячие точки — их объявляет спецификация. Изменение поведения в зонах ниже требует явного одобрения человека **независимо от размера диффа**. Задача, затрагивающая такую зону, обязана сослаться на эту секцию в своём DoD; агент при сомнении останавливается и спрашивает (stop-and-ask по `docs/process/roles.md`).

| Зона | Нормативные секции | Почему гейт |
|---|---|---|
| Аутентификация, обращение с токеном, `CONFLUENCE_VERIFY_SSL` | §6.1, §11.3, §11.4 | утечка кред, обход проверки TLS |
| Протокол скачивания вложений: основной REST-путь и fallback | §7.2 | возврат к UI-пути даёт 401 и тихую потерю медиа |
| Layout слоёв, схема относительных ссылок, имена файлов и slug | §0.1, §3.3, §7.4–§7.6 | ломает уже выгруженные хранилища и все ссылки в них |
| Disk-skip и сравнение версий | §3.2, §6.4, §6.6 | потеря идемпотентности либо перезапись актуальных данных |
| Публичные контракты: frontmatter, `manifest.json`, `run_report.json`, `PageRaw` | §4.4, §4.6, §4.7 | их читают внешние RAG- и Obsidian-пайплайны |
| Изоляция ошибок, failure policy, коды выхода | §10.4, §10.5, §11.2 | скрытые падения батча в автоматизации |
| Ослабление или удаление обязательных тестов | §12 | снимает страховку со всех зон выше |

---

## 2. C4 / компонентная схема

### 2.1. Уровень 1 — контекст

```text
┌───────────────┐      urls.txt        ┌───────────────────────────┐   HTTPS REST    ┌──────────────────────┐
│  Инженер      │ ───────────────────► │  confluence-md-exporter   │ ──────────────► │  Confluence           │
│  (CLI)        │ ◄─── exit code ───── │  (CLI + Prefect 3 flow)   │ ◄───JSON/bytes──│  Cloud | Server/DC    │
└───────────────┘                      └────────────┬──────────────┘                 └──────────────────────┘
                                                    │ files
                                                    ▼
                                       ┌───────────────────────────┐
                                       │ Локальная ФС: data/       │──► Obsidian / RAG-пайплайн
                                       │ 01_raw 02_interim         │
                                       │ 03_assets 04_markdown     │
                                       └───────────────────────────┘
                                                    │ run metadata
                                                    ▼
                                       ┌───────────────────────────┐
                                       │ Prefect 3 (local API/UI)  │
                                       │ task runs + artifacts     │
                                       └───────────────────────────┘
```

### 2.2. Уровень 2 — контейнеры/модули

```text
src/
├── config.py            Settings (pydantic-settings), get_settings(), валидация auth/edition
├── models.py            PageTarget, PageRaw, Attachment, AssetRecord, PageResult, ManifestItem, RunReport, enums
├── logging.py            configure_logging(), get_logger(); маскирование секретов
├── paths.py             layout-функции: raw_path(), interim_path(), assets_dir(), md_path(), asset_relative_path()
├── naming.py            slugify(), safe_filename(), unique_filename(), artifact_key()
├── client/
│   ├── resolver.py      parse_page_url() — чистый парсер URL (без сети)
│   ├── api.py           ApiStrategy (Protocol) + общие DTO эндпоинтов
│   ├── cloud.py         CloudApi  — Confluence Cloud REST v2 (+ v1 только для download/user)
│   ├── datacenter.py    DataCenterApi — Confluence Server/DC REST v1
│   └── confluence.py    ConfluenceClient — httpx.Client, auth, retry/backoff, disk-skip probe, download
├── transformers/
│   ├── macro_handlers.py  реестр обработчиков ac:*/ri:* макросов
│   ├── html_cleaner.py    storage XML -> clean HTML (нормализация таблиц, ссылок, entity)
│   └── md_converter.py    clean HTML -> GFM (ConfluenceMarkdownConverter + post-process + frontmatter)
└── flows/
    ├── tasks.py         @task: parse_and_validate_urls, fetch_page_raw, sync_page_assets,
    │                          transform_storage_to_clean_html, render_final_markdown,
    │                          process_page, write_manifest_and_report
    └── export_flow.py   @flow export_confluence_batch + argparse CLI + коды выхода
```

### 2.3. Уровень 3 — ответственность и зависимости

| Компонент | Знает про | Не знает про |
|---|---|---|
| `config.py` | env, файловые пути | HTTP, Prefect, HTML |
| `client/resolver.py` | формы URL, base_url | HTTP, файлы, Prefect |
| `client/confluence.py` | httpx, auth, retry, ФС (запись бинарников), `ApiStrategy` | Prefect, Markdown, макросы |
| `client/cloud.py`, `client/datacenter.py` | конкретные эндпоинты и маппинг в `PageRaw` | httpx-транспорт (получают `HttpTransport`-колбэк), ФС |
| `transformers/*` | XML/HTML/Markdown, `PageRaw`, `AssetSidecar`, `LinkIndex` | сеть, Prefect, env |
| `flows/tasks.py` | все вышестоящие, Prefect API | argparse |
| `flows/export_flow.py` | tasks, Settings, коды выхода | HTML/XML детали |

Правила зависимостей (проверяются ревью):

1. `transformers/*` **не выполняют сетевых вызовов** — они чистые функции от `(PageRaw, AssetSidecar, LinkIndex, Settings-подмножество)`. Это делает их полностью тестируемыми на фикстурах.
2. `client/*` **не импортируют Prefect**.
3. `flows/*` — единственное место, где есть `@task`/`@flow`/`get_run_logger()`.
4. Ни один модуль, кроме `config.py`, не читает `os.environ`.

---

## 3. Data flow

### 3.1. Сквозная схема

```text
input/urls.txt
   │
   ▼
[T1] parse_and_validate_urls
   │  чтение UTF-8, отбрасывание пустых строк и '#'-комментариев
   │  parse_page_url() -> ParsedUrlRef                     (чистый парсинг, §5)
   │  для kind=space_title: client.find_page_by_title()    (1 REST-вызов, кэш)
   │  дедупликация по page_id (WARNING на дубликат)
   ├──► invalid: list[InvalidUrl]  ─────────────────────────────────────────┐
   ▼                                                                        │
UrlBatch.targets: list[PageTarget]  (page_id всегда заполнен)               │
   │  batch_page_ids = frozenset(t.page_id)                                 │
   ▼                                                                        │
для каждого target, параллельно (ThreadPoolTaskRunner, max_workers=EXPORT_CONCURRENCY)
   │
   └─[T6] process_page(target, batch_page_ids)   ← изоляция ошибок try/except
         │
         ├─[T2] fetch_page_raw ──────────────────────────────────────────┐
         │        A. force_refresh?  ──да──► FULL FETCH                  │
         │        B. 01_raw/<id>.json нет? ──да──► FULL FETCH            │
         │        C. version probe (без body)                            │
         │             status != current ──► PageResult(skipped, trashed)│
         │             remote.version != local.version ──► FULL FETCH    │
         │             remote.version == local.version ──► DISK-SKIP     │
         │                                                               │
         │        FULL FETCH:  get_page(body.storage) + list_attachments  │
         │                     + labels + ancestors + build_link_index    │
         │                     запись 01_raw/<id>.json, <id>.links.json   │
         │        DISK-SKIP:   чтение локального 01_raw/<id>.json,        │
         │                     links.json (если нет — перестроить оффлайн)│
         ▼                                                               │
         FetchOutcome{page_raw, link_index, mode: full|disk_skip|trashed} │
         │                                                               │
         ├─[T3] sync_page_assets                                         │
         │        для каждого attachment (current-версия):                │
         │          safe = safe_filename(title); dest = 03_assets/<id>/…  │
         │          если mode=disk_skip и dest.exists() и size совпал     │
         │             ──► reuse (без сети)                               │
         │          иначе download_attachment() (REST, §7)                │
         │        удаление stale-файлов, которых нет в текущем списке      │
         │        запись 01_raw/<id>.assets.json                          │
         ▼                                                               │
         AssetSidecar{files: list[AssetRecord]}                          │
         │                                                               │
         ├─[T4] transform_storage_to_clean_html   (чистая, без сети)      │
         │        parse storage XML → макро-движок → clean HTML           │
         │        запись 02_interim/<id>.html                             │
         │        сбор unsupported_macros, warnings                        │
         ▼                                                               │
         CleanHtml{html, unsupported_macros, deferred_blocks, warnings}   │
         │                                                               │
         ├─[T5] render_final_markdown             (чистая, без сети)      │
         │        HTML → GFM (markdownify+post-process) → frontmatter      │
         │        запись 04_markdown/<id>_<slug>.md                       │
         │        create_markdown_artifact(key=f"page-{id}")              │
         ▼                                                               │
         PageResult(status=ok|skipped, manifest_item=…)                   │
                                                                          │
   ▼                                                                      │
[T7] write_manifest_and_report ◄──────────────────────────────────────────┘
   │  fixup_internal_links: cmex://page/<id> → ./<id>_<slug>.md | абсолютный URL
   │  04_markdown/manifest.json  (только ok|skipped|failed страницы)
   │  run_report.json            (+ invalid_urls)
   │  create_table_artifact(key="run-summary")
   ▼
exit code 0 | 1 | 2
```

### 3.2. Ветки disk-skip (нормативно)

Состояния локального кэша и реакция:

| # | Условие | Действие |
|---|---|---|
| D1 | `force_refresh=True` | FULL FETCH, все ассеты перекачиваются, `02_interim`/`04_markdown` перегенерируются |
| D2 | нет `01_raw/<id>.json` | FULL FETCH |
| D3 | `01_raw/<id>.json` не парсится в `PageRaw` (битый/старая схема) | WARNING, FULL FETCH |
| D4 | probe: `status != "current"` | `PageResult(status=skipped, reason=trashed)`, ассеты и md не трогать |
| D5 | probe: HTTP 404 | `PageResult(status=skipped, reason=not_found)` |
| D6 | probe: HTTP 403 | `PageResult(status=failed, reason=forbidden)`, без ретраев (§6.6) |
| D7 | `remote.version > local.version` или `!=` | FULL FETCH + пересборка всех слоёв страницы |
| D8 | версии равны, все ассеты на месте (`exists && st_size == file_size`), есть `02_interim/<id>.html` и `04_markdown/<id>_<slug>.md` | `PageResult(status=skipped, reason=up_to_date)`; сеть больше не используется; `manifest_item` собирается из локального raw |
| D9 | версии равны, часть ассетов отсутствует/размер не совпал | докачать **только** эти файлы, остальные слои пересобрать оффлайн из локального raw; итог `ok` |
| D10 | версии равны, но нет `02_interim`/`04_markdown` | пересборка T4+T5 из локального raw, без сети; итог `ok` |

Prefect-кэш (`cache_policy=INPUTS + TASK_SOURCE`) — **вторичный** слой ускорения внутри одного окна времени. Он не является механизмом идемпотентности: решение «качать/не качать» принимает алгоритм D1–D10 по состоянию диска и `version` из probe-запроса. При `force_refresh=True` ключ кэша меняется, потому что `force_refresh` входит в аргументы таски (§10.3).

### 3.3. Гарантии атомарности записи

Любая запись файла (json, html, md, бинарник) выполняется через `write_atomic()`:

1. запись в `<target>.tmp-<uuid4().hex[:8]>` в том же каталоге;
2. `os.replace(tmp, target)`.

Это исключает битые артефакты при прерывании и делает повторный запуск безопасным. `write_atomic` живёт в `src/paths.py`:

```python
def write_atomic(path: Path, data: bytes | str, *, encoding: str = "utf-8") -> Path: ...
```

Текст пишется с `newline="\n"` (LF) на всех платформах, включая Windows.

---
## 4. Pydantic-модели

Все модели — `pydantic v2`. Общая база для доменных моделей:

```python
# src/models.py
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Базовый класс всех доменных моделей: строгая схема, запрет мусорных полей."""

    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)
```

### 4.1. Перечисления

```python
class Edition(StrEnum):
    CLOUD = "cloud"
    DATACENTER = "datacenter"


class AuthType(StrEnum):
    BASIC = "basic"
    BEARER = "bearer"


class TargetKind(StrEnum):
    PAGE_ID = "page_id"          # page_id получен прямо из URL
    SPACE_TITLE = "space_title"  # нужен lookup по (space_key, title)


class FetchMode(StrEnum):
    FULL = "full"            # сходили за body.storage
    DISK_SKIP = "disk_skip"  # версия совпала, работаем с локальным raw
    ABSENT = "absent"        # страница недоступна (trashed/404) — дальше не идём


class ResultStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"
    INVALID_URL = "invalid_url"


class FailureReason(StrEnum):
    UP_TO_DATE = "up_to_date"                # skipped: disk-skip
    TRASHED = "trashed"                      # skipped: status != current
    NOT_FOUND = "not_found"                  # skipped: HTTP 404
    FORBIDDEN = "forbidden"                  # failed: HTTP 403/401 на странице
    AUTH_ERROR = "auth_error"                # failed: 401 на уровне сессии
    RATE_LIMITED = "rate_limited"            # failed: 429 после исчерпания retries
    HTTP_ERROR = "http_error"                # failed: прочий не-2xx
    NETWORK_ERROR = "network_error"          # failed: таймаут/DNS/SSL
    PARSE_ERROR = "parse_error"              # failed: storage XML не разобран
    RENDER_ERROR = "render_error"            # failed: ошибка сборки Markdown
    IO_ERROR = "io_error"                    # failed: ошибка записи на диск
    INVALID_URL = "invalid_url"              # строка входа не распознана
    HOST_MISMATCH = "host_mismatch"          # URL указывает на другой хост
    UNSUPPORTED_URL_FORM = "unsupported_url_form"   # /x/<tiny>, blogpost и т.п.
    TITLE_LOOKUP_FAILED = "title_lookup_failed"     # /display/SPACE/Title не нашёлся
    DUPLICATE = "duplicate"                  # схлопнутый дубликат (только WARNING в лог)


class AssetSource(StrEnum):
    ATTACHMENT = "attachment"        # вложение текущей страницы
    FOREIGN_ATTACHMENT = "foreign"   # вложение другой страницы (ri:page внутри ri:attachment)
    MISSING = "missing"              # скачать не удалось, вставлен placeholder


class MacroName(StrEnum):
    """Макросы с полноценной поддержкой (§8). Всё, чего здесь нет, идёт в fallback §8.20."""

    CODE = "code"
    PLANTUML = "plantuml"
    PLANTUMLCLOUD = "plantumlcloud"
    DRAWIO = "drawio"
    DRAWIO_DOT = "draw.io"
    INFO = "info"
    NOTE = "note"
    PANEL = "panel"
    TIP = "tip"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    EXPAND = "expand"
    STATUS = "status"
    DATE = "date"
    NOFORMAT = "noformat"
    VIEW_FILE = "view-file"
    VIEWPDF = "viewpdf"
    MULTIMEDIA = "multimedia"


class CalloutKind(StrEnum):
    NOTE = "NOTE"
    WARNING = "WARNING"
    TIP = "TIP"


class DeferredKind(StrEnum):
    RAW_HTML = "raw_html"   # блок вставляется в Markdown как есть (вложенные таблицы)
    DETAILS = "details"     # <details><summary>…</summary> + вложенный Markdown
```

### 4.2. `Settings`

```python
# src/config.py
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.models import AuthType, Edition


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    confluence_base_url: str = Field(..., description="Origin без хвоста /wiki и без завершающего /")
    confluence_edition: Edition = Field(...)
    confluence_auth_type: AuthType = Field(...)
    confluence_token: SecretStr = Field(...)
    confluence_username: str | None = Field(default=None)
    confluence_verify_ssl: bool = Field(default=True)
    confluence_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    confluence_max_retries: int = Field(default=3, ge=0, le=10)

    export_output_dir: Path = Field(default=Path("data"))
    export_input_file: Path = Field(default=Path("input/urls.txt"))
    export_concurrency: int = Field(default=4, ge=1, le=32)
    export_force_refresh: bool = Field(default=False)

    log_level: str = Field(default="INFO")

    # --- валидация ---

    @field_validator("confluence_base_url")
    @classmethod
    def _normalize_base_url(cls, value: str) -> str:
        """Убирает завершающие '/', хвост '/wiki', требует http(s)://host."""
        cleaned = value.strip().rstrip("/")
        if cleaned.lower().endswith("/wiki"):
            cleaned = cleaned[: -len("/wiki")]
        parts = urlsplit(cleaned)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("CONFLUENCE_BASE_URL must be an absolute http(s) origin")
        if parts.path.rstrip("/"):
            raise ValueError("CONFLUENCE_BASE_URL must not contain a path except optional /wiki")
        return f"{parts.scheme}://{parts.netloc}"

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        upper = value.strip().upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _check_auth_completeness(self) -> "Settings":
        if self.confluence_auth_type is AuthType.BASIC and not (self.confluence_username or "").strip():
            raise ValueError(
                "CONFLUENCE_USERNAME is required when CONFLUENCE_AUTH_TYPE=basic "
                "(Cloud: account email, Server/DC: username)"
            )
        if not self.confluence_token.get_secret_value().strip():
            raise ValueError("CONFLUENCE_TOKEN must not be empty")
        return self

    # --- производные значения ---

    @property
    def api_root(self) -> str:
        """Корень REST-API. Cloud: '<base>/wiki'. DC: '<base>'."""
        return f"{self.confluence_base_url}/wiki" if self.confluence_edition is Edition.CLOUD else self.confluence_base_url

    @property
    def site_host(self) -> str:
        return urlsplit(self.confluence_base_url).netloc.lower()

    @property
    def raw_dir(self) -> Path: return self.export_output_dir / "01_raw"

    @property
    def interim_dir(self) -> Path: return self.export_output_dir / "02_interim"

    @property
    def assets_root(self) -> Path: return self.export_output_dir / "03_assets"

    @property
    def markdown_dir(self) -> Path: return self.export_output_dir / "04_markdown"

    @property
    def manifest_path(self) -> Path: return self.markdown_dir / "manifest.json"

    @property
    def run_report_path(self) -> Path: return self.export_output_dir / "run_report.json"


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Единственная точка чтения окружения. Синглтон на процесс.
    Таски Prefect выполняются в потоках того же процесса (ThreadPoolTaskRunner),
    поэтому они видят настройки, применённые CLI через set_settings()."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings()  # type: ignore[call-arg]
    return _SETTINGS


def set_settings(settings: Settings) -> None:
    """Применяет настройки с CLI-переопределениями. Вызывается один раз из main()."""
    global _SETTINGS
    _SETTINGS = settings


def reset_settings(*, reload: bool = False) -> None:
    """Сбрасывает синглтон. Используется только в тестах."""
    global _SETTINGS
    _SETTINGS = Settings() if reload else None  # type: ignore[call-arg]
```

Синглтон на модульной переменной выбран вместо `functools.lru_cache`, потому что CLI обязан **подменить** уже собранный объект настройками с учётом флагов (`--output`, `--concurrency`), а `lru_cache` не позволяет засеять кэш готовым значением.

`SecretStr` обязателен: он исключает попадание токена в `repr`, логи, Prefect-параметры и трейсбеки. `Settings` **никогда** не передаётся в аргументы Prefect-таски (§10.3).

### 4.3. Входные модели URL

```python
class ParsedUrlRef(DomainModel):
    """Результат чистого (оффлайн) парсинга строки входного файла."""

    raw_input: str
    kind: TargetKind | None                 # None, если распознать не удалось
    page_id: str | None = None
    space_key: str | None = None
    title: str | None = None                # уже URL-декодированный, '+' -> ' '
    anchor: str | None = None               # фрагмент без '#'
    matched_pattern: str | None = None      # имя правила из §5.2 (для тестов и логов)
    error: FailureReason | None = None      # заполнено ⟺ kind is None


class PageTarget(DomainModel):
    """Разрешённая цель выгрузки. page_id гарантированно заполнен."""

    page_id: str = Field(..., pattern=r"^\d+$")
    raw_input: str
    space_key: str | None = None
    title_hint: str | None = None
    anchor: str | None = None
    source_url: str                          # канонический URL страницы (§6.5)


class InvalidUrl(DomainModel):
    raw_input: str
    line_no: int
    reason: FailureReason
    detail: str


class UrlBatch(DomainModel):
    targets: list[PageTarget]
    invalid: list[InvalidUrl]
    duplicates: list[str] = Field(default_factory=list)   # схлопнутые raw_input

    @property
    def batch_page_ids(self) -> frozenset[str]:
        return frozenset(t.page_id for t in self.targets)
```

### 4.4. Bronze-модели

```python
class Ancestor(DomainModel):
    id: str
    title: str


class Attachment(DomainModel):
    """Метаданные вложения в терминах REST (до скачивания)."""

    id: str                                  # attachment id, например "att12345"
    title: str                               # исходное имя файла как в Confluence
    media_type: str = "application/octet-stream"
    file_size: int = Field(default=0, ge=0)
    version: int = Field(default=1, ge=1)
    page_id: str                             # страница-владелец (может отличаться от текущей)
    download_api_path: str                   # основной REST-путь, относительный к base_url
    download_fallback_path: str | None = None  # путь из API-ответа (_links.download / downloadLink)


class PageRaw(DomainModel):
    """Контракт 01_raw/<page_id>.json. Ключи стабильны, порядок фиксирован."""

    page_id: str
    edition: Edition
    title: str
    space_key: str
    version: int = Field(..., ge=1)
    status: str                              # "current" для успешно выгруженных
    created_by: str                          # username (DC) / displayName или accountId (Cloud)
    updated_at: str                          # ISO-8601 UTC, формат "%Y-%m-%dT%H:%M:%SZ"
    source_url: str
    labels: list[str] = Field(default_factory=list)
    ancestors: list[Ancestor] = Field(default_factory=list)
    body_storage: str                        # именно body.storage, не view/export_view
    attachments: list[Attachment] = Field(default_factory=list)
    fetched_at: str                          # ISO-8601 UTC

    @property
    def breadcrumbs(self) -> list[str]:
        return [a.title for a in self.ancestors] + [self.title]


class VersionProbe(DomainModel):
    """Лёгкий ответ probe-запроса без body (§6.4)."""

    page_id: str
    version: int
    status: str
    title: str
    updated_at: str


class AssetRecord(DomainModel):
    attachment_id: str
    original_filename: str
    safe_filename: str
    media_type: str
    file_size: int
    sha256: str | None = None                # None только при source=missing
    source: AssetSource
    owner_page_id: str                       # страница-владелец вложения
    relative_path: str | None = None         # "../03_assets/<page_id>/<safe>"; None при missing
    downloaded_at: str | None = None


class AssetSidecar(DomainModel):
    """Контракт 01_raw/<page_id>.assets.json. Единственный источник карты original -> safe."""

    page_id: str
    generated_at: str
    files: list[AssetRecord] = Field(default_factory=list)

    def by_original(self) -> dict[str, AssetRecord]:
        """Ключ поиска для макросов: точное имя из ri:filename."""
        return {rec.original_filename: rec for rec in self.files}


class LinkTarget(DomainModel):
    """Разрешённая внутренняя ссылка (заполняется на этапе fetch, где разрешена сеть)."""

    space_key: str | None
    title: str
    page_id: str | None                      # None => цель не найдена
    absolute_url: str | None                  # канонический URL, если page_id известен


class LinkIndex(DomainModel):
    """Контракт 01_raw/<page_id>.links.json."""

    page_id: str
    generated_at: str
    entries: list[LinkTarget] = Field(default_factory=list)

    def lookup(self, space_key: str | None, title: str) -> LinkTarget | None: ...
```

Ключ поиска в `LinkIndex.lookup`: `(space_key or "", title)` в нижнем регистре с `strip()`.

### 4.5. Модели этапов трансформации

```python
class DeferredBlock(DomainModel):
    index: int
    kind: DeferredKind
    payload: str                             # HTML для raw_html; HTML тела для details
    title: str | None = None                 # summary для details


class CleanHtml(DomainModel):
    page_id: str
    html: str
    unsupported_macros: list[str] = Field(default_factory=list)   # уникальные, отсортированы
    deferred: list[DeferredBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FetchOutcome(DomainModel):
    """Результат fetch_page_raw: что удалось получить и в каком режиме."""

    mode: FetchMode
    page_raw: PageRaw | None                 # None только при mode=ABSENT
    link_index: LinkIndex
    reason: FailureReason | None = None      # заполнено при mode=ABSENT


class RenderedPage(DomainModel):
    page_id: str
    md_path: Path
    slug: str
    frontmatter: dict[str, object]
    body_markdown: str
    preview: str                             # для Prefect-артефакта, ≤ 1200 символов
```

### 4.6. Выходные модели

```python
class ManifestItem(DomainModel):
    """Элемент 04_markdown/manifest.json. Публичный контракт, см. §1.6."""

    id: str
    title: str
    space_key: str
    version: int
    source_url: str
    md_path: str                             # POSIX-путь относительно EXPORT_OUTPUT_DIR: "04_markdown/<id>_<slug>.md"
    assets_dir: str                          # "03_assets/<id>"
    labels: list[str] = Field(default_factory=list)
    status: Literal["ok", "failed", "skipped"]
    error: str | None = None


class PageResult(DomainModel):
    raw_input: str
    page_id: str | None
    title: str | None = None
    status: ResultStatus
    reason: FailureReason | None = None
    error: str | None = None                 # человекочитаемое сообщение, без секретов
    md_path: str | None = None
    assets_dir: str | None = None
    attachments_count: int = 0
    unsupported_macros: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    manifest_item: ManifestItem | None = None


class RunError(DomainModel):
    page_id: str | None
    raw_input: str
    reason: FailureReason
    message: str


class RunReport(DomainModel):
    """Контракт run_report.json. Публичный контракт, см. §1.6."""

    started_at: str
    finished_at: str
    pages_total: int
    ok: int
    failed: int
    skipped: int
    invalid_urls: list[InvalidUrl] = Field(default_factory=list)
    force_refresh: bool
    duplicates: list[str] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    edition: Edition
    output_dir: str
```

`pages_total` = число `targets` (без `invalid_urls`). Инвариант, проверяемый тестом: `pages_total == ok + failed + skipped`.

### 4.7. Frontmatter (Gold-контракт)

Frontmatter строится функцией `build_frontmatter(page_raw, unsupported_macros, attachments_count) -> dict[str, object]` с **фиксированным порядком ключей**:

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
  - architecture
breadcrumbs:
  - "Главная"
  - "Проекты 2026"
  - "Архитектура интеграционного шлюза"
attachments_count: 3
unsupported_macros:
  - toc
---
```

Правила сериализации (нормативно):

1. `id` — **всегда строка** (в YAML в двойных кавычках).
2. `breadcrumbs` = `[a.title for a in ancestors] + [title]`.
3. `labels`, `unsupported_macros` — списки; пустой список сериализуется как `[]` (ключ не опускается).
4. `unsupported_macros` — уникальные, отсортированы по алфавиту.
5. Сериализация: `yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10**6)`. Кириллица не escape-ится.
6. Значения строк с `:`/`#`/кавычками safe_dump закавычит сам; вручную кавычки не добавляются.
7. Обрамление: строка `---`, YAML, строка `---`, пустая строка, затем `# {title}` (H1) и тело.

---

## 5. URL resolver

Модуль `src/client/resolver.py`. Функция `parse_page_url` — **чистая, без сети**, полностью покрывается unit-тестами.

```python
def parse_page_url(raw_input: str, base_url: str) -> ParsedUrlRef: ...
```

### 5.1. Алгоритм

1. `line = raw_input.strip()`. Если пусто или начинается с `#` → строка вообще не доходит до resolver (фильтруется в `parse_and_validate_urls`).
2. Если `re.fullmatch(r"\d+", line)` → `kind=PAGE_ID, page_id=line, matched_pattern="bare_page_id"`. Возврат.
3. Если строка не начинается с `http://`/`https://` → попытка достроить: `candidate = f"{base_url}/{line.lstrip('/')}"`, `matched_pattern` получит суффикс `+relative`.
4. `parts = urlsplit(candidate)`; `anchor = parts.fragment or None`.
5. Проверка хоста: `parts.netloc.lower()` (без `:80`/`:443`) должен совпасть с `urlsplit(base_url).netloc.lower()`. Иначе → `error=HOST_MISMATCH`.
6. `query = parse_qs(parts.query, keep_blank_values=False)`.
7. Правила из таблицы §5.2 применяются **строго по порядку сверху вниз**; первое совпадение выигрывает.
8. Если ни одно правило не совпало → `error=UNSUPPORTED_URL_FORM`.
9. Нормализация `title`: `unquote_plus(...)` (то есть `+` → пробел, `%D0%90` → `А`), затем `unescape` HTML-entity, затем `strip()`.
10. `space_key`: берётся из пути как есть после `unquote()`; личные пространства (`~user`, `~5f3a…`) допустимы без изменений. Регистр не меняется.

### 5.2. Таблица правил

Проверка ведётся по `parts.path` (уже без хоста) и `query`. Префикс `/wiki` вырезается перед сопоставлением, если `edition=cloud`-подобный путь: технически применяется regex-нормализация `path = re.sub(r"^/wiki(?=/)", "", path)`.

| # | `matched_pattern` | Условие | Извлекается | Результат |
|---|---|---|---|---|
| 1 | `bare_page_id` | `^\d+$` по всей строке | `page_id` | `PAGE_ID` |
| 2 | `query_page_id` | в `query` есть ключ `pageId` (регистронезависимо) со значением `^\d+$` | `page_id`, `space_key` из `spaceKey` если есть | `PAGE_ID` |
| 3 | `spaces_pages_id` | `^/spaces/(?P<space>[^/]+)/pages/(?P<id>\d+)(?:/.*)?$` | `space_key`, `page_id`, `title` из последнего сегмента (если есть) | `PAGE_ID` |
| 4 | `display_space_title` | `^/display/(?P<space>[^/]+)/(?P<title>[^/]+)/?$` | `space_key`, `title` | `SPACE_TITLE` |
| 5 | `query_space_title` | `^/pages/viewpage\.action$` и в `query` есть `spaceKey` и `title` | `space_key`, `title` | `SPACE_TITLE` |
| 6 | `attachments_path` | `^/download/attachments/(?P<id>\d+)/.*$` | `page_id` | `PAGE_ID` (WARNING «ссылка на вложение, экспортируется страница-владелец») |
| 7 | `tiny_link` | `^/x/[A-Za-z0-9_\-+%]+$` | — | `error=UNSUPPORTED_URL_FORM`, detail `tiny links are out of MVP scope` |
| 8 | `blogpost` | путь содержит `/blog/` или `?type=blogpost` | — | `error=UNSUPPORTED_URL_FORM` |
| — | — | иначе | — | `error=UNSUPPORTED_URL_FORM` |

Правило 3 покрывает и `.../wiki/spaces/SPACE/pages/123456/Title`, и `.../wiki/spaces/~user/pages/123456/Title` (после снятия `/wiki`), и DC-форму `.../spaces/SPACE/pages/123/Title`.

### 5.3. Разрешение `SPACE_TITLE` в `page_id`

Выполняется в таске `parse_and_validate_urls` через `ConfluenceClient.find_page_by_title(space_key, title)` (§6.6). Результат кэшируется в процессе (`dict[(space_key, title), str]`). Если не найдено или доступ запрещён → строка попадает в `invalid` с `reason=TITLE_LOOKUP_FAILED`, весь батч продолжается.

### 5.4. Тесты-примеры (обязательный набор, `tests/test_url_resolver.py`)

`base_url = "https://confluence.example"` (кроме случаев с `atlassian.net`).

| Вход | Ожидаемый результат |
|---|---|
| `https://confluence.example/pages/viewpage.action?pageId=109847231` | `PAGE_ID`, `page_id="109847231"`, `matched_pattern="query_page_id"` |
| `https://confluence.example/pages/viewpage.action?pageId=109847231&src=contextnavpagetreemode` | `PAGE_ID`, `page_id="109847231"` |
| `https://confluence.example/pages/viewpage.action?spaceKey=ARCH&pageId=42` | `PAGE_ID`, `page_id="42"`, `space_key="ARCH"` |
| `https://confluence.example/display/ARCH/Kafka+Gateway` | `SPACE_TITLE`, `space_key="ARCH"`, `title="Kafka Gateway"` |
| `https://confluence.example/display/ARCH/%D0%A8%D0%BB%D1%8E%D0%B7` | `SPACE_TITLE`, `title="Шлюз"` |
| `https://confluence.example/pages/viewpage.action?spaceKey=ARCH&title=Kafka+Gateway` | `SPACE_TITLE`, `matched_pattern="query_space_title"` |
| `https://acme.atlassian.net/wiki/spaces/ARCH/pages/109847231/Gateway` (base `https://acme.atlassian.net`) | `PAGE_ID`, `page_id="109847231"`, `space_key="ARCH"`, `title="Gateway"` |
| `https://acme.atlassian.net/wiki/spaces/~712020abc/pages/55/Notes` | `PAGE_ID`, `space_key="~712020abc"` |
| `https://confluence.example/spaces/ARCH/pages/77/Title` | `PAGE_ID`, `page_id="77"` |
| `109847231` | `PAGE_ID`, `matched_pattern="bare_page_id"` |
| `/display/ARCH/Page` | `SPACE_TITLE` (достройка относительного пути), `matched_pattern="display_space_title+relative"` |
| `https://confluence.example/pages/viewpage.action?pageId=42#section-2` | `PAGE_ID`, `anchor="section-2"` |
| `https://confluence.example/download/attachments/42/f.png?version=1` | `PAGE_ID`, `page_id="42"`, WARNING |
| `https://other.example/pages/viewpage.action?pageId=1` | `error=HOST_MISMATCH` |
| `https://confluence.example/x/AbCdEf` | `error=UNSUPPORTED_URL_FORM` |
| `https://confluence.example/wiki/blog/2026/01/01/Post` | `error=UNSUPPORTED_URL_FORM` |
| `not a url at all` | `error=UNSUPPORTED_URL_FORM` |
| `https://confluence.example/pages/viewpage.action?pageId=abc` | `error=UNSUPPORTED_URL_FORM` |

Дедупликация (тест `test_dedup_by_page_id`): вход из трёх строк — `.../pageId=42`, `42`, `.../pageId=42&src=x` — даёт один `PageTarget` и два элемента в `UrlBatch.duplicates` + два WARNING в логе.

---

## 6. API adapter: Cloud vs Data Center

### 6.1. Транспорт (`src/client/confluence.py`)

```python
class ConfluenceClient:
    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None: ...

    # низкий уровень
    def request_json(self, method: str, path: str, *, params: dict[str, str | int] | None = None) -> dict: ...
    def stream_to_file(self, path: str, dest: Path) -> tuple[int, str]: ...   # (bytes_written, sha256)
    def close(self) -> None: ...
    def __enter__(self) -> "ConfluenceClient": ...
    def __exit__(self, *exc: object) -> None: ...

    # доменные операции (делегируют в ApiStrategy)
    def resolve_url(self, raw_input: str) -> PageTarget: ...
    def find_page_by_title(self, space_key: str, title: str) -> str | None: ...
    def probe_version(self, page_id: str) -> VersionProbe: ...
    def get_page(self, page_id: str) -> PageRaw: ...
    def list_attachments(self, page_id: str) -> list[Attachment]: ...
    def download_attachment(self, attachment: Attachment, dest_path: Path) -> AssetRecord: ...
    def get_labels(self, page_id: str) -> list[str]: ...
    def get_ancestors(self, page_id: str) -> list[Ancestor]: ...
    def build_link_index(self, page_raw: PageRaw) -> LinkIndex: ...
```

Конструкция `httpx.Client`:

```python
httpx.Client(
    base_url=settings.confluence_base_url,          # всегда origin без /wiki
    auth=self._build_auth(),                        # BasicAuth или None
    headers=self._build_headers(),
    verify=settings.confluence_verify_ssl,
    timeout=httpx.Timeout(
        connect=min(10.0, settings.confluence_timeout_seconds),
        read=settings.confluence_timeout_seconds,
        write=settings.confluence_timeout_seconds,
        pool=settings.confluence_timeout_seconds,
    ),
    follow_redirects=True,
    limits=httpx.Limits(max_connections=settings.export_concurrency * 2, max_keepalive_connections=settings.export_concurrency),
)
```

Заголовки:

| Заголовок | Значение | Условие |
|---|---|---|
| `Accept` | `application/json` | JSON-запросы |
| `Accept` | `*/*` | скачивание бинарников |
| `User-Agent` | `confluence-md-exporter/1.0` | всегда |
| `X-Atlassian-Token` | `no-check` | всегда для `edition=datacenter` (обход XSRF-проверки) |
| `Authorization` | `Bearer <token>` | `auth_type=bearer` |
| — | `httpx.BasicAuth(username, token)` | `auth_type=basic` |

`_build_auth()`:

```python
def _build_auth(self) -> httpx.Auth | None:
    if self.settings.confluence_auth_type is AuthType.BASIC:
        return httpx.BasicAuth(self.settings.confluence_username or "", self.settings.confluence_token.get_secret_value())
    return None  # bearer уходит в заголовок
```

Матрица auth (нормативно; human-gated зона, §1.6):

| Сценарий | `CONFLUENCE_EDITION` | `CONFLUENCE_AUTH_TYPE` | `CONFLUENCE_USERNAME` | `CONFLUENCE_TOKEN` |
|---|---|---|---|---|
| Cloud BASIC | `cloud` | `basic` | **обязателен**: email аккаунта | API token из id.atlassian.com |
| Server/DC BEARER | `datacenter` | `bearer` | не используется | Personal Access Token |
| Server/DC BASIC | `datacenter` | `basic` | **обязателен**: username | password или token |

Cloud + `bearer` формально допустим (OAuth access token), но не является поддерживаемым сценарием MVP: при такой комбинации логируется WARNING `bearer auth on cloud edition is untested`. Отсутствие `username` при `basic` — фатальная ошибка конфигурации → exit code 2.

### 6.2. Retry и backoff

Реализуется в `request_json`/`stream_to_file` **вручную** (без `httpx`-транспортных ретраев, чтобы уважать `Retry-After`):

```python
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
RETRYABLE_EXC = (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError)
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0
```

Алгоритм попытки `attempt` (0-based, всего `confluence_max_retries + 1` попыток):

1. Выполнить запрос.
2. Статус 2xx → вернуть.
3. Статус 401 → `AuthError` (не ретраить; ведёт к exit code 2, если возникает на первом же запросе, иначе `failed/auth_error`).
4. Статус 403 → `ForbiddenError` (**не ретраить**).
5. Статус 404 → `NotFoundError` (не ретраить).
6. Статус ∈ `RETRYABLE_STATUS`: если `attempt == max_retries` → `HttpError`. Иначе спать `delay` и повторить.
7. Прочий не-2xx → `HttpError` (не ретраить).
8. Исключение ∈ `RETRYABLE_EXC` → как п.6, но `reason=network_error`.

Расчёт задержки: `delay = float(Retry-After)` если заголовок присутствует и парсится (поддержать и число секунд, и HTTP-date), иначе `min(BACKOFF_MAX_SECONDS, BACKOFF_BASE_SECONDS * 2 ** attempt)`; к результату добавляется джиттер `random.uniform(0, 0.25 * delay)`. Каждая повторная попытка логируется на уровне WARNING в формате `retrying {method} {path_without_query} attempt={n} status={code} delay={d:.1f}s`.

**Запрещено** логировать: значение токена, заголовок `Authorization`, полный query-string запросов скачивания (в нём бывают подписи). В логи попадает только `method`, путь без query, статус.

### 6.3. Интерфейс стратегии

```python
# src/client/api.py
class ApiStrategy(Protocol):
    edition: Edition

    def probe_path(self, page_id: str) -> tuple[str, dict[str, str]]: ...
    def parse_probe(self, payload: dict) -> VersionProbe: ...

    def page_path(self, page_id: str) -> tuple[str, dict[str, str]]: ...
    def parse_page(self, payload: dict, *, labels: list[str], ancestors: list[Ancestor], space_key: str, created_by: str) -> PageRaw: ...

    def labels_request(self, page_id: str) -> tuple[str, dict[str, str]] | None: ...
    def ancestors_request(self, page_id: str) -> tuple[str, dict[str, str]] | None: ...
    def attachments_request(self, page_id: str) -> tuple[str, dict[str, str]]: ...
    def parse_attachments(self, payload: dict, page_id: str) -> list[Attachment]: ...
    def find_page_by_title_request(self, space_key: str, title: str) -> tuple[str, dict[str, str]]: ...
    def parse_find_page(self, payload: dict) -> list[str]: ...
    def next_page_path(self, payload: dict) -> str | None: ...
    def canonical_page_url(self, page_id: str, *, space_key: str | None = None, webui: str | None = None) -> str: ...
```

Реализации: `DataCenterApi` (REST v1) и `CloudApi` (REST v2 + два узких v1-вызова, см. §6.4.2). `ConfluenceClient` выбирает стратегию один раз в `__init__` по `settings.confluence_edition`. Никакой другой код не ветвится по редакции — это правило ревью.

### 6.4. Конкретные эндпоинты

#### 6.4.1. Data Center / Server (REST v1)

Все пути относительно `api_root == base_url`.

| Операция | Метод и путь | Параметры |
|---|---|---|
| probe версии | `GET /rest/api/content/{page_id}` | `expand=version,history.lastUpdated` |
| страница | `GET /rest/api/content/{page_id}` | `expand=body.storage,version,space,history,history.lastUpdated,ancestors,metadata.labels` |
| labels (добор) | `GET /rest/api/content/{page_id}/label` | `limit=200` — только если `metadata.labels.size >= 200` |
| ancestors | из `expand=ancestors` того же ответа | — |
| вложения | `GET /rest/api/content/{page_id}/child/attachment` | `limit=100&start=0&expand=version,history` |
| скачивание | `GET /rest/api/content/{page_id}/child/attachment/{attachment_id}/download` | — |
| поиск по title | `GET /rest/api/content` | `type=page&spaceKey={space}&title={title}&limit=2&expand=version` |

Пагинация v1: пока в ответе присутствует `_links.next` — выполнять `GET base_url + _links.next` (путь уже содержит query). Дополнительная страховка от бесконечного цикла: не более 50 итераций, затем WARNING и остановка.

Маппинг `parse_page` (DC):

| Поле `PageRaw` | Источник |
|---|---|
| `page_id` | `str(payload["id"])` |
| `edition` | `datacenter` |
| `title` | `html.unescape(payload["title"])` |
| `space_key` | `payload["space"]["key"]` |
| `version` | `int(payload["version"]["number"])` |
| `status` | `payload.get("status", "current")` |
| `created_by` | `payload["history"]["createdBy"].get("username") or ...get("displayName") or ...get("userKey") or "unknown"` |
| `updated_at` | `payload["version"]["when"]` → `normalize_ts()`; при отсутствии — `payload["history"]["lastUpdated"]["when"]` |
| `source_url` | `f"{base_url}/pages/viewpage.action?pageId={page_id}"` |
| `labels` | `[l["name"] for l in payload["metadata"]["labels"]["results"]]` (+ добор) |
| `ancestors` | `[Ancestor(id=str(a["id"]), title=html.unescape(a["title"])) for a in payload.get("ancestors", [])]`, порядок как отдан API (root-first) |
| `body_storage` | `payload["body"]["storage"]["value"]` (если ключа нет — `""`) |
| `attachments` | результат `list_attachments` |
| `fetched_at` | `utcnow_iso()` |

`parse_attachments` (DC): `id=str(r["id"])`, `title=html.unescape(r["title"])`, `media_type=r["extensions"].get("mediaType", "application/octet-stream")`, `file_size=int(r["extensions"].get("fileSize", 0))`, `version=int(r.get("version", {}).get("number", 1))`, `download_api_path=f"/rest/api/content/{page_id}/child/attachment/{id}/download"`, `download_fallback_path=r["_links"].get("download")`.

#### 6.4.2. Cloud (REST v2)

Все пути начинаются с `/wiki` (то есть относительны `base_url`, а `api_root` = `base_url + "/wiki"`). Причина выбора v2: v1 `content` API на Cloud объявлен deprecated, v2 — актуальный контракт.

| Операция | Метод и путь | Параметры |
|---|---|---|
| probe версии | `GET /wiki/api/v2/pages/{page_id}` | без `body-format` ⇒ ответ без тела |
| страница | `GET /wiki/api/v2/pages/{page_id}` | `body-format=storage` |
| labels | `GET /wiki/api/v2/pages/{page_id}/labels` | `limit=250` |
| ancestors | `GET /wiki/api/v2/pages/{page_id}/ancestors` | `limit=100` |
| title ancestor'а | `GET /wiki/api/v2/pages/{ancestor_id}` | без `body-format`; результат кэшируется в `dict[str,str]` |
| space key по id | `GET /wiki/api/v2/spaces/{space_id}` | кэшируется в `dict[str,str]` |
| space id по key | `GET /wiki/api/v2/spaces` | `keys={space_key}&limit=1` |
| поиск по title | `GET /wiki/api/v2/pages` | `space-id={space_id}&title={title}&status=current&limit=2` |
| вложения | `GET /wiki/api/v2/pages/{page_id}/attachments` | `limit=250` |
| скачивание (основное) | `GET /wiki/rest/api/content/{page_id}/child/attachment/{attachment_id}/download` | — |
| скачивание (fallback) | `GET /wiki{downloadLink}` из ответа v2 | — |
| displayName автора | `GET /wiki/rest/api/user` | `accountId={author_id}`; кэшируется; при 403/404 → `accountId` как есть |

Пагинация v2: курсорная. Пока `payload["_links"].get("next")` присутствует — выполнять `GET` по этому относительному пути (он уже содержит `cursor`). Тот же предохранитель на 50 итераций.

Маппинг `parse_page` (Cloud):

| Поле `PageRaw` | Источник |
|---|---|
| `page_id` | `str(payload["id"])` |
| `edition` | `cloud` |
| `title` | `html.unescape(payload["title"])` |
| `space_key` | `space_key_by_id(payload["spaceId"])` |
| `version` | `int(payload["version"]["number"])` |
| `status` | `payload.get("status", "current")` |
| `created_by` | `display_name(payload.get("authorId"))` |
| `updated_at` | `normalize_ts(payload["version"]["createdAt"])` |
| `source_url` | `f"{base_url}/wiki{payload['_links']['webui']}"`; если `webui` нет — `f"{base_url}/wiki/spaces/{space_key}/pages/{page_id}"` |
| `labels` | `[r["name"] for r in labels_results]` |
| `ancestors` | ids из `/ancestors` (root-first) → titles через кэш |
| `body_storage` | `payload["body"]["storage"]["value"]` |
| `attachments` | результат `list_attachments` |
| `fetched_at` | `utcnow_iso()` |

`parse_attachments` (Cloud): `id=str(r["id"])`, `title=html.unescape(r["title"])`, `media_type=r.get("mediaType", "application/octet-stream")`, `file_size=int(r.get("fileSize", 0))`, `version=int(r.get("version", {}).get("number", 1))`, `download_api_path=f"/wiki/rest/api/content/{page_id}/child/attachment/{id}/download"`, `download_fallback_path=("/wiki" + r["downloadLink"]) if r.get("downloadLink") else None`.

Ответы v2 могут содержать несколько записей с одинаковым `title` (разные вложения-омонимы). Правило дедупликации одинаково для обеих редакций: группировать по `title`, оставлять запись с максимальным `version`, при равенстве — с максимальным `id` (лексикографически по числовой части). Это реализует правило «брать current» из §8.22 (случай E4).

### 6.5. Канонический URL страницы

```python
def canonical_page_url(page_id: str, *, space_key: str | None = None, webui: str | None = None) -> str
```

- DC: `f"{base_url}/pages/viewpage.action?pageId={page_id}"` (всегда, `webui` игнорируется).
- Cloud: `f"{base_url}/wiki{webui}"` если `webui` передан, иначе `f"{base_url}/wiki/spaces/{space_key}/pages/{page_id}"`, а если `space_key` неизвестен — `f"{base_url}/wiki/pages/viewpage.action?pageId={page_id}"`.

Якорь добавляется вызывающей стороной как `f"{url}#{anchor}"` без дополнительного экранирования, кроме `quote(anchor, safe="-._~")`.

### 6.6. Normalization helpers и особые ответы

```python
def normalize_ts(value: str) -> str:
    """'2026-04-12T14:32:00.000+03:00' -> '2026-04-12T11:32:00Z'. Пустое/битое -> utcnow_iso()."""

def utcnow_iso() -> str:
    """datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')"""
```

Обработка особых ответов страницы:

| Ответ | Действие |
|---|---|
| 404 на probe или на странице | `NotFoundError` → `PageResult(skipped, not_found)` |
| `status` в ответе ≠ `current` (`trashed`, `draft`, `archived`) | `PageResult(skipped, trashed)`, тело не запрашивается |
| 403 | `ForbiddenError` → `PageResult(failed, forbidden)`, ретраев нет |
| 401 на первом запросе процесса | `AuthError` → flow не стартует, exit code 2 |
| 401 на отдельной странице (права на пространство) | `PageResult(failed, auth_error)` |
| 200, но `body.storage.value` отсутствует/пусто | не ошибка: `body_storage=""`, дальше §8.21 (пустая страница) |
| `type`/`_type` ответа не `page` | `PageResult(failed, http_error)` с сообщением `unsupported content type: {type}` |

### 6.7. `build_link_index`

Вызывается в `fetch_page_raw` **только при `FetchMode.FULL`** (единственное место, где трансформация нуждается в сети, поэтому она вынесена в fetch-этап).

Алгоритм:

1. Разобрать `page_raw.body_storage` (парсер §8.1) и собрать множество целей: все `ri:page` (атрибуты `ri:space-key`, `ri:content-title`) из `ac:link`, `ac:image`, `ri:attachment`.
2. Для каждой уникальной пары `(space_key or page_raw.space_key, title)`:
   - `page_id = find_page_by_title(space, title)` (кэш процесса);
   - при успехе `absolute_url = canonical_page_url(page_id, space_key=space)`;
   - при `None`/403 — `page_id=None`, `absolute_url=None`, WARNING `unresolved internal link: {space}/{title}`.
3. Записать `LinkIndex` в `01_raw/<page_id>.links.json`.

При `FetchMode.DISK_SKIP` индекс читается с диска; если файла нет — создаётся пустой `LinkIndex` (без сети), и нерешённые ссылки деградируют по правилу §8.16.3.

---

## 7. Asset download protocol

### 7.1. Общий порядок (`sync_page_assets`)

Вход: `PageRaw`, `FetchMode`, `Settings`. Выход: `AssetSidecar` (и файл `01_raw/<page_id>.assets.json`).

1. `attachments = page_raw.attachments` (уже дедуплицированы по §6.4.2).
2. `assets_dir = settings.assets_root / page_id`; `assets_dir.mkdir(parents=True, exist_ok=True)` — **только если есть хотя бы одно вложение**, иначе каталог не создаётся.
3. Построить `safe_filename` для каждого вложения (§7.4) и разрешить коллизии (§7.5).
4. Для каждого вложения:
   - `dest = assets_dir / safe`;
   - **reuse-условие**: `mode is FetchMode.DISK_SKIP and dest.exists() and dest.stat().st_size == attachment.file_size and attachment.file_size > 0`. Если выполнено — файл не качается, `AssetRecord` собирается из локального sidecar (в т.ч. `sha256`, если он там был), `downloaded_at` сохраняется прежним;
   - иначе — `download_attachment(attachment, dest)` (§7.2).
5. Только при `FetchMode.FULL`: удалить из `assets_dir` файлы, которых нет в новом наборе `safe_filename` (stale-очистка после переименования/удаления вложений в Confluence). Файлы с префиксом чужой страницы (`<other_id>__`) при этом сохраняются, если присутствуют в наборе; иначе удаляются.
6. Записать `AssetSidecar` (`write_atomic`, JSON `indent=2, ensure_ascii=False`, ключи в порядке модели).

Ошибка скачивания одного вложения **не валит страницу**: создаётся `AssetRecord(source=MISSING, sha256=None, relative_path=None)`, добавляется warning `asset download failed: {original_filename} ({reason})`, и макро-движок вставляет placeholder (§8.11.4). Это осознанное решение: текст страницы важнее полноты медиа.

### 7.2. `download_attachment`

```python
def download_attachment(self, attachment: Attachment, dest_path: Path) -> AssetRecord: ...
```

Порядок попыток (нормативно):

1. **Основной путь — REST**: `GET {base_url}{attachment.download_api_path}`, то есть
   - DC: `/rest/api/content/{page_id}/child/attachment/{attachment_id}/download`
   - Cloud: `/wiki/rest/api/content/{page_id}/child/attachment/{attachment_id}/download`
2. Если получен 401/403/404 — **fallback**: `GET {base_url}{attachment.download_fallback_path}` (значение пришло из API-ответа: `_links.download` для DC, `downloadLink` для Cloud). Fallback выполняется ровно один раз.
3. Если и fallback не дал 2xx — `AssetRecord(source=MISSING)` + warning.

UI-путь `/download/attachments/<page_id>/<file>` **никогда не конструируется вручную** — это источник 401 при отсутствии cookie-сессии. Он может встретиться только как значение `download_fallback_path`, полученное от самого API, и используется только на шаге 2.

Требования к запросу скачивания:

- `Authorization`/BasicAuth — те же, что для JSON-запросов (никакой cookie-сессии);
- `Accept: */*`;
- `follow_redirects=True` (Cloud отдаёт 302 на pre-signed URL медиа-сервиса; httpx снимает `Authorization` при кросс-origin редиректе, что корректно — подписанная ссылка самодостаточна);
- потоковая запись: `with client.stream("GET", url) as r:` → чанки по 64 KiB в `dest.with_suffix(dest.suffix + ".tmp-<uid>")`, параллельно `hashlib.sha256().update(chunk)`, затем `os.replace` на целевой путь;
- ретраи 429/5xx — по §6.2;
- по завершении: если `attachment.file_size > 0` и записано другое число байт — warning `size mismatch for {name}: expected {a}, got {b}`, но файл принимается, а в `AssetRecord.file_size` пишется **фактический** размер (иначе следующий запуск будет вечно считать файл битым).

### 7.3. Вложения с другой страницы

Storage может ссылаться на вложение чужой страницы:

```xml
<ac:image><ri:attachment ri:filename="Shared.png"><ri:page ri:space-key="ARCH" ri:content-title="Общие схемы"/></ri:attachment></ac:image>
```

Алгоритм (выполняется в `sync_page_assets`, до основного цикла):

1. Собрать такие ссылки из `body_storage` (тот же парсер, отдельная функция `collect_foreign_attachment_refs(body_storage) -> list[ForeignRef]`).
2. Для каждой: `owner_id = link_index.lookup(space_key, title).page_id`. Если `None` → `AssetRecord(source=MISSING)` + warning `foreign attachment owner not resolved`.
3. `owner_attachments = client.list_attachments(owner_id)`; найти по `title == ri:filename`. Не найдено → `MISSING` + warning.
4. `safe = f"{owner_id}__{safe_filename(filename)}"`, файл кладётся в **каталог текущей страницы** `03_assets/<current_page_id>/`. Это сохраняет единую схему относительных путей и делает каталог страницы самодостаточным.
5. `AssetRecord(source=FOREIGN_ATTACHMENT, owner_page_id=owner_id, original_filename=filename, safe_filename=safe)`.

Внешние картинки (`ac:image` + `ri:url`) **не скачиваются** (§8.12) — их URL остаётся в Markdown как есть, `AssetRecord` для них не создаётся.

### 7.4. `safe_filename`

```python
def safe_filename(original: str, *, max_length: int = 150) -> str: ...
```

Алгоритм (детерминированный, кроссплатформенный: результат обязан быть валиден и на Windows, и на POSIX):

1. `name = unicodedata.normalize("NFC", original.strip())`.
2. Отбросить путевые компоненты: `name = name.replace("\\", "/").rsplit("/", 1)[-1]`.
3. Заменить каждый символ из `< > : " / \ | ? *` и все `chr(0)–chr(31)` на `_`.
4. Свернуть повторяющиеся `_` в один; удалить пробелы по краям.
5. Удалить завершающие точки и пробелы (Windows их не хранит).
6. Разделить на `stem` и `suffix` (последнее расширение, ≤ 10 символов вместе с точкой; иначе всё считается stem).
7. Если `stem.upper()` ∈ `{CON, PRN, AUX, NUL, COM1..COM9, LPT1..LPT9}` → `stem = "_" + stem`.
8. Если `len(name.encode("utf-8")) > max_length` → обрезать `stem` по байтам UTF-8 (без разрыва символа) так, чтобы итог с `suffix` уложился в `max_length`, и добавить к stem суффикс `-<sha1(original)[:8]>` для устойчивой уникальности.
9. Если результат пуст или равен `_` → `f"file-{sha1(original)[:8]}{suffix}"`.

Кириллица и пробелы в именах вложений **сохраняются** (в отличие от slug страниц): `Схема шлюза.png` → `Схема шлюза.png`. Obsidian и файловые системы это поддерживают, а сохранение исходного имени важно для узнаваемости. Экранирование пробелов при вставке в Markdown — §9.5.

### 7.5. Коллизии `safe_filename`

Внутри одной страницы карта строится последовательно по возрастанию `attachment.id`:

- если `safe` ещё не занят — берём как есть;
- если занят — `f"{stem}__{n}{suffix}"`, где `n` — минимальное целое ≥ 2, дающее свободное имя.

Карта `original → safe` фиксируется в `01_raw/<page_id>.assets.json` и является **единственным** источником для макро-движка. Пример:

```json
{
  "page_id": "109847231",
  "generated_at": "2026-08-26T10:00:05Z",
  "files": [
    {
      "attachment_id": "att123",
      "original_filename": "Схема: v2?.png",
      "safe_filename": "Схема_ v2_.png",
      "media_type": "image/png",
      "file_size": 18420,
      "sha256": "9f2b…",
      "source": "attachment",
      "owner_page_id": "109847231",
      "relative_path": "../03_assets/109847231/Схема_ v2_.png",
      "downloaded_at": "2026-08-26T10:00:05Z"
    }
  ]
}
```

### 7.6. `slugify` и layout-хелперы

```python
# src/naming.py
def slugify(title: str, *, max_length: int = 60) -> str:
    """NFKC -> unidecode -> lower -> [^a-z0-9]+ -> '-' -> trim '-' -> cut 60 -> 'page' if empty."""

def artifact_key(page_id: str) -> str:
    """f'page-{page_id}' — уже соответствует [a-z0-9-]+, т.к. page_id только цифры."""

# src/paths.py
def raw_path(s: Settings, page_id: str) -> Path: ...              # data/01_raw/<id>.json
def assets_sidecar_path(s: Settings, page_id: str) -> Path: ...   # data/01_raw/<id>.assets.json
def links_index_path(s: Settings, page_id: str) -> Path: ...      # data/01_raw/<id>.links.json
def interim_path(s: Settings, page_id: str) -> Path: ...          # data/02_interim/<id>.html
def assets_dir(s: Settings, page_id: str) -> Path: ...            # data/03_assets/<id>/
def md_filename(page_id: str, slug: str) -> str: ...              # "<id>_<slug>.md"
def md_path(s: Settings, page_id: str, slug: str) -> Path: ...    # data/04_markdown/<id>_<slug>.md

ASSET_RELATIVE_PREFIX = "../03_assets"

def asset_relative_path(page_id: str, safe_filename: str) -> str:
    """Единственная функция построения ссылки на медиа из Markdown.
    Возвращает '../03_assets/<page_id>/<safe_filename>' — всегда POSIX-разделители."""
    return f"{ASSET_RELATIVE_PREFIX}/{page_id}/{safe_filename}"
```

Точный алгоритм `slugify`:

1. `text = unicodedata.normalize("NFKC", title)`.
2. `text = unidecode(text)` (пакет `unidecode`; выбран как детерминированная и покрывающая кириллицу транслитерация: `Архитектура` → `Arkhitektura`).
3. `text = text.lower()`.
4. `text = re.sub(r"[^a-z0-9]+", "-", text)`.
5. `text = text.strip("-")`.
6. Если `len(text) > 60`: `text = text[:60].rstrip("-")`.
7. Если `text == ""`: `text = "page"`.

Примеры (обязательные тест-кейсы):

| Вход | Slug |
|---|---|
| `Архитектура интеграционного шлюза` | `arkhitektura-integratsionnogo-shliuza` |
| `Kafka / Gateway: v2 (draft)` | `kafka-gateway-v2-draft` |
| `!!!` | `page` |
| `   ` | `page` |
| `Очень длинный заголовок …` (>60 после транслита) | обрезка до ≤60 без хвостового `-` |
| `C# и .NET` | `c-i-net` |

---
## 8. Макро-движок

### 8.1. Парсер: решение и обвязка

**Решение зафиксировано: `lxml.etree` (XML-режим) для разбора Storage Format; `BeautifulSoup` используется только внутри `markdownify` на этапе HTML → Markdown.** Причины: Storage Format — well-formed XML, XML-парсер сохраняет CDATA-содержимое без искажений и корректно различает `ac:`/`ri:`-пространства; HTML-парсер молча теряет неизвестные namespace-узлы и портит `CDATA`.

Storage-фрагмент не объявляет префиксы, поэтому перед разбором он оборачивается:

```python
WRAPPER = (
    '<cmex:root xmlns:cmex="urn:cmex" '
    'xmlns:ac="http://www.atlassian.com/schema/confluence/4/ac/" '
    'xmlns:ri="http://www.atlassian.com/schema/confluence/4/ri/" '
    'xmlns:at="http://www.atlassian.com/schema/confluence/4/at/">{body}</cmex:root>'
)

def parse_storage(body_storage: str) -> etree._Element:
    """Оборачивает фрагмент, нормализует HTML-entity, парсит. Бросает StorageParseError."""
    normalized = normalize_entities(body_storage)
    parser = etree.XMLParser(recover=False, resolve_entities=False, strip_cdata=False, huge_tree=True)
    try:
        return etree.fromstring(WRAPPER.format(body=normalized).encode("utf-8"), parser)
    except etree.XMLSyntaxError:
        recovering = etree.XMLParser(recover=True, resolve_entities=False, strip_cdata=False, huge_tree=True)
        root = etree.fromstring(WRAPPER.format(body=normalized).encode("utf-8"), recovering)
        if root is None:
            raise StorageParseError("storage body is not parsable as XML") from None
        return root  # WARNING: "storage parsed in recovery mode"
```

`normalize_entities` — обязательный шаг, иначе `&nbsp;` валит XML-парсер:

```python
XML_SAFE_ENTITIES = {"amp", "lt", "gt", "quot", "apos"}
ENTITY_RE = re.compile(r"&(#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]*);")

def normalize_entities(text: str) -> str:
    """Именованные HTML-entity -> числовые ссылки; неизвестные -> экранированный '&'."""
    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name.startswith("#") or name in XML_SAFE_ENTITIES:
            return m.group(0)
        ch = html.entities.html5.get(name + ";") or html.entities.html5.get(name)
        return f"&#{ord(ch[0])};" if ch and len(ch) == 1 else "&amp;" + name + ";"
    return ENTITY_RE.sub(_sub, text)
```

Также нормализуется одиночный `&`, не образующий entity: предварительный `re.sub(r"&(?![#A-Za-z])", "&amp;", text)`.

Хелперы работы с деревом (`src/transformers/macro_handlers.py`):

```python
E = ElementMaker()   # lxml.builder, без namespace -> чистые HTML-теги

def qname(prefix: str, tag: str) -> str: ...        # "{http://.../ac/}structured-macro"
def macro_name(node: etree._Element) -> str: ...    # node.get(qname("ac","name"), "").strip().lower()
def macro_params(node: etree._Element) -> dict[str, str]:
    """{ac:parameter[@ac:name] -> нормализованный текст}. Пустое имя -> ключ ''. Регистр ключей -> lower."""
def rich_text_body(node) -> etree._Element | None: ...   # первый ac:rich-text-body
def plain_text_body(node) -> str: ...                    # текст ac:plain-text-body (CDATA включительно), '' если нет
def replace_node(node, replacement: etree._Element | list[etree._Element]) -> None:
    """Заменяет node, перенося node.tail в конец вставленного, сохраняя позицию в родителе."""
def unwrap_node(node) -> None:
    """Удаляет тег, поднимая детей и текст на место узла (с корректной склейкой text/tail)."""
def drop_node(node, *, keep_tail: bool = True) -> None: ...
def marker_nodes(ctx, comment_text: str, body: etree._Element | None = None) -> list[etree._Element]:
    """[Comment(comment_text), <p>@@CMEX_DEFER_n@@</p>] + [body], где deferred хранит тот же comment_text.
    Комментарий нужен для читаемости 02_interim, deferred-токен — чтобы маркер дошёл до Markdown."""
```

Важное ограничение инструмента: `markdownify` выбрасывает HTML-комментарии. Поэтому любой маркер, который обязан присутствовать в итоговом Markdown (`unsupported-macro`, `missing-asset`, `unresolved-page-link`), эмитится **через deferred-блок** (`DeferredKind.RAW_HTML` с полезной нагрузкой-комментарием) и дополнительно дублируется настоящим комментарием в interim HTML.

### 8.2. Порядок трансформации (нормативный, менять нельзя)

```python
def transform(page_raw: PageRaw, sidecar: AssetSidecar, link_index: LinkIndex,
              batch_page_ids: frozenset[str], settings: Settings) -> CleanHtml:
```

| Шаг | Действие |
|---|---|
| 0 | `ctx = MacroContext(...)`; карта вложений `ctx.assets = sidecar.by_original()` + регистронезависимый индекс `ctx.assets_ci` |
| 1 | `root = parse_storage(page_raw.body_storage)`; если тело пустое — сразу `CleanHtml(html="", warnings=["empty_body"])` |
| 2 | **Pass A** — макросы, `ac:image`, `ac:task-list`, `ac:emoticon`, `time`, layout-контейнеры |
| 3 | **Pass B** — `ac:link` и остаточные `ri:*` |
| 4 | **Pass C** — `html_cleaner.normalize(root, ctx)`: таблицы, ячейки, атрибуты, `|`-экранирование |
| 5 | сериализация: `etree.tostring(root, encoding="unicode", method="html")` с последующим срезом обёртки `<cmex:root>`; запись `02_interim/<page_id>.html` |

Pass A и Pass B обходят узлы в **обратном документном порядке** (`reversed(list(root.iter()))`), что гарантирует обработку вложенных макросов раньше внешних (панель внутри expand, code внутри панели).

### 8.3. Контекст и реестр

```python
@dataclass(slots=True)
class MacroContext:
    page_id: str
    page_title: str
    space_key: str
    edition: Edition
    base_url: str
    assets: dict[str, AssetRecord]          # ключ — original_filename
    assets_ci: dict[str, AssetRecord]       # ключ — original_filename.lower()
    link_index: LinkIndex
    batch_page_ids: frozenset[str]
    unsupported: set[str] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
    deferred: list[DeferredBlock] = field(default_factory=list)

    def defer(self, kind: DeferredKind, payload: str, title: str | None = None) -> str:
        """Регистрирует блок и возвращает токен '@@CMEX_DEFER_<n>@@'."""

    def find_asset(self, filename: str) -> AssetRecord | None:
        """assets[filename] -> assets_ci[filename.lower()] -> None."""

    def find_foreign_asset(self, filename: str, owner_page_id: str) -> AssetRecord | None:
        """Вложение другой страницы: первый AssetRecord, у которого
        original_filename совпадает (регистронезависимо) и owner_page_id == owner_page_id."""

    def warn(self, message: str) -> None: ...


MacroHandler = Callable[[etree._Element, MacroContext], None]

MACRO_HANDLERS: dict[str, MacroHandler] = {
    "code": handle_code, "noformat": handle_noformat,
    "plantuml": handle_plantuml, "plantumlcloud": handle_plantuml,
    "drawio": handle_drawio, "draw.io": handle_drawio,
    "info": handle_callout, "note": handle_callout, "panel": handle_callout,
    "tip": handle_callout, "success": handle_callout,
    "warning": handle_callout, "error": handle_callout,
    "expand": handle_expand, "status": handle_status, "date": handle_date,
    "view-file": handle_view_file, "viewpdf": handle_view_file, "multimedia": handle_view_file,
}

UNWRAP_MACROS: frozenset[str] = frozenset({"section", "column", "div", "align", "toc-zone"})
SILENT_DROP_MACROS: frozenset[str] = frozenset({"anchor"})
```

Диспетчер узлов (Pass A):

| Тег узла | Обработчик |
|---|---|
| `{ac}structured-macro`, `{ac}macro` | `MACRO_HANDLERS[name]` → иначе `UNWRAP_MACROS` → иначе `SILENT_DROP_MACROS` → иначе `handle_unsupported` |
| `{ac}image` | `handle_image` |
| `{ac}task-list` | `handle_task_list` |
| `{ac}emoticon` | `handle_emoticon` |
| `time` | `handle_time` |
| `{ac}layout`, `{ac}layout-section`, `{ac}layout-cell`, `{ac}adf-extension`, `{ac}inline-comment-marker` | `unwrap_node` |
| `{ac}placeholder`, `{ac}adf-fallback` | `drop_node` |

Диспетчер Pass B:

| Тег узла | Обработчик |
|---|---|
| `{ac}link` | `handle_link` |
| `{ri}page`, `{ri}attachment`, `{ri}url`, `{ri}user`, `{ri}space`, `{ri}blog-post` (остаточные) | `drop_node` + warning `orphan resource identifier: {tag}` |

---

### 8.4. Стандартный HTML

**Поиск.** Теги `p h1 h2 h3 h4 h5 h6 ul ol li table thead tbody tr th td em strong b i code pre br hr a blockquote del s sup sub span div img` не трогаются в Pass A/B и доходят до `markdownify`.

**Нормализация (Pass C).** У всех элементов удаляются атрибуты, кроме белого списка: `a[href,title]`, `img[src,alt,title]`, `pre[data-lang]`, `blockquote[data-callout]`, `td/th/tr/table` — без атрибутов. Удаляются `style`, `class` (кроме служебного `class="task-list"`), `data-highlight-colour`, все `ac:*`/`at:*` атрибуты.

**Edge cases.** `<b>`/`<i>` конвертируются `markdownify` в `**`/`*`. `<span>` и `<div>` без атрибутов остаются и схлопываются конвертером.

```xml
<p>Обычный <strong>текст</strong> и <a href="https://example.org">ссылка</a>.</p>
```

→ `Обычный **текст** и [ссылка](https://example.org).`

---

### 8.5. `code`

**Поиск.** `{ac}structured-macro` с `ac:name="code"`.

**Параметры.** `macro_params(node)`: `language` (основной), `lang` (устаревший алиас), `title`, `linenumbers`, `collapse`, `theme`.

**Алгоритм.**

1. `language = (params.get("language") or params.get("lang") or "").strip().lower()`; если пусто → `"text"`.
2. Нормализация алиасов по таблице `CODE_LANGUAGE_ALIASES`: `js→javascript`, `py→python`, `sh|bash|shell→bash`, `yml→yaml`, `ps|powershell→powershell`, `c#|csharp→csharp`, `none|plain→text`. Неизвестное значение оставляется как есть (fenced-инфо строка допускает любое слово).
3. `body = plain_text_body(node)`; если пусто → `body = ""` (§8.22, макрос без body).
4. `title` (если задан) выносится **перед** блоком как `<p><strong>{title}</strong></p>`.
5. Результат: `<pre data-lang="{language}"><code>{body}</code></pre>`, где `body` кладётся в `code.text` (lxml сам экранирует `<`, `&`).
6. `collapse=true` игнорируется в MVP (блок всегда раскрыт) — решение зафиксировано, чтобы не плодить `<details>` вокруг кода.

**Edge cases.** Тройные бэктики внутри CDATA обрабатываются на этапе конвертера (§9.3): длина ограждения = `max(3, самая длинная серия бэктиков + 1)`. Табы сохраняются. Хвостовой `\n` в теле обрезается (`body.rstrip("\n")`).

```xml
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">python</ac:parameter>
  <ac:plain-text-body><![CDATA[print("hi")]]></ac:plain-text-body>
</ac:structured-macro>
```

→

````text
```python
print("hi")
```
````

---

### 8.6. `noformat`

**Поиск.** `ac:name="noformat"`. **Алгоритм.** Как `code`, но `language` всегда `"text"`, параметр `nopanel` игнорируется.

```xml
<ac:structured-macro ac:name="noformat"><ac:plain-text-body><![CDATA[raw text]]></ac:plain-text-body></ac:structured-macro>
```

→ ` ```text ` … `raw text` … ` ``` `

---

### 8.7. `plantuml` / `plantumlcloud`

**Поиск.** `ac:name` ∈ {`plantuml`, `plantumlcloud`}.

**Алгоритм.**

1. `body = plain_text_body(node)`; если пусто — попробовать `params.get("data")`, затем `params.get("body")`.
2. Если источник найден → `<pre data-lang="plantuml"><code>{body}</code></pre>`. Картинка **не рендерится и не скачивается** (out of scope, §1.4).
3. Если источник пуст (диаграмма хранится во вложении/на сервере рендера) → `handle_unsupported(node, ctx)` с добавлением `plantuml` в `unsupported_macros` и warning `plantuml macro without inline source`.

**Edge cases.** `@startuml/@enduml` сохраняются как есть. Параметр `format`/`revision` игнорируется.

```xml
<ac:structured-macro ac:name="plantuml">
  <ac:plain-text-body><![CDATA[@startuml
A -> B
@enduml]]></ac:plain-text-body>
</ac:structured-macro>
```

→ fenced-блок с языком `plantuml`.

---

### 8.8. `drawio` / `draw.io`

**Поиск.** `ac:name` ∈ {`drawio`, `draw.io`}.

**Параметры.** `diagramname` (основной), `diagramdisplayname`, `pageid`, `revision`, `baseurl`, `width`, `height`.

**Алгоритм.**

1. `name = params.get("diagramname") or params.get("diagramdisplayname")`. Если пусто → `handle_unsupported`, `unsupported += {"drawio"}`.
2. Preview-кандидаты в порядке приоритета: `f"{name}.png"`, `f"{name}.svg"`, `f"{name}.drawio.png"`, `f"{name}.drawio.svg"`, `name` (если уже содержит расширение изображения). Поиск через `ctx.find_asset` (регистронезависимо).
3. Source-кандидаты: `f"{name}.drawio"`, `f"{name}.xml"`, `name` (если оканчивается на `.drawio`/`.xml`).
4. Вывод:
   - preview найден → `<p><img src="{relative}" alt="{display_name}"/></p>`;
   - preview найден и source найден → к тому же `<p>` добавляется ` ` + `<a href="{source_relative}">source</a>`;
   - preview не найден, source найден → только `<p><a href="{source_relative}">{display_name} (draw.io source)</a></p>` + warning `drawio preview attachment not found: {name}`;
   - ничего не найдено → `marker_nodes(ctx, f"missing-asset: {name}")` + `<p><em>{display_name}</em></p>` + warning.
5. `display_name = params.get("diagramdisplayname") or name`.

```xml
<ac:structured-macro ac:name="drawio">
  <ac:parameter ac:name="diagramName">Gateway</ac:parameter>
</ac:structured-macro>
```

При наличии вложений `Gateway.png` и `Gateway.drawio` →

```text
![Gateway](../03_assets/109847231/Gateway.png) [source](../03_assets/109847231/Gateway.drawio)
```

---

### 8.9. Callout-макросы: `info`, `note`, `panel`, `tip`, `success`, `warning`, `error`

**Поиск.** `ac:name` ∈ {`info`, `note`, `panel`, `tip`, `success`, `warning`, `error`}.

**Отображение (нормативно).**

| `ac:name` | `CalloutKind` |
|---|---|
| `info`, `note`, `panel` | `NOTE` |
| `warning`, `error` | `WARNING` |
| `tip`, `success` | `TIP` |

**Алгоритм.**

1. `kind = CALLOUT_MAP[name]`; `title = params.get("title", "").strip()`.
2. `body = rich_text_body(node)`; если `None` → `body` считается пустым (§8.22).
3. Построить `<blockquote data-callout="{kind}">`, первым ребёнком — `<p>[!{kind}]{ ' ' + title if title }</p>`, затем **все дети** `ac:rich-text-body` в исходном порядке (перенос узлов, не копирование текста).
4. Параметры `bgColor`, `borderStyle`, `icon` игнорируются (MVP).

**Edge cases.** Вложенный callout внутри callout: обрабатывается первым (обратный порядок обхода), `markdownify` даст вложенный `> >`. Пустое тело → остаётся только строка `> [!NOTE]`.

```xml
<ac:structured-macro ac:name="info">
  <ac:parameter ac:name="title">Важно</ac:parameter>
  <ac:rich-text-body><p>Читать до конца.</p></ac:rich-text-body>
</ac:structured-macro>
```

→

```text
> [!NOTE] Важно
> Читать до конца.
```

---

### 8.10. `expand`

**Поиск.** `ac:name="expand"`.

**Алгоритм.**

1. `title = params.get("title") or "Подробнее"`.
2. `body_el = rich_text_body(node)`; HTML тела сериализуется: `inner = "".join(tostring(child, method="html", encoding="unicode") for child in body_el)` (+ `body_el.text`).
3. `token = ctx.defer(DeferredKind.DETAILS, payload=inner, title=title)`.
4. Узел заменяется на `<p>{token}</p>`.
5. На post-process (§9.4) `inner` рекурсивно конвертируется в Markdown и собирается блок:

```text
<details>
<summary>Подробнее</summary>

…markdown тела…

</details>
```

Пустые строки внутри `<details>` обязательны: без них Obsidian/GFM не отрендерят вложенный Markdown.

**Edge cases.** `title` экранируется как HTML-текст (`html.escape`). Вложенный `expand` внутри `expand` работает за счёт рекурсивной конвертации.

```xml
<ac:structured-macro ac:name="expand">
  <ac:parameter ac:name="title">Детали</ac:parameter>
  <ac:rich-text-body><p>Скрытый текст</p></ac:rich-text-body>
</ac:structured-macro>
```

---

### 8.11. `ac:image` + `ri:attachment`

**Поиск.** Узел `{ac}image`, содержащий `{ri}attachment`.

**Параметры.** Атрибуты `ac:alt`, `ac:alt-text`, `ac:title`, `ac:width`, `ac:height`, `ac:align`, `ac:thumbnail`; у `ri:attachment` — `ri:filename`, `ri:version-at-save`.

**Алгоритм.**

1. `filename = ri_attachment.get(qname("ri","filename"), "").strip()`. Пусто → `drop_node` + warning `ac:image without ri:filename`.
2. Если у `ri:attachment` есть дочерний `{ri}page` → это чужое вложение: `owner_id = ctx.link_index.lookup(ri:space-key, ri:content-title).page_id`, затем `record = ctx.find_foreign_asset(filename, owner_id)` (файл лежит как `<owner_id>__<safe>` в каталоге текущей страницы, см. §7.3). Если `owner_id` не разрешён — сразу переход к шагу 6.
3. Иначе `record = ctx.find_asset(filename)`.
4. `alt = attrs ac:alt | ac:alt-text | ac:title | filename` (первое непустое).
5. Если `record` и `record.source is not AssetSource.MISSING` → `<img src="{record.relative_path}" alt="{alt}"/>`, где `relative_path == asset_relative_path(page_id, record.safe_filename)`.
6. Если `record is None` или `source == MISSING` → `marker_nodes(ctx, f"missing-asset: {filename}")` + `<span>[missing attachment: {filename}]</span>` + warning.
7. `ac:width`/`ac:height` игнорируются: GFM не имеет переносимого синтаксиса размеров, а Obsidian-специфичный `|width` ломает совместимость. Решение зафиксировано.

```xml
<ac:image ac:alt="Схема шлюза"><ri:attachment ri:filename="ArchSchema.png"/></ac:image>
```

→ `![Схема шлюза](../03_assets/109847231/ArchSchema.png)`

---

### 8.12. `ac:image` + `ri:url`

**Поиск.** `{ac}image` с дочерним `{ri}url`.

**Алгоритм.** `src = ri_url.get(qname("ri","value"))`; внешний URL **сохраняется как есть**, файл не скачивается. `alt` — по правилу §8.11.4, при отсутствии — последний сегмент пути URL. Пустой `ri:value` → `drop_node` + warning.

```xml
<ac:image><ri:url ri:value="https://cdn.example/pic.png"/></ac:image>
```

→ `![pic.png](https://cdn.example/pic.png)`

---

### 8.13. `ri:attachment` в ссылке и файловые макросы (`view-file`, `viewpdf`, `multimedia`)

**Поиск.** (а) `{ac}link` с дочерним `{ri}attachment` (обрабатывается в `handle_link`, §8.16); (б) `{ac}structured-macro` с `ac:name` ∈ {`view-file`, `viewpdf`, `multimedia`}, содержащий `{ri}attachment` внутри `ac:parameter[@ac:name="name"]`.

**Алгоритм (б).**

1. Найти первый `{ri}attachment` среди потомков; `filename = ri:filename`.
2. `record = ctx.find_asset(filename)`.
3. Найден → `<p><a href="{record.relative_path}">{filename}</a></p>`.
4. Не найден → `marker_nodes(ctx, f"missing-asset: {filename}")` + `<p><em>[missing attachment: {filename}]</em></p>` + warning.
5. Если `ri:attachment` вообще нет → `handle_unsupported`.

```xml
<ac:structured-macro ac:name="view-file">
  <ac:parameter ac:name="name"><ri:attachment ri:filename="Отчёт.pdf"/></ac:parameter>
</ac:structured-macro>
```

→ `[Отчёт.pdf](../03_assets/109847231/Отчёт.pdf)`

---

### 8.14. `status`

**Поиск.** `ac:name="status"`.

**Алгоритм.** `title = params.get("title", "").strip()`; `colour` **игнорируется** (MVP). Результат — `<code>{title.upper()}</code>`. Пустой `title` → `<code>UNKNOWN</code>` + warning `status macro without title`.

```xml
<ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">Green</ac:parameter>
  <ac:parameter ac:name="title">Готово</ac:parameter>
</ac:structured-macro>
```

→ `` `ГОТОВО` ``

---

### 8.15. `ac:task-list` / `ac:task`

**Поиск.** `{ac}task-list`; дети `{ac}task` с `{ac}task-status` (`complete`/`incomplete`) и `{ac}task-body`.

**Алгоритм.**

1. Создать `<ul class="task-list">`.
2. Для каждого `{ac}task`: `checked = (task-status.text or "").strip().lower() == "complete"`; префикс `"[x] "` либо `"[ ] "`.
3. `<li>` получает текстовый префикс (в `li.text`), затем переносятся все дети `{ac}task-body`.
4. `{ac}task-id` игнорируется. Задача без `task-body` → `<li>[ ] </li>` + warning.

**Edge cases.** Вложенные task-list внутри `task-body` обрабатываются раньше (обратный обход) и дают вложенный список. `class="task-list"` — единственный `class`, сохраняемый нормализатором (§8.4).

```xml
<ac:task-list>
  <ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Сделано</ac:task-body></ac:task>
  <ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>В работе</ac:task-body></ac:task>
</ac:task-list>
```

→

```text
- [x] Сделано
- [ ] В работе
```

---

### 8.16. `ac:link` (внутренние ссылки)

**Поиск.** Узел `{ac}link` в Pass B. Атрибут `ac:anchor` — опциональный якорь.

**Текст ссылки** `label` определяется по первому непустому источнику:

1. `ac:plain-text-link-body` (CDATA);
2. текстовое содержимое `ac:link-body` (с сохранением inline-разметки: дети переносятся в `<a>`);
3. `ri:content-title` (для `ri:page`) / `ri:filename` (для `ri:attachment`) / `ri:username`/`ri:account-id` (для `ri:user`);
4. `ac:anchor`;
5. литерал `link`.

#### 8.16.1. `ri:page`

1. `title = ri:content-title`, `space = ri:space-key or ctx.space_key`.
2. Если `title` пуст и есть `ac:anchor` → внутристраничная ссылка `<a href="#{anchor}">{label}</a>`.
3. `target = ctx.link_index.lookup(space, title)`.
4. `page_id = target.page_id if target else None`.
5. Ветвление:
   - `page_id in ctx.batch_page_ids` → `href = f"cmex://page/{page_id}"` (+ `f"#{anchor}"`), финализируется в §10.6 в `./<id>_<slug>.md`;
   - `page_id` известен, но не в батче → `href = target.absolute_url` (+ `#anchor`), то есть абсолютный `source_url` цели;
   - `page_id is None` → `marker_nodes(ctx, f"unresolved-page-link: {space}/{title}")` + `<strong>{label}</strong>` + warning.

```xml
<ac:link><ri:page ri:space-key="ARCH" ri:content-title="Kafka Gateway"/>
  <ac:plain-text-link-body><![CDATA[см. шлюз]]></ac:plain-text-link-body></ac:link>
```

→ цель в батче: `[см. шлюз](./109847232_kafka-gateway.md)`; цель вне батча: `[см. шлюз](https://confluence.example/pages/viewpage.action?pageId=109847232)`.

#### 8.16.2. `ri:attachment`

`record = ctx.find_asset(ri:filename)` → `<a href="{record.relative_path}">{label}</a>`; не найден → маркер `missing-asset` + `<em>[missing attachment: {filename}]</em>` + warning. Если у `ri:attachment` есть `{ri}page` — применяется правило чужого вложения (§7.3).

#### 8.16.3. `ri:user`

`label = "@" + (ri:username or displayName-из-link-body or ri:account-id or "unknown")`. Результат — `<span>@v.petrov</span>` (без гиперссылки: URL профиля различается между редакциями и не нужен для RAG).

```xml
<ac:link><ri:user ri:username="v.petrov"/></ac:link>
```

→ `@v.petrov`

#### 8.16.4. `ri:url`, `ri:space`, `ri:blog-post`, прочее

- `ri:url` → `<a href="{ri:value}">{label}</a>`.
- `ri:space` → `<a href="{base}/display/{key}">{label}</a>` (DC) / `<a href="{base}/wiki/spaces/{key}">{label}</a>` (Cloud).
- `ri:blog-post`, `ri:content-entity` и любые прочие → `<strong>{label}</strong>` + маркер `unresolved-link: {tag}` + warning (out of scope MVP).
- `{ac}link` без дочерних `ri:*`, но с `ac:anchor` → `<a href="#{anchor}">{label}</a>`.
- `{ac}link` вообще без данных → `unwrap_node` + warning.

---

### 8.17. `ac:emoticon`

**Поиск.** `{ac}emoticon`. Атрибуты: `ac:name`, `ac:emoji-shortname`, `ac:emoji-fallback`, `ac:emoji-id`.

**Алгоритм.** Порядок приоритета: `ac:emoji-fallback` (готовый unicode-символ) → `EMOTICON_MAP[ac:name]` → `ac:emoji-shortname` (вида `:smile:`) → `f":{ac:name}:"`. Результат вставляется как текст (не элемент), склеиваясь с `text`/`tail` соседей.

**Таблица `EMOTICON_MAP` (полная, нормативная).**

| `ac:name` | Символ | | `ac:name` | Символ |
|---|---|---|---|---|
| `smile` | 🙂 | | `warning` | ⚠️ |
| `sad` | 🙁 | | `plus` | ➕ |
| `cheeky` | 😜 | | `minus` | ➖ |
| `laugh` | 😄 | | `question` | ❓ |
| `wink` | 😉 | | `light-on` | 💡 |
| `thumbs-up` | 👍 | | `light-off` | 🔌 |
| `thumbs-down` | 👎 | | `yellow-star` | ⭐ |
| `information` | ℹ️ | | `red-star` | 🌟 |
| `tick` | ✅ | | `green-star` | ✳️ |
| `cross` | ❌ | | `blue-star` | 💠 |
| `heart` | ❤️ | | `broken-heart` | 💔 |

```xml
<p>Готово <ac:emoticon ac:name="tick"/></p>
```

→ `Готово ✅`

---

### 8.18. `time` и макрос `date`

**Поиск.** Тег `time` (без namespace, атрибут `datetime`) и `{ac}structured-macro` с `ac:name="date"`.

**Алгоритм.**

1. `raw = node.get("datetime")` для `time`; для макроса — первый непустой из `params["date"]`, `params["datetime"]`, `params["value"]`, `plain_text_body(node)`.
2. `value = normalize_date_text(raw)`: если строка матчит `^\d{4}-\d{2}-\d{2}` → взять первые 10 символов; иначе попытка `datetime.fromisoformat` → `%Y-%m-%d`; при неудаче — исходная строка + warning `unparsable date: {raw}`.
3. Замена узла на текст `value` (склейка с `tail`).

```xml
<p>Дедлайн: <time datetime="2026-04-12"/></p>
```

→ `Дедлайн: 2026-04-12`

---

### 8.19. Layout-контейнеры и служебные узлы

| Узел | Действие | Причина |
|---|---|---|
| `{ac}layout`, `{ac}layout-section`, `{ac}layout-cell` | `unwrap_node` | колонки не выражаются в GFM; содержимое сохраняется в порядке следования ячеек |
| макросы `section`, `column`, `div`, `align`, `toc-zone` | `unwrap_node` тела `ac:rich-text-body` | то же |
| `{ac}inline-comment-marker` | `unwrap_node` | inline-комментарии не экспортируются, текст сохраняется |
| `{ac}placeholder` | `drop_node` | это подсказка редактора, не контент |
| `{ac}adf-extension` | `unwrap_node` | Cloud-обёртка над макросом |
| `{ac}adf-fallback` | `drop_node` | дублирует содержимое `adf-extension` |
| макрос `anchor` | `drop_node` (без маркера) | невизуальный якорь; шум в Markdown не нужен |

---

### 8.20. Fallback неизвестного макроса

```python
def handle_unsupported(node: etree._Element, ctx: MacroContext) -> None: ...
```

**Алгоритм.**

1. `name = macro_name(node) or "unknown"`; `ctx.unsupported.add(name)`.
2. Извлечение содержимого **строго** из `ac:rich-text-body` и `ac:plain-text-body`; `ac:parameter` игнорируются (иначе в текст утекают технические значения вида `true`, `sortBy=modified`).
3. Формируется результат:
   - комментарий `<!-- unsupported-macro: {name} -->` (в interim HTML) + deferred-токен с тем же текстом (чтобы маркер дошёл до Markdown);
   - если есть `rich-text-body` → `<div class="unsupported-macro-body">` с перенесёнными детьми;
   - если есть только `plain-text-body` → `<p>{text}</p>`;
   - если тела нет — только маркер.
4. `ctx.warn(f"unsupported macro: {name}")`.
5. Пайплайн не падает **никогда**: любое исключение внутри обработчика перехватывается диспетчером, узел заменяется маркером `<!-- macro-error: {name} -->`, warning уходит в отчёт.

Итог в Markdown:

```html
<!-- unsupported-macro: jira -->
```

плюс извлечённый текст, а имя `jira` попадает в `unsupported_macros` frontmatter.

```xml
<ac:structured-macro ac:name="jira">
  <ac:parameter ac:name="key">ARCH-42</ac:parameter>
  <ac:plain-text-body><![CDATA[ARCH-42: миграция]]></ac:plain-text-body>
</ac:structured-macro>
```

→

```text
<!-- unsupported-macro: jira -->

ARCH-42: миграция
```

Известный список макросов, гарантированно попадающих в fallback (проверяется тестом): `toc`, `children`, `pagetree`, `include`, `excerpt`, `excerpt-include`, `jira`, `jiraissues`, `widget`, `roadmap`, `gallery`, `contentbylabel`, `recently-updated`, `chart`, `livesearch`, `profile`.

---

### 8.21. Нормализация таблиц и ячеек (Pass C)

Модуль `src/transformers/html_cleaner.py`:

```python
def normalize(root: etree._Element, ctx: MacroContext) -> None: ...
```

Порядок операций:

1. **Вложенные таблицы.** Если `table` содержит потомка `table` — вся внешняя таблица сериализуется в HTML и заменяется на `<p>{ctx.defer(RAW_HTML, html)}</p>`. Обоснование: GFM не поддерживает вложенные таблицы, а сырой HTML корректно рендерится и в Obsidian, и в большинстве Markdown-движков.
2. **Заголовок.** Если в таблице нет ни одного `th` — все ячейки первой строки переименовываются `td` → `th` (в Confluence первая строка почти всегда заголовок). Если строк нет — таблица удаляется + warning `empty table dropped`.
3. **`colspan`/`rowspan`.** Атрибуты **удаляются** без объединения ячеек; строки дополняются пустыми `<td/>` до максимальной длины строки в таблице. Данные не теряются, структура упрощается; падение недопустимо (§8.22, случай E7).
4. **Блочная разметка в ячейках.** Внутри `th`/`td`: каждый `p` заменяется на свои дети + `<br/>` (кроме последнего); `ul`/`ol` → элементы `li` в виде `• текст` + `<br/>`; `pre` → `<code>` с заменой `\n` на пробел; `blockquote` → `unwrap`. Вложенные `details`/deferred-токены в ячейках остаются токенами (в Markdown вставится HTML).
5. **Экранирование `|`.** Во всех текстовых узлах внутри `th`/`td` символ `|` заменяется на `\|` (иначе ломается pipe-таблица; `markdownify` с `escape_misc=False` этого не делает).
6. **Атрибуты.** Применяется белый список §8.4.
7. **Пустые узлы.** `p`, `span`, `div`, `li` без текста и детей удаляются; `<br/>` в конце ячейки удаляется.

```xml
<table><tbody>
  <tr><td>Ключ</td><td>Значение</td></tr>
  <tr><td colspan="2">A|B</td></tr>
</tbody></table>
```

→

```text
| Ключ | Значение |
| --- | --- |
| A\|B |  |
```

---

### 8.22. Краевые случаи (нормативно; каждый — тест-кейс §12)

| № | Случай | Поведение |
|---|---|---|
| E1 | `body_storage == ""` или только пробелы | `CleanHtml(html="")`, warning `empty_body`; md = frontmatter + `# {title}`; статус `ok` |
| E2 | Макрос без body (`code`, `expand`, `panel`) | обработчик отрабатывает с пустым телом; для `code` — пустой fenced-блок; падений нет |
| E3 | CDATA с ` ``` ` внутри `code` | ограждение расширяется до 4+ бэктиков (§9.3) |
| E4 | Два вложения с одинаковым `title` | берётся запись с максимальным `version` (§6.4.2); второе не попадает в sidecar |
| E5 | Разные вложения дают одинаковый `safe_filename` | коллизия разрешается суффиксом `__2` (§7.5) |
| E6 | Вложение с другой страницы | §7.3, файл `<owner_id>__<safe>` в каталоге текущей страницы |
| E7 | `colspan`/`rowspan` | §8.21.3, упрощение без объединения |
| E8 | HTML-entities в `title` страницы | `html.unescape` при маппинге (§6.4); в YAML пишется уже расшифрованный текст |
| E9 | `&nbsp;` и прочие entity в body | §8.1 `normalize_entities`; в Markdown `\u00a0` → обычный пробел (§9.4) |
| E10 | `status=trashed` / 404 | `PageResult(skipped, trashed|not_found)`, запись в `run_report.json`, файлы не трогаются |
| E11 | 403 | `PageResult(failed, forbidden)`, без ретраев |
| E12 | Битый XML | попытка recovery-парсинга; полный провал → `PageResult(failed, parse_error)` |
| E13 | Неизвестный макрос | §8.20, `unsupported_macros`, пайплайн жив |
| E14 | Внутренняя ссылка на несуществующую страницу | `<strong>label</strong>` + маркер `unresolved-page-link` |
| E15 | Вложенная таблица | §8.21.1, сырой HTML-блок |
| E16 | Изображение без `ri:filename` | узел удаляется, warning |
| E17 | Вложение не скачалось | `AssetSource.MISSING`, маркер `missing-asset`, страница `ok` |
| E18 | Дубликат URL во входном файле | схлопывание + WARNING, `UrlBatch.duplicates` |

---
## 9. HTML → Markdown

### 9.1. Решение по библиотеке

**Зафиксировано: `markdownify>=0.13,<1.0`** (тянет `beautifulsoup4`, парсер `lxml` уже в зависимостях). Причины: поддержка GFM-таблиц, ATX-заголовков, настраиваемое экранирование и возможность точечно переопределить конвертеры через подкласс `MarkdownConverter`. Ручной генератор Markdown не пишется.

### 9.2. Конвертер

```python
# src/transformers/md_converter.py
from markdownify import MarkdownConverter

MD_OPTIONS: dict[str, object] = {
    "heading_style": "ATX",          # # H1, ## H2 …
    "bullets": "-",                  # единый маркер списка
    "strong_em_symbol": "*",
    "newline_style": "BACKSLASH",    # <br> -> '\' в конце строки: устойчиво к strip() пробелов
    "escape_asterisks": True,
    "escape_underscores": False,     # иначе имена файлов и идентификаторы обрастают '\_'
    "escape_misc": False,            # иначе '[x]' в task-list и '|' в таблицах ломаются
    "autolinks": False,              # всегда явный [text](url)
    "wrap": False,                   # без переноса по ширине: диффы стабильнее
    "code_language": "",
    "keep_inline_images_in": ["a", "p", "li", "td", "th", "span", "div"],
    "sub_symbol": "",
    "sup_symbol": "",
}


class ConfluenceMarkdownConverter(MarkdownConverter):
    """Переопределяет только то, что markdownify делает не так, как нужно проекту.
    Опции передаются в конструктор из MD_OPTIONS, класс Options не переопределяется."""

    def convert_pre(self, el, text, parent_tags=None) -> str:
        """Fenced-блок с языком из data-lang и динамической длиной ограждения."""
        code = el.get_text()
        if not code.strip():
            return "\n\n```text\n```\n\n"
        language = (el.get("data-lang") or "text").strip()
        longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
        fence = "`" * max(3, longest + 1)
        return f"\n\n{fence}{language}\n{code.rstrip()}\n{fence}\n\n"

    def convert_img(self, el, text, parent_tags=None) -> str:
        src = md_url(el.get("src", ""))
        alt = (el.get("alt") or "").replace("]", r"\]")
        return f"![{alt}]({src})"

    def convert_a(self, el, text, parent_tags=None) -> str:
        href = md_url(el.get("href", ""))
        label = (text or el.get_text() or href).strip() or href
        return f"[{label}]({href})"


def md_url(url: str) -> str:
    """URL с пробелами/скобками оборачивается в <>, как разрешает GFM.
    Кириллица не percent-кодируется — так путь остаётся читаемым и совпадает с именем файла."""
    if re.search(r"[\s()<>]", url):
        return "<" + url.replace("<", "%3C").replace(">", "%3E") + ">"
    return url


def html_to_markdown(html: str) -> str:
    return ConfluenceMarkdownConverter(**MD_OPTIONS).convert(html)
```

Подпись `convert_*(self, el, text, parent_tags=None)` совместима и с 0.13.x, и с 0.14.x (в 0.13 третий аргумент не передаётся, поэтому у него есть значение по умолчанию).

### 9.3. Обработка кода

Ограждение считается по фактическому содержимому: `fence = "`" * max(3, longest_backtick_run + 1)`. Это единственное место, где решается краевой случай E3. Внутри `pre`/`code` `markdownify` не применяет экранирование, поэтому `*`, `_`, `|` остаются как есть.

### 9.4. Post-process (строгий порядок)

```python
def postprocess(markdown: str, deferred: list[DeferredBlock]) -> str: ...
```

| # | Шаг | Реализация |
|---|---|---|
| 1 | Подстановка deferred-блоков | для каждого токена `@@CMEX_DEFER_<n>@@`: `RAW_HTML` → `payload` как есть; `DETAILS` → блок из §8.10 с рекурсивным `html_to_markdown(payload)` и последующим `postprocess` (рекурсия ограничена глубиной 5, дальше — payload как HTML) |
| 2 | Схлопывание callout-заголовка | `re.sub(r"^(> \[![A-Z]+\][^\n]*)\n>\s*\n", r"\1\n", md, flags=re.M)` |
| 3 | Пустая строка после callout-заголовка без тела | `re.sub(r"^(> \[![A-Z]+\][^\n]*)\n(?!>)", r"\1\n\n", md, flags=re.M)` |
| 4 | NBSP → пробел | замена `\u00a0`, `\u202f`, `\u2007` на ` ` **вне** fenced-блоков (сегментация по строкам с трекингом состояния fence) |
| 5 | Zero-width символы | удаление `\u200b`, `\u200c`, `\u200d`, `\ufeff` вне fenced-блоков |
| 6 | Хвостовые пробелы | `re.sub(r"[ \t]+$", "", line)` вне fenced-блоков (безопасно, т.к. `newline_style="BACKSLASH"`) |
| 7 | Сжатие пустых строк | 3 и более `\n` → `\n\n` вне fenced-блоков |
| 8 | Нормализация переводов строк | CRLF/CR → LF |
| 9 | Финальный вид | `md.strip() + "\n"` |

### 9.5. Сборка итогового файла

```python
def render_markdown(page_raw: PageRaw, clean: CleanHtml, sidecar: AssetSidecar) -> RenderedPage: ...
```

1. `body = postprocess(html_to_markdown(clean.html), clean.deferred)` (для пустого `clean.html` → `body = ""`).
2. `frontmatter = build_frontmatter(page_raw, sorted(set(clean.unsupported_macros)), attachments_count=len(sidecar.files))`.
3. `slug = slugify(page_raw.title)`; `path = md_path(settings, page_raw.page_id, slug)`.
4. Содержимое файла:

```text
---
<yaml>
---

# <title>

<body>
```

`# <title>` вставляется всегда (даже при пустом теле): это даёт стабильный H1 для чанкинга в RAG и человекочитаемый заголовок в Obsidian.
5. Запись через `write_atomic` (LF, UTF-8 без BOM).
6. Если существуют старые md-файлы этой же страницы с другим slug (`04_markdown/<page_id>_*.md`, не равные целевому) — они удаляются, warning `stale markdown removed: {name}`. Иначе смена заголовка страницы плодит дубли.
7. `preview` для Prefect-артефакта: `f"### {title}\n\n```yaml\n{yaml}```\n\n{body[:500]}"`, итог обрезается до 1200 символов. Секретов в нём нет по построению (frontmatter не содержит токенов).

Пример полного результата (сокращённо):

```markdown
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
  - architecture
breadcrumbs:
  - "Главная"
  - "Проекты 2026"
  - "Архитектура интеграционного шлюза"
attachments_count: 3
unsupported_macros:
  - toc
---

# Архитектура интеграционного шлюза

<!-- unsupported-macro: toc -->

> [!NOTE] Важно
> Схема актуальна на релиз 2026.2.

![Схема шлюза](../03_assets/109847231/ArchSchema.png)

| Компонент | Назначение |
| --- | --- |
| gateway | маршрутизация |

- [x] Согласовано с ИБ
- [ ] Нагрузочное тестирование

См. также [Kafka Gateway](./109847232_kafka-gateway.md).
```

---

## 10. Prefect graph

### 10.1. Импорты (только Prefect 3 API)

```python
from datetime import timedelta

from prefect import flow, task
from prefect.artifacts import create_markdown_artifact, create_table_artifact
from prefect.cache_policies import INPUTS, TASK_SOURCE
from prefect.logging import get_run_logger
from prefect.task_runners import ThreadPoolTaskRunner
```

Запрещено использовать API Prefect 2: `cache_key_fn`, `task_runner=ConcurrentTaskRunner()` из старых путей импорта, `prefect.context.get_run_context().task_run.name` для логирования, `create_markdown_artifact` из `prefect.artifacts.core`. Логирование внутри тасок и flow — **только** `get_run_logger()`; `print` и корневой `logging` в `flows/*` не используются.

### 10.2. Граф

```text
export_confluence_batch (@flow, task_runner=ThreadPoolTaskRunner(max_workers=EXPORT_CONCURRENCY))
├── parse_and_validate_urls(input_file)                     -> UrlBatch
├── for target in batch.targets:  process_page.submit(...)  -> PrefectFuture[PageResult]
│     └── process_page (@task, изоляция ошибок)
│           ├── fetch_page_raw(target, force_refresh)                       -> FetchOutcome
│           ├── sync_page_assets(page_raw, mode, link_index)                -> AssetSidecar
│           ├── transform_storage_to_clean_html(page_raw, sidecar, links)   -> CleanHtml
│           └── render_final_markdown(page_raw, clean, sidecar)             -> RenderedPage
│                 └── create_markdown_artifact(key=f"page-{page_id}")
└── write_manifest_and_report(results, batch, started_at, force_refresh)    -> RunReport
      └── create_table_artifact(key="run-summary")
```

`process_page` — таска, вызывающая вложенные таски (Prefect 3 поддерживает nested tasks). Это даёт и изоляцию ошибок на уровне страницы, и индивидуальные политики ретраев на сетевых шагах.

### 10.3. Сигнатуры и параметры декораторов

```python
# src/flows/tasks.py

@task(
    name="parse-and-validate-urls",
    description="Читает input-файл, парсит URL, резолвит title-формы, дедуплицирует",
    retries=0,
    persist_result=False,
)
def parse_and_validate_urls(input_file: str) -> UrlBatch: ...


@task(
    name="fetch-page-raw",
    retries=3,
    retry_delay_seconds=[5, 15, 45],
    persist_result=True,
    cache_policy=INPUTS + TASK_SOURCE,
    cache_expiration=timedelta(hours=1),
    timeout_seconds=600,
)
def fetch_page_raw(target: PageTarget, force_refresh: bool) -> FetchOutcome: ...


@task(
    name="sync-page-assets",
    retries=2,
    retry_delay_seconds=[5, 20],
    persist_result=True,
    cache_policy=INPUTS + TASK_SOURCE,
    cache_expiration=timedelta(hours=1),
    timeout_seconds=1800,
)
def sync_page_assets(page_raw: PageRaw, mode: FetchMode, link_index: LinkIndex) -> AssetSidecar: ...


@task(
    name="transform-storage-to-clean-html",
    retries=1,
    retry_delay_seconds=5,
    persist_result=False,
)
def transform_storage_to_clean_html(
    page_raw: PageRaw,
    sidecar: AssetSidecar,
    link_index: LinkIndex,
    batch_page_ids: list[str],
) -> CleanHtml: ...


@task(
    name="render-final-markdown",
    retries=1,
    retry_delay_seconds=5,
    persist_result=False,
)
def render_final_markdown(page_raw: PageRaw, clean: CleanHtml, sidecar: AssetSidecar) -> RenderedPage: ...


@task(
    name="process-page",
    retries=0,
    persist_result=False,
)
def process_page(target: PageTarget, batch_page_ids: list[str], force_refresh: bool) -> PageResult: ...


@task(
    name="write-manifest-and-report",
    retries=0,
    persist_result=False,
)
def write_manifest_and_report(
    results: list[PageResult],
    batch: UrlBatch,
    started_at: str,
    force_refresh: bool,
) -> RunReport: ...
```

Таблица политик выше нормативна: `retries`, `retry_delay_seconds`, `persist_result` и `cache_policy` каждой таски меняются только через `spec-patch`. Дополнительные правила:

1. **`Settings` и `ConfluenceClient` никогда не являются аргументами таски.** Настройки читаются внутри через `get_settings()`, клиент создаётся внутри `fetch_page_raw`/`sync_page_assets` контекстным менеджером (`with ConfluenceClient(get_settings()) as client:`). Причины: живой `httpx.Client` не сериализуется, а параметры тасок сохраняются в Prefect API — токен туда попадать не должен.
2. `batch_page_ids` передаётся как **отсортированный `list[str]`** (не `frozenset`) — иначе ключ кэша нестабилен и параметр не сериализуется.
3. `force_refresh` входит в аргументы `fetch_page_raw`, поэтому при `--force-refresh` меняется ключ `INPUTS` и Prefect-кэш не может отдать старый результат.
4. Prefect-кэш — **вторичный** слой: он экономит повторные вызовы внутри часа при одинаковых входах, но решение о скачивании принимает disk-skip (§3.2, §10.4). При включённом `persist_result=True` результаты складываются в локальный result store Prefect по умолчанию; отдельная настройка storage не требуется.
5. `timeout_seconds` у `sync_page_assets` рассчитан на крупные вложения; при срабатывании таймаута страница получает `failed/network_error`.

### 10.4. `process_page` — изоляция ошибок

```python
def process_page(target: PageTarget, batch_page_ids: list[str], force_refresh: bool) -> PageResult:
    logger = get_run_logger()
    started = time.perf_counter()
    try:
        outcome = fetch_page_raw(target, force_refresh)
        if outcome.mode is FetchMode.ABSENT:
            return PageResult(raw_input=target.raw_input, page_id=target.page_id,
                              status=ResultStatus.SKIPPED, reason=outcome.reason,
                              duration_seconds=time.perf_counter() - started)
        page_raw = outcome.page_raw
        sidecar = sync_page_assets(page_raw, outcome.mode, outcome.link_index)
        if outcome.mode is FetchMode.DISK_SKIP and artifacts_are_complete(page_raw, sidecar):
            return PageResult(..., status=ResultStatus.SKIPPED, reason=FailureReason.UP_TO_DATE,
                              manifest_item=build_manifest_item(page_raw, status="skipped"))
        clean = transform_storage_to_clean_html(page_raw, sidecar, outcome.link_index, batch_page_ids)
        rendered = render_final_markdown(page_raw, clean, sidecar)
        create_markdown_artifact(key=artifact_key(page_raw.page_id),
                                 markdown=rendered.preview, description=page_raw.title)
        return PageResult(..., status=ResultStatus.OK,
                          manifest_item=build_manifest_item(page_raw, status="ok"))
    except ForbiddenError as exc:
        return _failed(target, FailureReason.FORBIDDEN, exc, started)
    except NotFoundError as exc:
        return _skipped(target, FailureReason.NOT_FOUND, started)
    except (AuthError, RateLimitError, HttpError, NetworkError) as exc:
        return _failed(target, exc.reason, exc, started)
    except StorageParseError as exc:
        return _failed(target, FailureReason.PARSE_ERROR, exc, started)
    except OSError as exc:
        return _failed(target, FailureReason.IO_ERROR, exc, started)
    except Exception as exc:  # noqa: BLE001 — последний барьер, батч не должен падать
        logger.exception("unexpected failure on page %s", target.page_id)
        return _failed(target, FailureReason.RENDER_ERROR, exc, started)
```

`artifacts_are_complete(page_raw, sidecar)` — предикат ветки D8: `interim_path(...).exists() and md_path(..., slugify(title)).exists() and all(rec.source is MISSING or (assets_dir/rec.safe_filename).exists() for rec in sidecar.files)`.

`_failed` формирует `error` через `sanitize_error(exc)`: берётся `type(exc).__name__ + ": " + str(exc)`, из строки вырезаются значение токена и заголовок `Authorization` (защита от утечки при нестандартных сообщениях httpx), длина обрезается до 500 символов.

**Никакое исключение не покидает `process_page`.** Таска всегда завершается `Completed` с `PageResult`; статус страницы виден в `PageResult.status`, отчёте и артефакте сводки.

### 10.5. Flow, concurrency и failure policy

```python
# src/flows/export_flow.py

@flow(
    name="export-confluence-batch",
    description="Экспорт страниц Confluence в Markdown (bronze/silver/assets/gold)",
    log_prints=False,
)
def export_confluence_batch(
    input_file: str | None = None,
    output_dir: str | None = None,
    force_refresh: bool | None = None,
) -> RunReport:
    logger = get_run_logger()
    settings = apply_flow_overrides(input_file, output_dir, force_refresh)   # см. ниже
    started_at = utcnow_iso()

    batch = parse_and_validate_urls(str(settings.export_input_file))
    logger.info("targets=%d invalid=%d duplicates=%d",
                len(batch.targets), len(batch.invalid), len(batch.duplicates))

    page_ids = sorted(batch.batch_page_ids)
    force = settings.export_force_refresh
    futures = [process_page.submit(t, page_ids, force) for t in batch.targets]
    results: list[PageResult] = []
    for target, future in zip(batch.targets, futures, strict=True):
        try:
            results.append(future.result(raise_on_failure=True))
        except Exception as exc:  # noqa: BLE001 — страховка: таска упала вопреки try/except внутри
            logger.error("process_page crashed for %s: %s", target.page_id, sanitize_error(exc))
            results.append(PageResult(raw_input=target.raw_input, page_id=target.page_id,
                                      status=ResultStatus.FAILED, reason=FailureReason.RENDER_ERROR,
                                      error=sanitize_error(exc)))

    report = write_manifest_and_report(results, batch, started_at, force)
    if report.failed > 0 and report.ok == 0:
        raise RuntimeError(f"all {report.failed} pages failed; see {settings.run_report_path}")
    return report
```

Параметры flow существуют для запуска из Prefect UI/деплоя и для явности; при вызове из CLI они уже согласованы с настройками. Согласование делает единственная функция:

```python
def apply_flow_overrides(input_file: str | None, output_dir: str | None, force_refresh: bool | None) -> Settings:
    """Если параметры flow отличаются от текущих Settings — применяет их через set_settings().
    Возвращает актуальный объект настроек. Значения None означают «не переопределять»."""
    current = get_settings()
    updates: dict[str, object] = {}
    if input_file is not None and Path(input_file) != current.export_input_file:
        updates["export_input_file"] = Path(input_file)
    if output_dir is not None and Path(output_dir) != current.export_output_dir:
        updates["export_output_dir"] = Path(output_dir)
    if force_refresh is not None and force_refresh != current.export_force_refresh:
        updates["export_force_refresh"] = force_refresh
    if updates:
        current = current.model_copy(update=updates)
        set_settings(current)
        ensure_layout(current)
    return current
```

**Concurrency.** Параллелизм задаётся task runner'ом при запуске из CLI:

```python
runner = ThreadPoolTaskRunner(max_workers=settings.export_concurrency)
report = export_confluence_batch.with_options(task_runner=runner)(
    input_file=args.input, output_dir=args.output, force_refresh=args.force_refresh
)
```

`with_options` вместо параметра в декораторе — потому что значение приходит из `Settings`, которые нельзя читать на этапе импорта модуля (иначе `--help` падает без `.env`). Транспорт синхронный (`httpx.Client`) и потокобезопасен; async-вариант в MVP не используется, смешивать sync и async запрещено.

**Failure policy.**

| Ситуация | Состояние flow | Exit code |
|---|---|---|
| `failed == 0` и `invalid_urls == []` | `Completed` | 0 |
| `ok >= 1`, есть `failed` или `invalid_urls` | `Completed` | 1 |
| `ok == 0`, `failed >= 1` | `Failed` (исключение после записи отчёта) | 1 |
| `ok == 0`, `failed == 0`, `skipped >= 1` | `Completed` | 0 |
| ошибка конфигурации/`AuthError` до старта | flow не запускается | 2 |

`manifest.json` и `run_report.json` пишутся **до** возможного `raise`, поэтому диагностика доступна и при полном провале батча.

### 10.6. `write_manifest_and_report`

Алгоритм:

1. Собрать `items = [r.manifest_item for r in results if r.manifest_item]`; для `failed` создать `ManifestItem` с `status="failed"`, `error=r.error`, `md_path`/`assets_dir` — фактические или `""`.
2. Построить карту `page_id → md_filename` по `items` со статусами `ok`/`skipped`.
3. **`fixup_internal_links`**: для каждой страницы со `status == "ok"` прочитать её md-файл и заменить все вхождения `cmex://page/<id>`:
   - `id` есть в карте → `./<id>_<slug>.md`;
   - `id` отсутствует (страница батча упала) → абсолютный URL `canonical_page_url(id)`;
   - оставшиеся (теоретически невозможные) вхождения → абсолютный URL + warning.
   Регексп: `r"cmex://page/(\d+)"`. Файл перезаписывается через `write_atomic` только если содержимое изменилось.
4. Записать `04_markdown/manifest.json`: `json.dumps(items, ensure_ascii=False, indent=2)`, отсортировано по `id` как по числу.
5. Записать `run_report.json` c `RunReport` (§4.6); `finished_at = utcnow_iso()`.
6. `create_table_artifact(key="run-summary", table=[...])` — по одной строке на страницу с колонками `page_id`, `title`, `status`, `reason`, `attachments`, `unsupported_macros`, `duration_s`; секретов в таблице нет.
7. Вернуть `RunReport`.

Ограничение, принятое осознанно: `fixup_internal_links` правит только страницы, отрендеренные в текущем запуске. Если ранее выгруженная страница ссылается на страницу, у которой изменился заголовок (а значит slug), ссылка станет устаревшей до следующего `--force-refresh`. Зафиксировано в §14 (R-09).

---

## 11. CLI и конфигурация

### 11.1. CLI-контракт

```text
uv run python -m src.flows.export_flow [--input PATH] [--output PATH] [--force-refresh]
                                       [--concurrency N] [--log-level LEVEL] [--version]
```

| Флаг | Тип | Default | Семантика |
|---|---|---|---|
| `--input` | путь | `EXPORT_INPUT_FILE` (`input/urls.txt`) | входной файл со списком URL |
| `--output` | путь | `EXPORT_OUTPUT_DIR` (`data`) | корень слоёв |
| `--force-refresh` | флаг | `EXPORT_FORCE_REFRESH` (`false`) | игнорировать disk-skip, перевыгрузить всё |
| `--concurrency` | int ≥ 1 | `EXPORT_CONCURRENCY` (`4`) | `max_workers` для `ThreadPoolTaskRunner` |
| `--log-level` | enum | `LOG_LEVEL` (`INFO`) | `CRITICAL\|ERROR\|WARNING\|INFO\|DEBUG` |
| `--version` | флаг | — | печатает версию и выходит с кодом 0 |

Приоритет источников: **CLI-флаг > переменная окружения > `.env` > default модели**. Реализация: `argparse` парсит аргументы, затем значения, отличные от `None`, применяются к копии настроек через `settings.model_copy(update=...)`, и результат устанавливается синглтоном `set_settings(...)` (§4.2) — чтобы таски, читающие `get_settings()`, видели те же значения.

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings()                          # ValidationError -> exit 2
        settings = settings.model_copy(update=cli_overrides(args))
        set_settings(settings)
    except ValidationError as exc:
        print(format_config_error(exc), file=sys.stderr)
        return 2
    configure_logging(settings.log_level)
    ensure_layout(settings)                             # mkdir 01_raw, 02_interim, 04_markdown
    try:
        report = export_confluence_batch.with_options(
            task_runner=ThreadPoolTaskRunner(max_workers=settings.export_concurrency)
        )(input_file=str(settings.export_input_file),
          output_dir=str(settings.export_output_dir),
          force_refresh=settings.export_force_refresh)
    except AuthError as exc:
        print(f"authentication failed: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"input file not found: {exc}", file=sys.stderr)
        return 2
    except Exception:
        return 1                                        # flow упал: отчёт уже на диске
    return 0 if (report.failed == 0 and not report.invalid_urls) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

`cli_overrides(args) -> dict[str, object]` возвращает только те ключи, чьи флаги реально переданы: `export_input_file`, `export_output_dir`, `export_force_refresh`, `export_concurrency`, `log_level`. Все флаги объявляются с `default=None` (для `--force-refresh` — `action="store_true", default=None`), иначе флаг-«выключатель» перебивал бы `EXPORT_FORCE_REFRESH=true` из окружения.

### 11.2. Коды выхода

| Код | Условие |
|---|---|
| `0` | все страницы `ok`/`skipped`, невалидных URL нет |
| `1` | есть хотя бы одна `failed` страница или невалидный URL (включая случай «все страницы failed») |
| `2` | невозможный старт: ошибка валидации `Settings`, отсутствие обязательных env, 401 при первом обращении, отсутствующий входной файл |

### 11.3. `.env.example` (полный, обязательный файл репозитория)

```dotenv
# --- Confluence connection ---
CONFLUENCE_BASE_URL=https://confluence.example
CONFLUENCE_EDITION=datacenter
CONFLUENCE_AUTH_TYPE=bearer
CONFLUENCE_TOKEN=replace-me
CONFLUENCE_USERNAME=
CONFLUENCE_VERIFY_SSL=true
CONFLUENCE_TIMEOUT_SECONDS=30
CONFLUENCE_MAX_RETRIES=3

# --- Cloud BASIC (пример альтернативной конфигурации) ---
# CONFLUENCE_BASE_URL=https://acme.atlassian.net
# CONFLUENCE_EDITION=cloud
# CONFLUENCE_AUTH_TYPE=basic
# CONFLUENCE_USERNAME=user@acme.com
# CONFLUENCE_TOKEN=<api-token-from-id.atlassian.com>

# --- Export ---
EXPORT_OUTPUT_DIR=data
EXPORT_INPUT_FILE=input/urls.txt
EXPORT_CONCURRENCY=4
EXPORT_FORCE_REFRESH=false
LOG_LEVEL=INFO
```

`.gitignore` обязан содержать: `.env`, `../../../output/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.mypy_cache/`, `*.tmp-*`.

### 11.4. Логирование

```python
# src/logging.py
SECRET_PLACEHOLDER = "***"

class SecretMaskingFilter(logging.Filter):
    """Вырезает из сообщений значение CONFLUENCE_TOKEN, basic-заголовки и query-подписи."""

def configure_logging(level: str) -> None:
    """dictConfig: stderr-handler, формат '%(asctime)s %(levelname)s %(name)s %(message)s',
    SecretMaskingFilter на всех хендлерах, httpx/httpcore -> WARNING."""
```

Внутри тасок и flow используется `get_run_logger()` (Prefect агрегирует такие логи в UI). Вне Prefect-контекста (CLI, клиент, трансформеры) — `logging.getLogger(__name__)`. `httpx`-логгер поднимается до `WARNING`, чтобы URL с подписями не сыпались в вывод.

### 11.5. `pyproject.toml` (нормативный минимум)

```toml
[project]
name = "confluence-md-exporter"
version = "1.0.0"
requires-python = ">=3.11,<3.14"
dependencies = [
    "prefect>=3.1,<4",
    "httpx>=0.27,<1",
    "pydantic>=2.7,<3",
    "pydantic-settings>=2.3,<3",
    "beautifulsoup4>=4.12,<5",
    "lxml>=5.2,<6",
    "markdownify>=0.13,<1",
    "python-dotenv>=1.0,<2",
    "unidecode>=1.3,<2",
    "PyYAML>=6,<7",
]

[project.optional-dependencies]
dev = ["pytest>=8,<9", "pytest-cov>=5", "ruff>=0.6", "mypy>=1.11", "respx>=0.21"]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "C4", "RET", "PTH", "ANN"]
ignore = ["ANN401"]

[tool.mypy]
python_version = "3.11"
strict = true
plugins = []
warn_unused_ignores = true
disallow_untyped_defs = true

[[tool.mypy.overrides]]
module = ["markdownify.*", "unidecode.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q --strict-markers"
```

Команды разработчика (для README):

```bash
uv sync --extra dev
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run python -m src.flows.export_flow --input input/urls.txt --output data
```

`PyYAML` добавлен к минимальному набору зависимостей сознательно (§17): frontmatter требует детерминированной YAML-сериализации, писать её вручную — источник ошибок экранирования.

---
## 12. Стратегия тестов

### 12.1. Принципы

1. Ни один тест не обращается к живому Confluence. HTTP-слой мокается `respx` (транспортный мок для `httpx`).
2. Трансформеры тестируются как чистые функции: вход — XML-фикстура + `AssetSidecar` + `LinkIndex`, выход — строка Markdown/HTML. Ассерты — по подстрокам и полным блокам, не по «примерно похоже».
3. Файловые тесты используют `tmp_path` и `Settings(export_output_dir=tmp_path, ...)`.
4. Фикстуры не содержат реальных корпоративных данных: пространства `ARCH`/`DEMO`, пользователи `v.petrov`/`i.ivanov`, домен `confluence.example`.
5. Целевое покрытие: `src/transformers/` и `src/client/resolver.py` — ≥ 90% строк; остальное — ≥ 70%.

Состав каталога `tests/` (три файла, отмеченных `+`, добавлены сверх исходного канона, см. §17):

```text
tests/
├── conftest.py                 +  фикстуры settings/tmp-layout/sidecar/link_index
├── test_url_resolver.py           §12.2
├── test_macro_handlers.py         §12.3
├── test_md_converter.py           §12.4
├── test_disk_skip.py              §12.5
├── test_naming.py              +  slugify / safe_filename / коллизии
├── test_api_adapter.py         +  Cloud vs DC маппинг в PageRaw (respx)
├── test_manifest_and_report.py +  manifest/run_report/fixup_internal_links
└── fixtures/
    ├── sample_storage.xml
    ├── sample_page.json
    ├── sample_page_cloud_v2.json   +
    ├── sample_attachments_dc.json  +
    ├── sample_attachments_cloud.json +
    └── urls.txt
```

### 12.2. `test_url_resolver.py`

Параметризованный тест по всей таблице §5.4 (19 кейсов) — имя `test_parse_page_url_table`. Дополнительно:

| Тест | Проверяет |
|---|---|
| `test_ignores_comments_and_blank_lines` | строки `#…` и пустые не создают ни `PageTarget`, ни `InvalidUrl` |
| `test_dedup_by_page_id` | три формы одного `pageId=42` → 1 target, 2 записи в `duplicates`, 2 WARNING |
| `test_host_mismatch_is_invalid_url` | `https://other.example/...` → `InvalidUrl(reason=host_mismatch)`, батч продолжается |
| `test_tiny_link_unsupported` | `/x/AbCdEf` → `unsupported_url_form` |
| `test_space_title_resolved_via_api` | `respx`-мок DC `GET /rest/api/content?title=…` → `page_id` подставлен в `PageTarget` |
| `test_space_title_not_found` | пустой `results` → `InvalidUrl(reason=title_lookup_failed)` |
| `test_anchor_preserved` | `#section-2` попадает в `PageTarget.anchor` |
| `test_percent_encoded_cyrillic_title` | `%D0%A8%D0%BB%D1%8E%D0%B7` → `Шлюз` |

`fixtures/urls.txt`:

```text
# страницы для регрессионного теста
https://confluence.example/pages/viewpage.action?pageId=109847231
https://confluence.example/pages/viewpage.action?pageId=109847231&src=contextnavpagetreemode
https://confluence.example/display/ARCH/Kafka+Gateway

109847232
https://other.example/pages/viewpage.action?pageId=1
https://confluence.example/x/AbCdEf
```

Ожидание: 3 target (`109847231`, `109847232`, id из lookup), 1 дубликат, 2 `InvalidUrl`.

### 12.3. `test_macro_handlers.py`

Один тест на каждый макрос из каталога §8.4–§8.19. Каждый использует минимальный XML-фрагмент (те же, что в §8) и проверяет HTML после `transform`, а сквозной Markdown — в §12.4.

| Тест | Макрос / узел | Ключевой ассерт |
|---|---|---|
| `test_plain_html_passthrough` | `p/h1-h6/ul/ol/table/em/strong/a/hr/br` | теги доходят до clean HTML без изменений |
| `test_code_macro_language` | `code` с `language=python` | `<pre data-lang="python">`, тело точное |
| `test_code_macro_without_language` | `code` без параметра | `data-lang="text"` |
| `test_code_macro_language_alias` | `lang=js` | `data-lang="javascript"` |
| `test_noformat_macro` | `noformat` | `data-lang="text"` |
| `test_plantuml_macro` | `plantuml` | `data-lang="plantuml"`, картинка не создаётся |
| `test_plantumlcloud_macro` | `plantumlcloud` | то же |
| `test_plantuml_without_source_falls_back` | `plantuml` без body | `unsupported` содержит `plantuml` |
| `test_drawio_preview_and_source` | `drawio` + `Gateway.png` + `Gateway.drawio` | `img src="../03_assets/109847231/Gateway.png"` и второй `<a>` на `.drawio` |
| `test_drawio_preview_missing` | `drawio` без preview | только ссылка на source + warning |
| `test_drawio_nothing_found` | `drawio`, ассетов нет | маркер `missing-asset`, страница не падает |
| `test_callout_info_note_panel` | `info`, `note`, `panel` | `data-callout="NOTE"`, первый `<p>` = `[!NOTE]` |
| `test_callout_warning_error` | `warning`, `error` | `data-callout="WARNING"` |
| `test_callout_tip_success` | `tip`, `success` | `data-callout="TIP"` |
| `test_callout_with_title` | `panel` + `title` | `[!NOTE] Важно` |
| `test_image_attachment_relative_path` | `ac:image`+`ri:attachment` | ровно `../03_assets/109847231/ArchSchema.png` |
| `test_image_alt_fallback_to_filename` | `ac:image` без `ac:alt` | `alt == "ArchSchema.png"` |
| `test_image_external_url_kept` | `ac:image`+`ri:url` | внешний URL не изменён, файл не скачан |
| `test_image_missing_attachment` | вложения нет в sidecar | маркер `missing-asset`, warning, нет исключения |
| `test_view_file_macro` | `view-file`+`ri:attachment` | ссылка на локальный файл |
| `test_expand_macro` | `expand` | deferred-блок `DETAILS` с `title` |
| `test_status_macro` | `status` | `<code>ГОТОВО</code>`, цвет проигнорирован |
| `test_task_list` | `ac:task-list` | `<li>[x] …`, `<li>[ ] …` |
| `test_emoticon_named` | `ac:emoticon ac:name="tick"` | `✅` |
| `test_emoticon_with_emoji_fallback` | `ac:emoji-fallback="🚀"` | приоритет у `ac:emoji-fallback` |
| `test_emoticon_unknown_name` | `ac:name="galaxy"` | `:galaxy:` |
| `test_internal_link_in_batch` | `ac:link`+`ri:page`, цель в батче | `href="cmex://page/109847232"` |
| `test_internal_link_out_of_batch` | цель вне батча | абсолютный `source_url` |
| `test_internal_link_unresolved` | цели нет в `LinkIndex` | `<strong>` + маркер `unresolved-page-link` |
| `test_internal_link_with_anchor` | `ac:anchor="Итоги"` | суффикс `#Итоги` |
| `test_link_attachment` | `ac:link`+`ri:attachment` | локальная ссылка на файл |
| `test_link_user` | `ac:link`+`ri:user` | `@v.petrov` |
| `test_time_element` | `<time datetime="2026-04-12"/>` | текст `2026-04-12` |
| `test_date_macro` | `date` | ISO-дата текстом |
| `test_unsupported_macro_fallback` | `jira` | маркер `unsupported-macro: jira`, текст тела сохранён, `unsupported == ["jira"]` |
| `test_unsupported_macro_ignores_parameters` | `contentbylabel` с параметрами | значения параметров не попали в текст |
| `test_layout_unwrapped` | `ac:layout-section`/`ac:layout-cell` | контейнеры сняты, контент сохранён в порядке ячеек |
| `test_inline_comment_marker_unwrapped` | `ac:inline-comment-marker` | текст сохранён, тег убран |
| `test_foreign_attachment_prefix` | `ri:attachment`+`ri:page` | имя `<owner_id>__file.png` |

Краевые случаи (§8.22) — отдельный параметризованный блок: `test_edge_cases[E1…E18]`.

### 12.4. `test_md_converter.py`

| Тест | Проверяет |
|---|---|
| `test_frontmatter_keys_and_order` | точный порядок ключей §4.7, `id` — строка в кавычках, кириллица не escape-ится |
| `test_frontmatter_empty_lists` | `labels: []`, `unsupported_macros: []` присутствуют |
| `test_h1_injected_after_frontmatter` | `# {title}` сразу после закрывающего `---` |
| `test_code_fence_escaping` | тело с ` ``` ` даёт ограждение из 4 бэктиков |
| `test_callout_render` | `> [!NOTE] Важно` и следующая строка `> …` без пустой `>` между ними |
| `test_details_render` | блок `<details>` с пустыми строками вокруг Markdown-тела |
| `test_table_simple` | pipe-таблица с разделителем `| --- |` |
| `test_table_first_row_promoted_to_header` | таблица без `th` получает заголовок из первой строки |
| `test_table_colspan_flattened` | `colspan=2` → строка добита пустой ячейкой, исключения нет |
| `test_table_pipe_escaped` | `A|B` → `A\|B` |
| `test_nested_table_raw_html` | вложенная таблица вставлена как HTML-блок |
| `test_task_list_markdown` | `- [x] Сделано` / `- [ ] В работе` |
| `test_image_path_is_relative_two_levels` | в Markdown ровно `../03_assets/<id>/<file>`; строка `../assets/` **отсутствует** |
| `test_image_path_with_spaces_wrapped` | путь с пробелом обёрнут в `<…>` |
| `test_nbsp_normalized` | `\u00a0` заменён вне кода и сохранён внутри fenced-блока |
| `test_no_trailing_whitespace` | ни одна строка вне кода не оканчивается пробелом |
| `test_empty_body_page` | md = frontmatter + `# title`, warning `empty_body`, статус `ok` |
| `test_preview_is_truncated` | `RenderedPage.preview` ≤ 1200 символов и не содержит токена |
| `test_stale_markdown_removed` | смена заголовка удаляет старый `<id>_<old-slug>.md` |
| `test_full_fixture_snapshot` | сквозной прогон `sample_storage.xml` + `sample_page.json` → сравнение с эталонным `.md` (snapshot в фикстурах) |

### 12.5. `test_disk_skip.py`

Все кейсы D1–D10 из §3.2 как отдельные тесты, `respx` считает число исходящих запросов.

| Тест | Сценарий | Ожидание |
|---|---|---|
| `test_d1_force_refresh_refetches` | локальные файлы актуальны, `force_refresh=True` | probe не нужен, body-запрос выполнен, файлы перезаписаны |
| `test_d2_no_raw_json_full_fetch` | пустой `01_raw` | 1 body-запрос |
| `test_d3_corrupted_raw_json` | битый JSON | WARNING + full fetch |
| `test_d4_trashed_page_skipped` | probe отдаёт `status="trashed"` | `skipped/trashed`, body-запрос не выполнялся, файлы не тронуты |
| `test_d5_not_found_skipped` | probe → 404 | `skipped/not_found` |
| `test_d6_forbidden_failed_no_retries` | probe → 403 | `failed/forbidden`, ровно 1 запрос (ретраев нет) |
| `test_d7_version_bumped_refetch` | local `version=5`, remote `6` | full fetch, ассеты пересинхронизированы |
| `test_d8_up_to_date_skip` | всё на месте | `skipped/up_to_date`, запросов ровно 1 (probe), mtime файлов не изменились |
| `test_d9_missing_asset_repaired` | удалён один ассет | докачан только он (1 download-запрос), статус `ok` |
| `test_d10_missing_markdown_rerendered` | удалён md | пересборка без сетевых запросов, кроме probe |
| `test_prefect_cache_is_not_idempotency` | версия совпала, но Prefect-кэш пуст | решение принимает disk-skip, а не кэш: сетевых body-запросов 0 |
| `test_retry_after_respected` | 429 с `Retry-After: 1` | 1 повтор, задержка учтена (монипатч `time.sleep`) |
| `test_attachment_download_uses_rest_path` | скачивание вложения | запрос ушёл на `/rest/api/content/<page>/child/attachment/<att>/download`, а **не** на `/download/attachments/...` |
| `test_attachment_download_fallback_on_401` | REST-путь → 401 | ровно один fallback-запрос на путь из API-ответа |
| `test_attachment_download_failure_keeps_page_ok` | оба пути → 500 | `AssetSource.MISSING`, статус страницы `ok`, warning в отчёте |

### 12.6. `test_api_adapter.py`

| Тест | Проверяет |
|---|---|
| `test_dc_page_mapping` | `sample_page.json` → `PageRaw` со всеми полями §5.1 (в т.ч. `created_by` из `history.createdBy.username`) |
| `test_cloud_page_mapping` | `sample_page_cloud_v2.json` → тот же `PageRaw`; `space_key` получен из `/spaces/{id}`, `created_by` — из `/rest/api/user` |
| `test_cloud_source_url_from_webui` | `source_url == base + "/wiki" + _links.webui` |
| `test_dc_source_url_viewpage` | `source_url == base + "/pages/viewpage.action?pageId=<id>"` |
| `test_attachment_dedup_by_version` | два вложения `report.pdf` v1/v2 → остаётся v2 |
| `test_pagination_cursor_cloud` | два ответа с `_links.next` → собраны все вложения |
| `test_pagination_next_dc` | то же для v1 |
| `test_basic_auth_requires_username` | `auth_type=basic` без `CONFLUENCE_USERNAME` → `ValidationError` (проекция exit 2) |
| `test_bearer_header_set` | заголовок `Authorization: Bearer …`, `BasicAuth` не используется |
| `test_dc_sends_atlassian_token_header` | `X-Atlassian-Token: no-check` присутствует для DC и отсутствует для Cloud |
| `test_token_never_logged` | `caplog` не содержит значения токена ни на одном уровне |

### 12.7. `test_manifest_and_report.py`

| Тест | Проверяет |
|---|---|
| `test_manifest_fields` | все ключи §5.3, `md_path` = `04_markdown/<id>_<slug>.md`, `assets_dir` = `03_assets/<id>` |
| `test_manifest_includes_failed_with_error` | `status="failed"`, `error` не `None` |
| `test_run_report_invariant` | `pages_total == ok + failed + skipped` |
| `test_run_report_contains_invalid_urls` | невалидные строки с причинами |
| `test_fixup_internal_links_in_batch` | `cmex://page/109847232` → `./109847232_kafka-gateway.md` |
| `test_fixup_internal_links_failed_target` | цель упала → абсолютный URL |
| `test_no_placeholder_left` | в финальных md нет ни `cmex://`, ни `@@CMEX_DEFER_` |
| `test_manifest_links_resolve` | каждая ссылка `../03_assets/...` из md существует на диске |
| `test_exit_code_matrix` | 0/1/2 по таблице §10.5 (через `main(argv)` с моками) |

### 12.8. Фикстуры

`fixtures/sample_page.json` (DC, сокращённо — ровно то, что нужно маппингу):

```json
{
  "id": "109847231",
  "type": "page",
  "status": "current",
  "title": "Архитектура интеграционного шлюза",
  "space": {"key": "ARCH", "name": "Архитектура"},
  "version": {"number": 5, "when": "2026-04-12T17:32:00.000+03:00"},
  "history": {
    "createdBy": {"username": "v.petrov", "displayName": "Петров В."},
    "lastUpdated": {"when": "2026-04-12T17:32:00.000+03:00"}
  },
  "ancestors": [{"id": "1", "title": "Главная"}, {"id": "2", "title": "Проекты 2026"}],
  "metadata": {"labels": {"size": 2, "results": [{"name": "kafka"}, {"name": "architecture"}]}},
  "body": {"storage": {"value": "<!-- содержимое sample_storage.xml -->", "representation": "storage"}},
  "_links": {"webui": "/display/ARCH/Arch"}
}
```

`fixtures/sample_page_cloud_v2.json`:

```json
{
  "id": "109847231",
  "status": "current",
  "title": "Архитектура интеграционного шлюза",
  "spaceId": "98765",
  "authorId": "712020:abc-def",
  "version": {"number": 5, "createdAt": "2026-04-12T14:32:00.000Z", "authorId": "712020:abc-def"},
  "body": {"storage": {"value": "<p>ok</p>", "representation": "storage"}},
  "_links": {"webui": "/spaces/ARCH/pages/109847231/Arch"}
}
```

`fixtures/sample_attachments_dc.json`:

```json
{
  "results": [
    {"id": "att123", "title": "ArchSchema.png", "version": {"number": 2},
     "extensions": {"mediaType": "image/png", "fileSize": 18420},
     "_links": {"download": "/download/attachments/109847231/ArchSchema.png?version=2&api=v2"}},
    {"id": "att124", "title": "Gateway.drawio", "version": {"number": 1},
     "extensions": {"mediaType": "application/octet-stream", "fileSize": 4096},
     "_links": {"download": "/download/attachments/109847231/Gateway.drawio?version=1&api=v2"}}
  ],
  "size": 2,
  "_links": {}
}
```

`fixtures/sample_storage.xml` — покрывает все макросы §6.1 и краевые случаи E2/E3/E7/E9/E15:

````xml
<p>Вступление с &nbsp; и <strong>акцентом</strong>.</p>
<h2>Схема</h2>
<ac:image ac:alt="Схема шлюза"><ri:attachment ri:filename="ArchSchema.png"/></ac:image>
<ac:image><ri:url ri:value="https://cdn.example/pic.png"/></ac:image>
<ac:structured-macro ac:name="info">
  <ac:parameter ac:name="title">Важно</ac:parameter>
  <ac:rich-text-body><p>Схема актуальна на релиз 2026.2.</p></ac:rich-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="warning"><ac:rich-text-body><p>Не менять в прод.</p></ac:rich-text-body></ac:structured-macro>
<ac:structured-macro ac:name="tip"><ac:rich-text-body><p>Совет.</p></ac:rich-text-body></ac:structured-macro>
<ac:structured-macro ac:name="code">
  <ac:parameter ac:name="language">python</ac:parameter>
  <ac:plain-text-body><![CDATA[print("```")]]></ac:plain-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="noformat"><ac:plain-text-body><![CDATA[raw]]></ac:plain-text-body></ac:structured-macro>
<ac:structured-macro ac:name="plantuml">
  <ac:plain-text-body><![CDATA[@startuml
A -> B
@enduml]]></ac:plain-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="drawio"><ac:parameter ac:name="diagramName">Gateway</ac:parameter></ac:structured-macro>
<ac:structured-macro ac:name="expand">
  <ac:parameter ac:name="title">Детали</ac:parameter>
  <ac:rich-text-body><p>Скрытый текст</p></ac:rich-text-body>
</ac:structured-macro>
<ac:structured-macro ac:name="panel"/>
<p>Статус: <ac:structured-macro ac:name="status">
  <ac:parameter ac:name="colour">Green</ac:parameter>
  <ac:parameter ac:name="title">Готово</ac:parameter>
</ac:structured-macro> <ac:emoticon ac:name="tick"/></p>
<ac:task-list>
  <ac:task><ac:task-status>complete</ac:task-status><ac:task-body>Согласовано с ИБ</ac:task-body></ac:task>
  <ac:task><ac:task-status>incomplete</ac:task-status><ac:task-body>Нагрузочное тестирование</ac:task-body></ac:task>
</ac:task-list>
<p>См. <ac:link><ri:page ri:space-key="ARCH" ri:content-title="Kafka Gateway"/>
  <ac:plain-text-link-body><![CDATA[Kafka Gateway]]></ac:plain-text-link-body></ac:link>,
  автор <ac:link><ri:user ri:username="v.petrov"/></ac:link>,
  файл <ac:link><ri:attachment ri:filename="Gateway.drawio"/></ac:link>.</p>
<ac:structured-macro ac:name="view-file">
  <ac:parameter ac:name="name"><ri:attachment ri:filename="ArchSchema.png"/></ac:parameter>
</ac:structured-macro>
<p>Дедлайн: <time datetime="2026-04-12"/></p>
<ac:structured-macro ac:name="toc"/>
<ac:structured-macro ac:name="jira">
  <ac:parameter ac:name="key">ARCH-42</ac:parameter>
  <ac:plain-text-body><![CDATA[ARCH-42: миграция]]></ac:plain-text-body>
</ac:structured-macro>
<ac:layout><ac:layout-section ac:type="two_equal">
  <ac:layout-cell><p>Левая колонка</p></ac:layout-cell>
  <ac:layout-cell><p>Правая колонка</p></ac:layout-cell>
</ac:layout-section></ac:layout>
<table><tbody>
  <tr><td>Компонент</td><td>Назначение</td></tr>
  <tr><td colspan="2">gateway | маршрутизация</td></tr>
  <tr><td><table><tbody><tr><td>вложенная</td></tr></tbody></table></td><td>x</td></tr>
</tbody></table>
````

Сопутствующая фикстура `AssetSidecar` для тестов содержит `ArchSchema.png`, `Gateway.png`, `Gateway.drawio`; `LinkIndex` — запись `("ARCH", "Kafka Gateway") -> 109847232`; `batch_page_ids = ["109847231", "109847232"]`.

---

## 13. План реализации файлов

**Статус раздела.** Это рекомендованный порядок сборки и Definition of Done по файлу, а не нарезка работ. Нарезка живёт в `docs/todo/<epic>/`: границы конкретного PR задаёт файл задачи, который ссылается на секции этого документа. Нормативны здесь именно DoD-условия по каждому файлу; последовательность может быть перегруппирована планировщиком эпика, если зависимости соблюдены.

Порядок обязателен в части зависимостей: каждый следующий файл опирается только на уже готовые. После каждого шага прогоняются `ruff check`, `mypy src`, `pytest` (тесты шага).

| # | Файл | Зависит от | Definition of Done |
|---|---|---|---|
| 1 | `pyproject.toml`, `.gitignore`, `.env.example`, `input/urls.txt` (пример из §12.2), `README.md` | — | `uv sync --extra dev` проходит; `.env.example` содержит все 13 ключей §11.3; README описывает установку, `.env`, запуск, коды выхода, layout |
| 2 | `src/__init__.py`, `src/models.py` | 1 | все модели и enum'ы §4 объявлены, `mypy strict` чист, `python -c "import src.models"` работает |
| 3 | `src/config.py` | 2 | `Settings` валидирует все правила §4.2; тест «basic без username → ValidationError» зелёный; `get_settings()` кэшируется |
| 4 | `src/logging.py`, `src/paths.py`, `src/naming.py` | 3 | `slugify`/`safe_filename` проходят таблицы §7.4–§7.6; `write_atomic` пишет LF и не оставляет `.tmp-*`; `asset_relative_path` — единственный конструктор медиа-путей (проверяется grep'ом: строка `03_assets` встречается в `src/` только в `paths.py`) |
| 5 | `src/client/resolver.py` | 4 | `test_url_resolver.py` (кроме api-lookup) зелёный; чистая функция без импортов `httpx` |
| 6 | `src/client/api.py` | 2 | `ApiStrategy` Protocol + исключения (`AuthError`, `ForbiddenError`, `NotFoundError`, `RateLimitError`, `HttpError`, `NetworkError`, `StorageParseError`) с полем `reason: FailureReason` |
| 7 | `src/client/datacenter.py` | 6 | `test_api_adapter.py::test_dc_*` зелёные; маппинг §6.4.1 полный |
| 8 | `src/client/cloud.py` | 6 | `test_api_adapter.py::test_cloud_*` зелёные; кэши `space_key`/`title`/`user` внутри стратегии |
| 9 | `src/client/confluence.py` | 5,7,8 | retry/backoff §6.2, `download_attachment` §7.2 (REST-путь основной, fallback один раз), `probe_version`, `build_link_index`; токен не появляется в логах (`test_token_never_logged`) |
| 10 | `src/transformers/macro_handlers.py` | 4 | все тесты §12.3 зелёные; каждый макрос §6.1 имеет обработчик; `handle_unsupported` не бросает исключений |
| 11 | `src/transformers/html_cleaner.py` | 10 | нормализация §8.21; вложенные таблицы → deferred; `|` экранирован |
| 12 | `src/transformers/md_converter.py` | 11 | тесты §12.4 зелёные; snapshot-тест совпадает байт в байт |
| 13 | `src/flows/tasks.py` | 9,12 | сигнатуры и декораторы §10.3 буквально; `process_page` не пропускает исключений; disk-skip D1–D10 (`test_disk_skip.py`) зелёный |
| 14 | `src/flows/export_flow.py` | 13 | flow + CLI §11; `--help` работает без `.env`; коды выхода по §11.2; `test_exit_code_matrix` зелёный |
| 15 | `tests/*` дополняются на каждом шаге, финальный прогон | 1–14 | `uv run pytest` зелёный целиком; покрытие §12.1 достигнуто; `ruff check src tests` и `mypy src` без ошибок |

Запрещено на всех шагах: реализовывать что-либо из §1.4 (out of scope), добавлять CLI-флаги вне §11.1, вводить альтернативные схемы путей, менять имена ключей frontmatter/manifest.

---

## 14. Риски и явные решения

**Статус раздела.** Таблица — это индекс принятых решений и их обоснований. Нормативной является формулировка в профильной секции, на которую ссылается строка; обоснование «почему именно так» по процессу принадлежит слою ADR (`docs/decisions/`, см. `docs/process/README.md`). Строки, отмеченные как настоящие развилки с альтернативами (R-02, R-03, R-05, R-06, R-09, R-13, R-15, R-16), подлежат оформлению отдельными ADR при приёмке пакета; до этого действует текст профильных секций.

| ID | Риск | Выбранное решение | Цена решения |
|---|---|---|---|
| R-01 | Относительные пути к медиа расходятся между слоями и ломают Obsidian | Единственная функция `asset_relative_path()` в `src/paths.py`, единственная форма `../03_assets/<page_id>/<file>`; форма `../assets/...` запрещена и проверяется тестом `test_image_path_is_relative_two_levels` | нет |
| R-02 | Prefect-кэш создаёт иллюзию идемпотентности и отдаёт устаревшие данные | Disk-skip D1–D10 как основной механизм; Prefect-кэш только как вторичный ускоритель с `cache_expiration=1h`; `force_refresh` в аргументах таски меняет ключ | один дополнительный probe-запрос на страницу |
| R-03 | Скачивание вложений через UI-путь `/download/attachments/...` даёт 401 без cookie | Основной путь — REST `/rest/api/content/{page}/child/attachment/{att}/download` (для Cloud с префиксом `/wiki`), fallback — путь из API-ответа, всегда с `Authorization` и `follow_redirects=True` | один лишний запрос в редком fallback-случае |
| R-04 | Неполная auth-модель (token без username) даёт 401 на Cloud BASIC | Три явных режима (§6.1), `CONFLUENCE_USERNAME` обязателен при `basic`, `CONFLUENCE_EDITION` обязателен всегда; нарушение — exit 2 на старте | пользователь обязан заполнить больше env-ключей |
| R-05 | Смешение Cloud и DC API даёт неверные пути и типы id | Тонкий адаптер: `ConfluenceClient` + `CloudApi`/`DataCenterApi`; ветвление по редакции существует ровно в одном месте (`__init__`) | два набора фикстур в тестах |
| R-06 | Неизвестный макрос валит пайплайн | `handle_unsupported` + перехват любого исключения в диспетчере; имя макроса в `unsupported_macros` frontmatter | часть контента деградирует до текста |
| R-07 | Cloud v2 не отдаёт `title` ancestors и `space key` напрямую | Дополнительные запросы `/pages/{id}` и `/spaces/{id}` с process-кэшем | до `len(ancestors)+1` лишних запросов на первую страницу пространства |
| R-08 | Cloud скрывает `displayName` автора настройками приватности | `created_by` деградирует до `accountId`, страница не падает | менее читаемый `created_by` |
| R-09 | Смена заголовка страницы меняет slug, старые ссылки из ранее выгруженных файлов устаревают | `fixup_internal_links` правит страницы текущего запуска; устаревшие ссылки в неперегенерированных файлах лечатся `--force-refresh`; старый md с прежним slug удаляется (§9.5.6) | периодически нужен полный прогон |
| R-10 | 429/503 при большом батче | Backoff §6.2 с уважением `Retry-After` + `EXPORT_CONCURRENCY` по умолчанию 4 | экспорт медленнее при троттлинге |
| R-11 | Небезопасные имена файлов (кириллица, `:`, `?`, длина, зарезервированные имена Windows) | `safe_filename` §7.4 + карта `original → safe` в `01_raw/<id>.assets.json` | имена могут отличаться от Confluence, карта обязательна для отладки |
| R-12 | `colspan`/`rowspan` и вложенные таблицы не выражаются в GFM | `colspan/rowspan` — упрощение с добивкой пустых ячеек; вложенные таблицы — сырой HTML-блок | визуальные потери в сложных таблицах |
| R-13 | `markdownify` выбрасывает HTML-комментарии, а маркеры обязаны дойти до Markdown (§8.20) | Маркеры проходят через deferred-механизм (§8.1) и дублируются комментарием в interim HTML | небольшая потеря читаемости `02_interim` |
| R-14 | Секреты утекают в логи/Prefect-артефакты/параметры тасок | `SecretStr`, `SecretMaskingFilter`, запрет `Settings`/клиента в аргументах тасок, `sanitize_error`, `httpx`-логгер на WARNING | немного больше кода в клиенте |
| R-15 | Storage-фрагмент не парсится XML-парсером (`&nbsp;`, битая разметка) | `normalize_entities` + recovery-парсинг вторым проходом; полный провал → `failed/parse_error` только для одной страницы | редкие страницы теряют часть разметки |
| R-16 | Внутренняя ссылка на страницу вне батча требует lookup по title | Индекс ссылок строится на fetch-этапе (`build_link_index`) и кладётся в `01_raw/<id>.links.json`; трансформеры остаются без сети | дополнительные запросы на первую выгрузку страницы |
| R-17 | Идентичные `title` у разных вложений/версий | Дедупликация по `(title, max version)` (§6.4.2) и `__N`-суффиксы при коллизии safe-имён (§7.5) | старые версии вложений не выгружаются: осознанное сужение, §8.22 E4 |
| R-18 | Параллелизм ломает порядок и создаёт гонки за файлы | Каждая страница пишет только в свои файлы (`<page_id>*`), общий `manifest.json` пишется единственной таской после всех страниц; все записи атомарны | нет |
| R-19 | Соблазн реализовать out-of-scope (descendants, комментарии, PDF) | Явный запрет §1.4 + §13; отсутствие CLI-флагов для этого | функциональность откладывается |
| R-20 | Расхождение кода и SDD со временем | SDD — единственный источник правды; изменение поведения требует правки SDD в том же PR | дисциплина ревью |

---

## 15. Бриф реализатора (продуктовые инварианты)

Этот раздел **не заменяет** `docs/process/agent-prompt.md` и не дублирует его. Процессный промпт задаёт роль, стадию репозитория, тип изменения, порядок чтения и гейты; бриф ниже задаёт продуктовые инварианты. Реализатор получает оба плюс файл задачи.

Предусловия работы: стадия репозитория `spec-first` (`docs/process/STATUS.md`), пакет принят человеком, для работы есть файл задачи в `docs/todo/<epic>/`. Файла задачи нет — реализация не начинается (роль не Implementer).

```text
Ты — Implementer. Реализуешь ОДИН таск из docs/todo/<epic>/ в рамках спецификации
docs/spec/. Спецификация — единственный источник требований: она уже содержит решения,
сигнатуры, алгоритмы и контракты. Ничего не придумывай и не расширяй.

ЖЁСТКИЕ ПРАВИЛА
1. Читаешь файл задачи и ТОЛЬКО те секции спеки, на которые он ссылается. Документ целиком
   не грузишь. Если задача требует секций, которых в ней нет, — просишь дополнить задачу.
2. Ответа в спеке нет или он противоречив — СТОП и предложение spec-patch (или adr+spec,
   если развилка неочевидна). Не «минимальный вариант на своё усмотрение», не файл
   с отклонениями, не молчаливый выбор.
3. Границы PR задаёт DoD задачи. Порядок сборки из §13 — ориентир для планировщика, а не
   разрешение выйти за рамки таска.
4. Стек фиксирован: Python >=3.11,<3.14, uv, prefect>=3.1,<4, httpx (sync), pydantic v2,
   pydantic-settings, lxml, beautifulsoup4, markdownify, PyYAML, unidecode, python-dotenv.
   Dev: pytest, respx, ruff, mypy. Других зависимостей не добавляешь.
5. Prefect только 3.x: from prefect import flow, task; from prefect.cache_policies import
   INPUTS, TASK_SOURCE; from prefect.artifacts import create_markdown_artifact,
   create_table_artifact; from prefect.logging import get_run_logger; from prefect.task_runners
   import ThreadPoolTaskRunner. API Prefect 2 (cache_key_fn и т.п.) запрещён.
6. Структура репозитория — ровно §2.2 плюс tests из §12.1. Новых модулей не создаёшь.
7. Задача затрагивает зону из §1.6 — останавливаешься и запрашиваешь человека,
   даже если дифф выглядит мелким.

КРИТИЧНЫЕ ИНВАРИАНТЫ (нарушение = дефект)
- Ссылки на медиа из Markdown только вида ../03_assets/<page_id>/<safe_filename>, и строятся
  только функцией paths.asset_relative_path(). Формы ../assets/... не существует.
- Идемпотентность — это disk-skip D1–D10 из §3.2 (probe версии + проверка файлов на диске),
  а не Prefect-кэш. Prefect-кэш — вторичный слой с cache_expiration=1h.
- Вложения качаются через REST: /rest/api/content/{page_id}/child/attachment/{att_id}/download
  (для Cloud с префиксом /wiki), fallback — путь из API-ответа, один раз. UI-путь
  /download/attachments/... вручную не конструируется никогда.
- Auth: три режима (Cloud basic = email+API token; DC bearer = PAT; DC basic = username+token).
  CONFLUENCE_USERNAME обязателен при basic, CONFLUENCE_EDITION обязателен всегда. Токен —
  SecretStr, он не попадает ни в логи, ни в артефакты, ни в аргументы Prefect-тасок.
- Settings и ConfluenceClient никогда не передаются в аргументах @task; настройки читаются
  внутри таски через get_settings(), клиент создаётся внутри таски как контекстный менеджер.
- Одна страница не валит батч: process_page перехватывает всё и возвращает PageResult.
  Flow падает только если ok == 0 и failed > 0, и только после записи manifest.json и
  run_report.json.
- Каждый макрос из §8.4–§8.19 реализован по своему алгоритму; всё остальное идёт в
  handle_unsupported (§8.20) с маркером <!-- unsupported-macro: name --> и записью имени в
  frontmatter.unsupported_macros. Пайплайн не падает на неизвестном макросе никогда.
- frontmatter: ключи и их порядок ровно как в §4.7, id всегда строка, breadcrumbs =
  titles(ancestors) + title.
- manifest.json и run_report.json соответствуют §4.6; инвариант
  pages_total == ok + failed + skipped.
- Out of scope (§1.4) не реализуется: descendants, комментарии, запись в Confluence,
  рендер PlantUML/Draw.io, tiny-links, Docker/CI.

ТЕСТЫ
Пишешь вместе с кодом, состав — по §12 и по DoD задачи: URL-паттерны (§12.2), каждый макрос
(§12.3), Markdown-рендер (§12.4), все ветки disk-skip D1–D10 (§12.5), адаптеры Cloud/DC (§12.6),
manifest/report/exit codes (§12.7). Живой Confluence не используется: только фикстуры §12.8
и respx. Ослабление или удаление обязательного теста — human-gated (§1.6).

ГОТОВО, КОГДА
DoD задачи выполнен; uv run ruff check src tests, uv run mypy src и uv run pytest зелёные;
uv run python -m src.flows.export_flow --help работает без .env; PR цитирует секции
docs/spec/... по каждому изменению поведения.
```

---

## 16. Приложение: критерии приёмки пакета

Чеклист для человека, принимающего спецификацию (`docs/process/roles.md`, «Human only»). Пакет считается принятым, когда каждая строка подтверждена; после приёмки стадия в `docs/process/STATUS.md` переводится в `spec-first`.

| Критерий приёмки | Где выполнено |
|---|---|
| Нет противоречий в путях ассетов | §0.1 (единственная форма `../03_assets/...`), §7.6 (`asset_relative_path`), §8.11, §9.5, §12.4 (`test_image_path_is_relative_two_levels`), §14 R-01 |
| Auth и edition разведены | §4.2 (валидатор `basic → username`), §6.1 (матрица трёх режимов), §6.3–§6.4 (две стратегии), §12.6, §14 R-04/R-05 |
| Download attachments через REST, не через UI path | §6.4 (эндпоинты download), §7.2 (основной REST-путь, fallback из API-ответа, запрет ручного UI-пути), §12.5 (`test_attachment_download_uses_rest_path`), §14 R-03 |
| Disk-skip описан пошагово и не подменён Prefect-кэшем | §3.2 (D1–D10), §6.4 (probe-запросы и поля), §7.1 (reuse-условие ассетов), §10.3 п.3–4, §12.5, §14 R-02 |
| Каждый обязательный макрос имеет алгоритм и fixture-пример | §8.4–§8.19 (алгоритм + XML-пример на каждое правило), §12.3 (тест на каждый), §12.8 (`sample_storage.xml`) |
| Контракт неизвестных макросов, 404/403, пустых страниц | §8.20 (fallback), §6.6 и §3.2 D4–D6 (404/403/trashed), §8.22 E1 (пустая страница) |
| Есть `manifest.json` и `run_report.json` | §0.1, §4.6, §10.6, §12.7 |
| Prefect 3 API корректен | §10.1 (`prefect.cache_policies`, `prefect.artifacts`, `prefect.logging.get_run_logger`, `ThreadPoolTaskRunner`), §10.3, запрет Prefect 2 API |
| In scope и out of scope объявлены явно, out of scope не просачивается в план | §1.4 (оба списка), §13 (запреты на всех шагах), §14 R-19 |
| Человеко-гейтные зоны объявлены в спеке, а не в процессном пакете | §1.6 |
| Бриф реализатора не противоречит процессу (минимальный контекст, stop-and-ask, слой задач) | §15 |
| Документ самодостаточен: нормативность не выведена из Init Requirements | §17 (перечень расхождений), отсутствие ссылок на init как на источник нормы |

---

## 17. Приложение: расхождения с Init Requirements

Пакет собран из `init/Requirements.md` v1.1. Ниже — все места, где спецификация сознательно отличается от исходного документа. Список нужен человеку для приёмки; после приёмки Init Requirements становятся необязывающими, и нормой остаётся только текст этой спецификации.

| # | Init Requirements | Решение спеки | Обоснование |
|---|---|---|---|
| 1 | Каталог `src/` без модулей путей и имён | Добавлены `src/paths.py`, `src/naming.py`, `src/client/api.py` | единственный владелец схемы путей (§7.6) и типов ошибок; иначе литерал `03_assets` расползается по коду и нарушает инвариант R-01 |
| 2 | Четыре тестовых файла | Добавлены `test_naming.py`, `test_api_adapter.py`, `test_manifest_and_report.py` и `conftest.py` | покрытие адаптеров и публичных контрактов не помещается в исходные четыре файла (§12.1) |
| 3 | Минимальный список зависимостей | Добавлены `PyYAML` (обязателен) и `respx` (dev) | детерминированная YAML-сериализация frontmatter и мок HTTP без живого Confluence |
| 4 | Layout из шести артефактов | Добавлены sidecar `01_raw/<id>.assets.json` и `01_raw/<id>.links.json` | карта `original → safe` требуется исходным документом, индекс ссылок держит трансформацию без сети (§6.7) |
| 5 | `CONFLUENCE_USERNAME` «опционально» в одном месте и «обязателен при basic» в другом | Обязателен при `basic`, иначе старт невозможен (exit 2) | снятие противоречия внутри исходного документа; BASIC без username даёт 401 |
| 6 | Парсер: `lxml` **или** `BeautifulSoup` | Зафиксирован `lxml` в XML-режиме; `BeautifulSoup` только внутри `markdownify` | развилка закрыта: XML-парсер сохраняет CDATA и различает `ac:`/`ri:` (§8.1) |
| 7 | Cloud API: v1 или v2 на выбор | Зафиксирован v2 для Cloud, v1 для DC; два узких v1-вызова на Cloud (download, user) | v1 `content` на Cloud deprecated (§6.4.2) |
| 8 | Раздел «Промпт для агента-реализатора» как самодостаточный prompt | Раздел 15 переоформлен в продуктовый бриф, композиционный с `docs/process/agent-prompt.md` | требование «читать документ целиком» и «фиксировать отклонения в отдельном файле» противоречит процессу: минимальный контекст и stop-and-ask |
| 9 | План реализации файлов как порядок работ | Раздел 13 объявлен ориентиром; нарезка работ живёт в `docs/todo/<epic>/` | слой задач по процессу отделён от слоя спецификации |
| 10 | Риски с обоснованиями внутри спеки | Раздел 14 объявлен индексом решений; настоящие развилки подлежат оформлению ADR | по процессу «ADR объясняет почему, спека фиксирует что должно быть истинным» |

