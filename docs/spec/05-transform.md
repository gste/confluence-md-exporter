# Transform: Storage Format to Markdown

Норма — наблюдаемый Markdown, не внутренний разбор. Вход — `body_storage`. Выход — GFM-тело файла gold и заполненный `unsupported_macros`.

Тело — Storage Format (XHTML-фрагмент с префиксами `ac:` / `ri:`). Трансформер разбирает его как XML с пространствами имён Confluence:

```text
ac  http://www.atlassian.com/schema/confluence/4/ac/
ri  http://www.atlassian.com/schema/confluence/4/ri/
```

Страница не переходит в `failed` только из‑за неизвестного макроса или перечисленных краевых случаев. Битый XML тела, который нельзя разобрать, — `failed` с причиной в отчёте; остальные страницы батча продолжаются.

## Known constructs

| Источник | Результат |
|---|---|
| Обычный HTML `p`, `h1`–`h6`, `ul`, `ol`, `li`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `em`, `strong`, `code`, `pre`, `br`, `hr`, `a` | GFM / ATX / pipe-tables |
| Макрос `code` | fenced-блок; язык из параметра макроса, иначе `text` |
| `plantuml` / `plantumlcloud` | fenced `plantuml`; картинка не рендерится |
| `drawio` / `draw.io` | ссылка на preview png/svg среди вложений страницы, если есть; если есть исходник `.drawio` или `.xml` — вторая ссылка `[source](...)` |
| `info`, `note`, `panel` | `> [!NOTE]` |
| `warning`, `error` | `> [!WARNING]` |
| `tip`, `success` | `> [!TIP]` |
| `ac:image` + вложение | локальная картинка по каноническому относительному пути |
| `ac:image` + внешний URL | внешний URL без переписывания |
| вложение в ссылке | локальная файловая ссылка по каноническому пути |
| `expand` | `<details><summary>…</summary>…</details>` |
| `status` | код-спаны с текстом статуса; цвет игнорируется |
| task list | `- [x]` / `- [ ]` |
| emoticon | `:name:`, где `name` — атрибут `ac:name` (иначе `ac:emoji-shortname`; если нет ни того ни другого — `emoticon`) |
| ссылка на пользователя | `@displayName`, если display name есть; иначе `@accountId` |
| дата/time | ISO-дата текстом |

Канонический путь медиа — `../03_assets/<page_id>/<safe_filename>` ([03-output.md#layout](./03-output.md#layout)).

Для callout-макросов тело макроса становится телом callout (каждая строка с префиксом `>`). Для `expand` текст `summary` берётся из параметра title; если параметра нет — `Details`.

Макрос `code`: если в содержимом есть ряд из трёх или более обратных кавычек, ограда fenced-блока длиннее любого такого ряда (минимум три).

## Internal links

`ac:link` с `ri:page`:

- если `page_id` цели входит в текущий батч (уникальные валидные id этого запуска) — относительная ссылка на файл `04_markdown/<page_id>_<slug>.md` цели (из соседнего `.md` это `{page_id}_{slug}.md`);
- иначе — абсолютный `source_url` цели: при известном `page_id` — `{CONFLUENCE_BASE_URL}/pages/viewpage.action?pageId={id}`; при известных space + title без id — `{CONFLUENCE_BASE_URL}/display/{space}/{title}` с URL-encoding заголовка;
- фрагмент `#anchor` сохраняется суффиксом, если якорь известен из ссылки.

Ссылки чинятся так, чтобы в записанном Markdown выполнялось это правило. Промежуточное представление в коде не нормируется.

## Unknown macros

Любой макрос `ac:structured-macro` (и эквивалент), которого нет в таблице известных конструкций, обрабатывается так:

1. В тело вставляется HTML-комментарий `<!-- unsupported-macro: <name> -->`.
2. Текстовое содержимое макроса (рекурсивно извлечённый текст) сохраняется сразу после комментария.
3. `<name>` добавляется в `unsupported_macros` frontmatter (без дубликатов, порядок первого появления).

Пайплайн из‑за неизвестного макроса не падает. Страница остаётся `ok`, если нет другой ошибки.

## Edge cases

Обязаны не валить страницу в неопределённое состояние:

| Случай | Поведение |
|---|---|
| Пустое тело | страница `ok`, Markdown с frontmatter и пустым телом |
| Макрос без body | обёртка конструкции пишется без внутреннего текста |
| Тройные бэктики внутри code-блока | ограда длиннее содержимого |
| Два вложения с одним именем разных версий | на диск и в ссылки — только current |
| Вложение с другой страницы | скачать либо плейсхолдер `[missing-attachment: <original_name>]` и предупреждение; страница не `failed` |
| Таблица с colspan/rowspan | GFM без объединения ячеек: атрибуты объединения игнорируются, строки дополняются пустыми ячейками до прямоугольника |
| HTML-entities в title | декодируются до slug, frontmatter и breadcrumbs |
| `trashed` или 404 | `skipped`, запись в отчёт |
| 403 | `failed` / `forbidden`, без ретраев |

## Media links integrity

Каждая ссылка вида `../03_assets/...` в записанном Markdown резолвится в существующий файл относительно каталога `04_markdown/`. Исключение — плейсхолдер missing-attachment, который не является путём `../03_assets/`.
