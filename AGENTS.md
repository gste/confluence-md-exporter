# AGENTS.md

Standing orders for any AI agent working in a **DeltaFuse** repository (`delta-fuse`: this file + `docs/process/`).

This file is **process-only**. Product behaviour lives exclusively under `docs/spec/` (the Specification / SDD pack), derived from Init Requirements and accepted ADRs. How to adopt the framework: `docs/process/using.md`.

## Source of truth chain

```text
Init Requirements + Architecture Decisions (ADR)
    → Specification (docs/spec/)      ← sole implementation law
        → Atomic tasks (docs/todo/)
            → Implementation
```

| Need                    | Read                                                      |
|-------------------------|-----------------------------------------------------------|
| What to implement       | `docs/spec/**` only                                       |
| Why a decision was made | `docs/decisions/**`                                       |
| How we work             | DeltaFuse: `docs/process/**` + this file                  |
| Current epic tasks      | `docs/todo/<epic>/` (if present)                          |
| Init Requirements       | `docs/init/` (pre-accept) or `docs/archive/` (historical) |

Rules:

- **Implementation law** = `docs/spec/`. If code and spec disagree, spec wins; open a `spec-patch`, do not “fix in code only”.
- **ADR does not replace spec.** An accepted ADR must be reflected as imperative text in `docs/spec/` in the same change set.
- **Init Requirements do not replace spec.** After the Specification pack is accepted, do not implement from Init or archive.
- Task files under `docs/todo/` are an inbox (links + DoD only), not a second specification. Layout: `docs/todo/<epic>/task/` (`kind: task`, branch `feature/<slug>`) and `docs/todo/<epic>/bug/` (`kind: bug`, branch `bugfix/<slug>`). `NN` is repo-wide: next = `1 + max(Closed ∪ live task/bug files)` in `docs/todo/README.md`. A `bug` file carries `opened` (YYYY-MM-DD) and may include a `Run` note without secrets. Implement `task/` with `/implement-task`; take a bug with `/fix-bug`. Closing a slice deletes the file, appends Closed, and adds one `CHANGELOG.md` Unreleased bullet; an empty epic directory is removed.
- User-facing chat follows the Language table in `docs/process/README.md` (Russian), even though this file is English. Exception: the human wrote this turn in English.

## Default reading order

**Implementer agent**

1. `AGENTS.md` (this file)
2. `docs/process/workflow.md`
3. `docs/process/roles.md`
4. `docs/spec/README.md` → only sections linked from the current task
5. Task file under `docs/todo/<epic>/task/` or `docs/todo/<epic>/bug/` if provided

**Planner / auditor agent**

1. This file + `docs/process/**`
2. Spec index + relevant ADRs in `docs/decisions/`
3. Diff or draft under review

Do not load the entire Specification pack unless the task explicitly spans multiple modules.

## Hard prohibitions

- Do not invent requirements missing from `docs/spec/`.
- Do not implement from chat history, Init Requirements, archive, or ADR text alone.
- Do not expand scope beyond what the active Specification states as in-scope.
- Do not log or commit secrets, tokens, or raw credential files.
- Do not change `docs/spec/**` or `docs/decisions/**` unless the task explicitly allows it.
- Do not edit spec anchors outside the declared Spec delta, and do not rewrite a chapter “while you are in there”.
- Do not add changelog ledgers to `docs/spec/**` (`ADDED` / `MODIFIED` / `REMOVED` lists, “was / now”, dated entries). The pack states only how the system works now; intent lives in `docs/todo/` and the PR.
- Do not treat a branch diff as the source of requirements — it is evidence, `docs/spec/**` is law.
- Do not duplicate long requirement text under `docs/todo/` (links + DoD only).

## Change types (summary)

| Type         | Spec first?      | ADR?            | When                                        |
|--------------|------------------|-----------------|---------------------------------------------|
| `trivial`    | no               | no              | no contract/behaviour change                |
| `spec-patch` | yes              | no              | behaviour/contract change; decision obvious |
| `adr+spec`   | yes              | yes             | non-obvious design fork                     |
| `epic`       | yes (spec green) | if forks remain | multi-slice delivery                        |

Full rules: `docs/process/workflow.md`.

## Human gates (do not skip)

Stop and request a human when:

- Accepting or rejecting an ADR
- Merging contract changes in `docs/spec/`
- Merging non-trivial work to the default branch
- Security, credentials, or trust-boundary changes
- Spec is silent or contradictory and a product choice is required
- The task touches a human-gated area declared in `docs/spec/`

Details: `docs/process/roles.md`.

## How to implement a task

`/implement-task` is only for `docs/todo/<epic>/task/`. A bug is `/fix-bug`.

1. Read the task file — including its Spec delta — and **linked** spec sections only. A branch diff replaces neither.
2. Implement the smallest change that satisfies DoD.
3. Add or adjust tests required by the task or by the testing section of the Specification.
4. If the task allows spec edits: change only the anchors listed in the Spec delta, phrased as if the requirement had always been that way, then check `git diff -- docs/spec/` against that list. Anything extra is reverted or escalated. If `docs/spec/**` was not edited, say `spec unchanged` in the closing answer.
5. If the operator surface changed (CLI, env, input, exit codes, output layout, report/manifest shape), update the root `README.md` how-to; it is not a second specification. Otherwise say `README unchanged`.
6. Commit each completed step yourself (`git add` only that step’s files). For `spec-patch`: spec commit, then code commit. Do not wait to be asked. Commit messages in English. Do not amend, push, or merge to the default branch.
7. When closing the slice: delete the inbox file, append Closed in `docs/todo/README.md`, add one Unreleased bullet to `CHANGELOG.md` (`- NN short phrase`). PR description cites spec paths (e.g. `docs/spec/0X-name.md#anchor`).
8. If blocked by a missing or contradictory requirement → stop; propose `spec-patch` (and ADR if non-obvious). Do not guess product intent.

## PR expectations

- Prefer one task ≈ one PR.
- The implementing PR deletes the closed inbox file (`task/` or `bug`), appends Closed, adds a `CHANGELOG.md` Unreleased bullet, and removes the epic README row; delete `docs/todo/<epic>/` if nothing remains.
- No drive-by refactors outside task scope.
- Behaviour change ⇒ spec updated in the same PR or an already-merged prior PR.
- `docs/spec/**` changed ⇒ PR body carries the Spec delta (`ADDED` / `MODIFIED` / `REMOVED` + anchors) and the diff stays inside it.
- After the last remaining slice of an epic: delete `docs/todo/<epic>/`. Each implementing PR already deletes its own inbox file.
