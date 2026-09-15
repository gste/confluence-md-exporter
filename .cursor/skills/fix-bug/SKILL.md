---
name: fix-bug
description: Takes exactly one bug from a live observation or a file under docs/todo/<epic>/bug/ — optional run, spec-gap analysis, ADR if needed, spec patch, then surgical code. Use for kind: bug. Do not use for files under docs/todo/<epic>/task/ (that is implement-task).
disable-model-invocation: true
---

# Fix bug

This skill carries no rules of its own. The repository files are the source of truth.

1. Read `docs/process/agent-prompt.md` and follow its core prompt.
2. Read `docs/process/prompts/05-fix-bug.md` and follow it as the procedure for this job.
3. Fix one bug only: the given `bug/` file, or an observation that creates one.

Stop at human gates (ADR accept). After spec is law: tests of the slice must fail on current code, then the fix. Commit each completed step (spec, then green tests+code). If spec was not edited, say `spec unchanged`. Do not mix uncommitted spec and code. Do not merge or push to the default branch.
