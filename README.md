# confluence-md-exporter

Локальный read-only конвейер: страницы Confluence Server/Data Center → Markdown, медиа и каталог батча. Закон реализации — [`docs/spec/README.md`](docs/spec/README.md). Этот файл — как запустить, не спецификация.

## Установка

Python `>=3.11,<3.14`. Пакетный менеджер — `uv`.

```text
uv sync
```

## Окружение

Скопируй [`.env.example`](.env.example) в `.env` и заполни. Файл `.env` в git не коммитится. CLI его **сам не читает** — передай в процесс:

```text
uv run --env-file .env confluence-md-exporter
```

Обязательно:

- `CONFLUENCE_BASE_URL` — origin (схема + хост, без пути `/wiki`, без хвостового `/`)
- `CONFLUENCE_AUTH_TYPE` — `bearer` или `basic`
- `CONFLUENCE_TOKEN` — PAT или пароль

Для `basic` ещё `CONFLUENCE_USERNAME`. Редакция по умолчанию — `datacenter`; иное значение — невозможный старт.

## Вход

Список URL: `input/urls.txt` (UTF-8, одна строка на запись; `#` и пустые строки игнорируются).

Принимаются: `viewpage.action?pageId=`, `/display/SPACE/Title`, `/wiki/spaces/.../pages/<id>/…`, голый `pageId`. Tiny-link `/x/<hash>` и прочие формы — невалидные: в `run_report.json` как `invalid_urls`, батч не валят.

## Запуск

```text
uv run --env-file .env confluence-md-exporter
```

Флаги: `--input`, `--output`, `--force-refresh` (полная перевыгрузка, без disk-skip).

Коды выхода: `0` — нет страниц `failed`; `1` — есть `failed`; `2` — невозможный старт (конфиг, 401, нет входного файла).

## Выход

Корень по умолчанию — `data/`:

```text
data/
├── 01_raw/
├── 02_interim/
├── 03_assets/
├── 04_markdown/          # *.md и manifest.json
└── run_report.json
```
