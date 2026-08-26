---
name: init-to-spec
description: Assembles the modular Specification pack under docs/spec/ from Init Requirements and accepted ADRs. Use during bootstrap when docs/init/ is filled and the spec pack is missing, incomplete, or still a monolith, so the human gets a single review entry to accept.
disable-model-invocation: true
---

# Init to spec

This skill carries no rules of its own. The repository files are the source of truth.

1. Read `docs/process/agent-prompt.md` and follow its core prompt.
2. Read `docs/process/prompts/02-init-to-spec.md` and follow it as the procedure for this job.
3. Inputs are `docs/init/**` plus ADRs with `status: accepted` only.

`docs/spec/README.md` is the single review and acceptance entry of the pack. Do not open epics, do not write product code, do not flip `docs/process/STATUS.md`.
