---
name: init-requirements
description: Captures product intent as Init Requirements under docs/init/ before any specification exists. Use at repository bootstrap when the product is not described yet. If docs/init already has files, follow the existing-init fork in the job prompt before writing.
disable-model-invocation: true
---

# Init requirements

This skill carries no rules of its own. The repository files are the source of truth.

1. Read `docs/process/agent-prompt.md` and follow its core prompt (role, law chain, stage, preamble, prohibitions, stop-and-ask).
2. Read `docs/process/prompts/01-init-requirements.md` and follow it as the procedure for this job.
3. Take the product intent from the human. Do not invent requirements.

Output goes to files under `docs/init/`, never to chat only. Do not write the spec pack, tasks, or product code in this job.
