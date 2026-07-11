---
description: Run the full dev pipeline (research, plan, implement, audit, test, review)
argument-hint: "[task description]"
---

Invoke the `dev-pipeline` skill to drive this feature or fix through the full automated
pipeline (research to review, with gates and auto-resume).

- `.claude/harness-state.json` exists: always resume the existing run — continue whatever
  stage/phase is currently in progress, regardless of whether `$ARGUMENTS` was passed.
- No state file: `$ARGUMENTS` (if given) becomes the task description for a new run:
  $ARGUMENTS
- To abandon an in-progress task and start over, delete `.claude/harness-state.json` first —
  passing new `$ARGUMENTS` alone does not override an existing run.

Call the `dev-pipeline` skill now. Do not reimplement its orchestration logic here.
