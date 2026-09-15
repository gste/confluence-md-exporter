---
name: implement-task
description: Implements exactly one task file from docs/todo/<epic>/task/ with its tests and opens a PR that cites the specification. Use when kind is task. Do not use for docs/todo/<epic>/bug/ or kind: bug (that is fix-bug).
disable-model-invocation: true
---

# Implement task

This skill carries no rules of its own. The repository files are the source of truth.

1. Read `docs/process/agent-prompt.md` and follow its core prompt.
2. Read `docs/process/prompts/04-implement-task.md` and follow it as the procedure for this job.
3. Read the given file under `docs/todo/<epic>/task/`, then only the spec anchors it lists.

A path under `bug/` or `kind: bug` is the wrong job: stop and point to `/fix-bug`. No task file means plan it first or stop and ask. Commit each completed step; tests of the slice must fail on current code before the fix, then go green. On close append Closed and a CHANGELOG Unreleased bullet. If spec was not edited, say `spec unchanged`. Do not merge or push to the default branch.
