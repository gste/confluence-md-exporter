# 10 — Transform media and links

## Goal

Вставлять локальные и внешние медиа-ссылки и чинить внутренние ссылки на страницы батча в записанном Markdown.

## Spec

- [`docs/spec/05-transform.md#known-constructs`](../../spec/05-transform.md#known-constructs) (строки `ac:image`, вложение в ссылке, `drawio` / `draw.io`)
- [`docs/spec/05-transform.md#internal-links`](../../spec/05-transform.md#internal-links)
- [`docs/spec/05-transform.md#media-links-integrity`](../../spec/05-transform.md#media-links-integrity)
- [`docs/spec/03-output.md#layout`](../../spec/03-output.md#layout)

## In scope

- картинки из вложений и внешних URL
- файловые ссылки на вложения; drawio preview + `[source](...)`
- относительные `.md` для целей в батче и абсолютный `source_url` иначе; `#anchor`

## Out of scope

- скачивание бинарников (задача 07 уже положила файлы)
- fallback неизвестных макросов
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [07-attachment-download.md](./07-attachment-download.md)
- [09-transform-core.md](./09-transform-core.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_media_links.py`: канон `../03_assets/...` резолвится в существующий файл; внешний URL картинки не переписывается; drawio — preview и source, если есть; missing-attachment не выглядит как `../03_assets/`.
- `tests/test_internal_links.py`: цель в батче → относительный `{page_id}_{slug}.md`; цель вне батча → абсолютный URL; якорь сохраняется.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (макросы; layout путей).
