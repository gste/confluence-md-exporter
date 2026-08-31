# AGENTS.md

Standing orders for any AI agent working in this repository.

This file is **process-only**. Product behaviour lives exclusively under `docs/spec/` (the Specification / SDD pack), derived from Init Requirements and accepted ADRs.

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
| How we work             | `docs/process/**` + this file                             |
| Current epic tasks      | `docs/todo/<epic>/` (if present)                          |
| Init Requirements       | `docs/init/` (pre-accept) or `docs/archive/` (historical) |

Rules:

- **Implementation law** = `docs/spec/`. If code and spec disagree, spec wins; open a `spec-patch`, do not “fix in code only”.
- **ADR does not replace spec.** An accepted ADR must be reflected as imperative text in `docs/spec/` in the same change set.
- **Init Requirements do not replace spec.** After the Specification pack is accepted, do not implement from Init or archive.
- Task files under `docs/todo/` are an inbox (links + DoD only), not a second specification. Each file is `kind: feature` or `kind: bug`; implementation branches are `feature/<slug>` or `bugfix/<slug>`.

## Default reading order

**Implementer agent**

1. `AGENTS.md` (this file)
2. `docs/process/workflow.md`
3. `docs/process/roles.md`
4. `docs/spec/README.md` → only sections linked from the current task
5. Task file under `docs/todo/<epic>/` if provided

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

1. Read the task file — including its Spec delta — and **linked** spec sections only. A branch diff replaces neither.
2. Implement the smallest change that satisfies DoD.
3. Add or adjust tests required by the task or by the testing section of the Specification.
4. If the task allows spec edits: change only the anchors listed in the Spec delta, phrased as if the requirement had always been that way, then check `git diff -- docs/spec/` against that list. Anything extra is reverted or escalated.
5. Keep commits focused; PR description cites spec paths (e.g. `docs/spec/0X-name.md#anchor`).
6. If blocked by a missing or contradictory requirement → stop; propose `spec-patch` (and ADR if non-obvious). Do not guess product intent.

## PR expectations

- Prefer one task ≈ one PR.
- No drive-by refactors outside task scope.
- Behaviour change ⇒ spec updated in the same PR or an already-merged prior PR.
- `docs/spec/**` changed ⇒ PR body carries the Spec delta (`ADDED` / `MODIFIED` / `REMOVED` + anchors) and the diff stays inside it.
- After the last task of an epic: clear `docs/todo/<epic>/`.
