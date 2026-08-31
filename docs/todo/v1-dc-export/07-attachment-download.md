# 07 — Attachment download

## Goal

Скачивать вложения только REST-путём с тем же Authorization и класть их в `03_assets/` под безопасными именами.

## Spec

- [`docs/spec/04-fetch.md#attachments`](../../spec/04-fetch.md#attachments)
- [`docs/spec/03-output.md#asset-sidecar`](../../spec/03-output.md#asset-sidecar)
- [`docs/spec/03-output.md#safe-filename`](../../spec/03-output.md#safe-filename)
- [`docs/spec/01-configuration.md#http-transport`](../../spec/01-configuration.md#http-transport)

## In scope

- download по REST `_links.download` (или эквивалент), follow redirects, без cookie
- вложение с другой страницы: успех или плейсхолдер, страница не `failed`
- карта original→safe на диске
- две версии одного имени — только current

## Out of scope

- UI-путь `/download/attachments/...` как основной способ
- disk-skip
- [`docs/spec/00-context.md#out-of-scope`](../../spec/00-context.md#out-of-scope)

## Depends on

- [04-slug-and-layout.md](./04-slug-and-layout.md)
- [06-http-and-page-fetch.md](./06-http-and-page-fetch.md)

## Spec delta

none

## Spec edits allowed

no

## Definition of Done

- `tests/test_attachment_download.py` на моках: основной путь не `/download/attachments/`; тот же Authorization; чужое недоступное вложение → `[missing-attachment: …]` и страница не `failed`; sidecar отражает итог имён.
- Human-gated: [`docs/spec/00-context.md#human-gated-areas`](../../spec/00-context.md#human-gated-areas) (протокол вложений).
