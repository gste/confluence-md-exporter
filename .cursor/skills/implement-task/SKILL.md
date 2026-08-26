---
name: implement-task
description: Implements exactly one task file from docs/todo/ with its tests and opens a PR that cites the specification. Use when a task file exists and the work is coding, test writing, or a spec-patch limited to a declared Spec delta.
disable-model-invocation: true
---

# Implement task

This skill carries no rules of its own. The repository files are the source of truth.

1. Read `docs/process/agent-prompt.md` and follow its core prompt.
2. Read `docs/process/prompts/04-implement-task.md` and follow it as the procedure for this job.
3. Read the given task file, then only the spec anchors it lists.

No task file means this is the wrong job: plan it first or stop and ask. Do not merge or push to the default branch.
