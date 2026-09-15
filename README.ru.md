# confluence-md-exporter

[English](README.md) | **Русский**

Локальная read-only выгрузка страниц **Confluence Server/Data Center** в Markdown: тело страницы, вложения, сравнение версий и отчёт батча.

Не пишет в Confluence, не обходит дерево descendants и не ходит в Cloud. Python `>=3.11,<3.15`.

## Установка

```bash
pip install confluence-md-exporter
```

или

```bash
uv tool install confluence-md-exporter
```

Проверка: `confluence-md-exporter --version`. Справка: `confluence-md-exporter -h`.

## Сценарии

Во всех примерах список ссылок — текстовый файл UTF-8, одна строка = одна страница. Строки `#…` и пустые игнорируются.

### Открытый инстанс

Страницы доступны без логина. База берётся из абсолютных URL — `--base-url` не нужен.

`urls.txt`:

```text
https://confluence.example.com/pages/viewpage.action?pageId=123456
https://confluence.example.com/display/SPACE/Page+Title
```

```bash
confluence-md-exporter -i urls.txt -o output
```

### Закрытый инстанс: Personal Access Token

Токен без имени пользователя → Bearer.

```bash
confluence-md-exporter -i urls.txt -o output -t PAT
```

### Закрытый инстанс: логин и пароль (или логин и PAT)

Имя + токен → HTTP Basic.

```bash
confluence-md-exporter -i urls.txt -o output -u USER -t TOKEN
```

### В списке только идентификаторы страниц

Если строки вида `123456`, а не полные URL, базу нужно указать явно.

`ids.txt`:

```text
123456
789012
```

```bash
confluence-md-exporter -i ids.txt -o output --base-url https://confluence.example.com
```

### Сравнить две версии одной страницы

В список — URL diff из Confluence. В `output/05_diffs/` появится Markdown с YAML-метаданными и блоком ` ```diff `.

```text
https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42
```

```bash
confluence-md-exporter -i urls.txt -o output -t PAT
```

### Повторный прогон, обновление, чистый старт

Повторный запуск в тот же `-o` пропускает страницу, если локальная версия совпала с серверной и файлы вложений на месте (disk-skip).

| Задача | Команда |
|---|---|
| Докачать только изменившееся | `confluence-md-exporter -i urls.txt -o output` |
| Перекачать всё, каталог оставить | `confluence-md-exporter -i urls.txt -o output -r` |
| Удалить выход и выгрузить заново | `confluence-md-exporter -i urls.txt -o output -c` |

Креды можно держать в `.env` (`CONFLUENCE_TOKEN`, `CONFLUENCE_USERNAME`, …). CLI-флаги перекрывают окружение. Файл `.env` в git не коммитится.

## Форматы строк во входном файле

| Формат | Пример |
|---|---|
| Страница по id | `https://host/pages/viewpage.action?pageId=123456` |
| Страница в space | `https://host/wiki/spaces/SPACE/pages/123456/Title` |
| Только id | `123456` (нужен `--base-url`, если в файле нет абсолютных URL) |
| По space и title | `https://host/display/SPACE/Page+Title` |
| Diff версий | `…/pages/diffpagesbyversion.action?pageId=…&selectedPageVersions=41&selectedPageVersions=42` |
| Diff версий | `…/diffpagesbyversion.action?pageId=…&originalVersion=41&revisedVersion=42` |

Неподдерживаемые строки (tiny-link `/x/…` и т.п.) попадают в `run_report.json` как `invalid_urls` и не валят батч.

## Что получается на диске

```text
output/
├── 01_raw/             # сырой JSON REST API
├── 02_interim/         # Storage XML
├── 03_assets/          # вложения и картинки (по page_id)
├── 04_markdown/        # итоговый Markdown и manifest.json
├── 05_diffs/           # unified diff двух версий (*_v41_to_v42.md)
└── run_report.json     # сводка батча
```

## Коды выхода

| Код | Когда |
|---|---|
| `0` | все обработанные страницы `ok` или `skipped` |
| `1` | хотя бы одна страница `failed` |
| `2` | нет входного файла, неверная конфигурация или непройденная авторизация |

## Разработка

```bash
uv sync
uv run python -m pytest
```
