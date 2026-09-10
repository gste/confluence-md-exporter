# confluence-md-exporter

Локальный read-only конвейер: выгрузка страниц Confluence Server/Data Center → Markdown, медиа-ассеты, diff-сравнение версий и каталог батча. Закон реализации — [`docs/spec/README.md`](docs/spec/README.md).

## Установка

Требуется Python `>=3.11,<3.14`. Пакетный менеджер — `uv`.

```bash
uv sync
```

## Окружение (.env)

Скопируй [`.env.example`](.env.example) в `.env` и укажи параметры подключения:

```bash
cp .env.example .env
```

Файл `.env` в git не коммитится. Передавай его при запуске:

```bash
uv run --env-file .env confluence-md-exporter [OPTIONS]
```

### Основные переменные:
- `CONFLUENCE_BASE_URL` — базовый URL инстанса: origin и опциональный контекст-путь (без `/wiki` и без хвоста `/`). Пример: `https://confluence.example.com` или `https://confluence.example.com/confluence`.
- `CONFLUENCE_AUTH_TYPE` — `bearer` (рекомендуется) или `basic`.
- `CONFLUENCE_TOKEN` — Personal Access Token (PAT) или пароль.
- `CONFLUENCE_USERNAME` — имя пользователя (обязательно только для `basic`).
- `EXPORT_INPUT_FILE` — путь по умолчанию к файлу со списком URL (например `input/urls.txt`).
- `EXPORT_OUTPUT_DIR` — каталог сохранения по умолчанию (например `data` или `output`).
- `EXPORT_CONCURRENCY` — количество параллельных потоков при многопоточном экспорте (по умолчанию `4`).

---

## Форматы входных ссылок (input/urls.txt)

Файл `input/urls.txt` (UTF-8, одна ссылка на строку; строки с `#` и пустые строки игнорируются).

Поддерживаются:
1. **Прямые страницы по ID**:
   - `https://confluence.example.com/pages/viewpage.action?pageId=123456`
   - `https://confluence.example.com/wiki/spaces/SPACE/pages/123456/Some+Page+Title`
   - `123456` (чистый идентификатор)
2. **Страницы по Space и Title**:
   - `https://confluence.example.com/display/SPACE/Page+Title`
3. **Diff-страницы (сравнение версий)**:
   - `https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42`
   - `https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&originalVersion=41&revisedVersion=42`

*Примечание: неподдерживаемые форматы (tiny-link `/x/...` и т.д.) помечаются в `run_report.json` как `invalid_urls` и не валят батч.*

---

## CLI команды и флаги

```text
usage: confluence-md-exporter [-h] [-i INPUT] [-o OUTPUT] [-r] [-c] [-s]

Export Confluence Server/Data Center pages to Markdown.

options:
  -h, --help            Показать справку по командам и выйти
  -i, --input INPUT     Путь к файлу со списком URL (переопределяет EXPORT_INPUT_FILE)
  -o, --output OUTPUT   Каталог для выгрузки (переопределяет EXPORT_OUTPUT_DIR)
  -r, --refresh         Игнорировать disk-skip и принудительно обновить контент (алиас: --force-refresh)
  -c, --clean           Полностью очистить каталог выгрузки перед началом работы
  -s, --simple          Простой синхронный однопоточный вызов без Prefect (KISS режим)
```

---

## Примеры использования

### 1. Быстрый простой запуск (KISS)
Выгрузка страниц по списку из `input/urls.txt` в один поток без оркестрации:
```bash
uv run --env-file .env confluence-md-exporter -s
```

### 2. Чистая выгрузка с очисткой папки
Полная очистка папки `data/` и выгрузка заново:
```bash
uv run --env-file .env confluence-md-exporter -c -s
```

### 3. Принудительное обновление кэша (Refresh)
Перескачивание контента даже при совпадении версий на диске:
```bash
uv run --env-file .env confluence-md-exporter -r -s
```

### 4. Указание произвольных входных и выходных путей
```bash
uv run --env-file .env confluence-md-exporter -i ./my_pages.txt -o ./exports/march_release -s
```

### 5. Выгрузка разницы версий (Diff)
Добавь в файл ссылок URL вида:
```text
https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42
```
И запусти:
```bash
uv run --env-file .env confluence-md-exporter -s
```
В результате в папке `05_diffs/` будет создан файл `607636678_title_v41_to_v42.md` с YAML-метаданными (авторы версий, даты, статистика `+X/-Y`) и блоком ` ```diff `.

---

## Структура выгрузки (Output)

```text
data/
├── 01_raw/             # Сырой Confluence JSON ответа REST API
├── 02_interim/         # Storage XML страницы
├── 03_assets/          # Скачанные вложения и картинки (по page_id)
├── 04_markdown/        # Итоговый Markdown (*.md) и manifest.json
├── 05_diffs/           # Unified diff между версиями страниц (*_v41_to_v42.md)
└── run_report.json     # Сводный отчет о результатах выгрузки батча
```

---

## Коды возврата (Exit Codes)

- `0` — успех (все страницы обработаны со статусом `ok` или `skipped`);
- `1` — частичная ошибка (хотя бы одна страница завершилась со статусом `failed`);
- `2` — критическая ошибка конфигурации / непройденная авторизация / отсутствует входной файл.

---

## Разработка и тестирование

Запуск полного набора тестов:
```bash
uv run python -m pytest
```
