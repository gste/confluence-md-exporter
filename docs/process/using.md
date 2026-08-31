# Как пользоваться DeltaFuse

DeltaFuse — фреймворк работы через спецификацию. Репозиторий ядра: `delta-fuse`. В продуктовом репозитории ядро лежит как `AGENTS.md` + `docs/process/` (+ тонкие скиллы в `.cursor/skills/`).

Это не спецификация продукта и не how-to оператора CLI. Закон продукта — только `docs/spec/`.

## Состав ядра (копируется целиком)

| Путь | Зачем |
|------|--------|
| `AGENTS.md` | постоянные распоряжения агенту |
| `docs/process/workflow.md` | типы изменений, inbox, коммиты |
| `docs/process/roles.md` | полномочия и human gates |
| `docs/process/agent-prompt.md` | ядро сессии + repo-local addendum |
| `docs/process/STATUS.md` | `stage` (`bootstrap` / `spec-first`) |
| `docs/process/prompts/` | работы `01`–`05` |
| `.cursor/skills/` | вызовы `/init-requirements`, `/init-to-spec`, `/spec-to-epic`, `/implement-task`, `/fix-bug` |

Не копировать из чужого продукта: `docs/spec/`, `docs/init/`, `docs/decisions/`, `docs/todo/` с чужими слайсами, исходный код, корневой операторский `README.md`.

## Подключить к новому репозиторию

1. Скопировать ядро. В [`agent-prompt.md`](./agent-prompt.md) заменить только **Repo-local addendum** (язык, локальные имена).
2. Создать пустые `docs/init/`, `docs/decisions/`, `docs/spec/`, `docs/todo/`, `docs/archive/`. В `docs/todo/README.md` — **Open** и пустая таблица **Closed**.
3. Выставить `stage: bootstrap` в [`STATUS.md`](./STATUS.md). Поле переключает только человек.
4. Написать Init Requirements → при необходимости ADR → пакет `docs/spec/`. Точка приёмки — `docs/spec/README.md`.
5. После приёмки человек ставит `stage: spec-first`. Дальше поставка только по [`workflow.md`](./workflow.md).

## Человек

| Нужно | Куда |
|-------|------|
| Понять закон цепочки | этот файл → [`README.md`](./README.md) → [`workflow.md`](./workflow.md) |
| Принять пакет спеки | `docs/spec/README.md` |
| Принять ADR | `docs/decisions/` (`accepted` / `rejected`) |
| Сменить стадию | [`STATUS.md`](./STATUS.md) |
| Merge в default | человек; агент не пушит и не мерджит |
| Релиз банка | корневой `CHANGELOG.md`: секции `## Версия` и `### Релиз` |

Агент коммитит законченный шаг сам. Ревью и squash — по истории git.

## Агент

Скилл = работа из [`prompts/README.md`](./prompts/README.md). Скилл правил не несёт.

| Вызов | Когда |
|-------|--------|
| `/init-requirements` | нет замысла в `docs/init/`; если файлы уже есть — стоп, A/B/C в работе 01 |
| `/init-to-spec` | `bootstrap`, Init есть, пакета спеки нет |
| `/spec-to-epic` | `spec-first`, нет файла под работу |
| `/implement-task` | файл в `docs/todo/<epic>/task/` |
| `/fix-bug` | файл в `bug/` или наблюдение |

`NN` слайса — сквозной, формула в `docs/todo/README.md`. Номера job-промптов `01`–`05` — другое.

## Имя

В прозе: **DeltaFuse**. Идентификатор репозитория: `delta-fuse`. Не называть ядро «process pack» в новых текстах: одно имя — одно правило.
