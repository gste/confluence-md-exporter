# confluence-md-exporter

Локальный read-only конвейер: выгрузка страниц Confluence Server/Data Center → Markdown, медиа-ассеты, diff-сравнение версий и каталог батча. Закон реализации — [спецификация](https://github.com/gste/confluence-md-exporter/blob/master/docs/spec/README.md).

## Установка

Требуется Python `>=3.11,<3.14`.

```bash
pip install confluence-md-exporter
```

Или через `uv`:

```bash
uv tool install confluence-md-exporter
```

Из исходников:

```bash
uv sync
```

## Запуск

По умолчанию: вход `input/urls.txt`, выход `output/`, доступ анонимный. База Confluence берётся из абсолютных URL в списке — отдельный `--base-url` не нужен, если в файле есть полные ссылки.

Стартовый список ссылок:

```bash
cp input/urls.txt.example input/urls.txt
```

Закрытый инстанс (нужны учётные данные):

```bash
uv run confluence-md-exporter -u USER -t TOKEN
```

Только PAT (Bearer):

```bash
uv run confluence-md-exporter -t TOKEN
```

`.env` не обязателен. Если удобнее держать креды в файле — [`.env.example`](https://github.com/gste/confluence-md-exporter/blob/master/.env.example) и `uv run --env-file .env confluence-md-exporter`. CLI-флаги перекрывают окружение.

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
usage: confluence-md-exporter [-h] [--version] [-i INPUT] [-o OUTPUT]
                              [-u USER] [-t TOKEN] [--base-url URL] [-r] [-c] [-s]

options:
  --version             Версия пакета
  -i, --input INPUT     Список URL (default: input/urls.txt)
  -o, --output OUTPUT   Каталог выгрузки (default: output)
  -u, --user USER       Имя пользователя (вместе с -t — HTTP Basic)
  -t, --token TOKEN     PAT или пароль
  --base-url URL        База инстанса, если её нельзя вывести из списка URL
  -r, --refresh         Игнорировать disk-skip
  -c, --clean           Очистить каталог выгрузки перед работой
```

Выгрузка всегда однопоточная: один процесс, страницы строго последовательно, без Prefect и без лишних серверов. В консоли на уровне INFO виден прогресс каждой страницы и итоговая сводка.

---

## Примеры использования

### 1. Обычный запуск
Выгрузка страниц по списку из `input/urls.txt` (анонимно, база из URL):
```bash
uv run confluence-md-exporter
```

### 2. Чистая выгрузка с очисткой папки
Полная очистка папки выгрузки и выгрузка заново:
```bash
uv run confluence-md-exporter -c
```

### 3. Принудительное обновление кэша (Refresh)
Перескачивание контента даже при совпадении версий на диске:
```bash
uv run confluence-md-exporter -r
```

### 4. Указание произвольных входных и выходных путей
```bash
uv run confluence-md-exporter -i ./my_pages.txt -o ./exports/march_release
```

### 5. Выгрузка разницы версий (Diff)
Добавь в файл ссылок URL вида:
```text
https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42
```
И запусти:
```bash
uv run confluence-md-exporter
```
В результате в папке `05_diffs/` будет создан файл `607636678_title_v41_to_v42.md` с YAML-метаданными (авторы версий, даты, статистика `+X/-Y`) и блоком ` ```diff `.

---

## Структура выгрузки (Output)

```text
output/
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
