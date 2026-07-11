---
description: Run the full dev pipeline (research, plan, implement, audit, test, review)
argument-hint: "[task description]"
---

Invoke the `dev-pipeline` skill to drive this feature or fix through the full automated
pipeline (research to review, with gates and auto-resume).

- No `$ARGUMENTS`: resume the existing run from `.claude/harness-state.json` — continue
  whatever stage/phase is currently in progress.
- `$ARGUMENTS` provided: start a new pipeline run, using it as the task description:
  $ARGUMENTS

Call the `dev-pipeline` skill now. Do not reimplement its orchestration logic here.
