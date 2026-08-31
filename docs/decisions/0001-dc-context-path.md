# 0001 — Data Center context path

```yaml
status: accepted
date: 2026-08-31
```

Человек выставляет `accepted` или `rejected`. Пока `proposed`, это не закон для кода.

## Context

`CONFLUENCE_BASE_URL` сейчас — origin без пути. REST собирается как `{origin}/rest/api/...`. Входные формы сравниваются с путями вида `/pages/viewpage.action`, `/display/...`.

Живой прогон против Server/DC: приложение смонтировано в `/confluence`. `GET {origin}/rest/api/user/current` → 404. Тот же PAT на `GET {origin}/confluence/rest/api/user/current` → 200. Входные URL вида `{origin}/confluence/pages/...` и `{origin}/confluence/display/...` резолвер не принимает, даже если форма в остальном штатная.

Запрет пути `/wiki` остаётся: это маркер Cloud и out of scope.

## Options

| ID | Вариант                                                                                                                                                               |
|----|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A  | `CONFLUENCE_BASE_URL` допускает контекст-путь, кроме `/wiki` и кроме завершающего `/`. Пример: `https://host/confluence`. REST и разбор URL — относительно этой базы. |
| B  | Origin без пути как сейчас плюс отдельный ключ `CONFLUENCE_CONTEXT_PATH` (например `/confluence`).                                                                    |
| C  | Контекст-путь не поддерживается. Оператор обязан выставить reverse-proxy так, чтобы `{origin}/rest/api` попадал в приложение.                                         |

## Recommendation

A: один ключ, совпадает с тем, как оператор копирует URL из браузера, меньше скрытого состояния, чем B. C оставляет типичный DC-деплой нерабочим при корректном токене.

## Consequences if A

- Нормализация base URL меняется: путь разрешён, если он не `/wiki` и не содержит `/wiki/`.
- Резолвер сравнивает path относительно базы приложения, а не origin.
- Клиент ходит на `{base}/rest/api/...`.
- `.env.example` показывает пример с контекст-путём.
- Tiny-link по-прежнему out of scope.
