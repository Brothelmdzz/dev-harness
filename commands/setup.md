---
description: Doctor and optionally repair the dev-harness plugin install (venv, deps, hook trust, plugin integrity)
argument-hint: '[--fix] [--json]'
allowed-tools: Bash(bash:*), AskUserQuestion
---

Run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/setup_report.py" --json $ARGUMENTS
```

The script prints a JSON report `{ready, host, checks[], actionsTaken[], nextSteps[]}`. It is a read-only doctor unless `--fix` is passed.

If `ready` is `false` AND the user did not already pass `--fix` AND at least one check has a non-empty `fix_hint`:
- Use `AskUserQuestion` exactly once to ask whether Claude should run the automatic repair now.
- Put the repair option first and suffix it with `(Recommended)`.
- Use these two options:
  - `Run --fix (Recommended)`
  - `Skip for now`
- If the user chooses repair, rerun with `--fix`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/setup_report.py" --json --fix
```

If `ready` is already `true`, or the user passed `--fix`, or no check is fixable:
- Do not ask about repair.

Output rules:
- Present the final report to the user as a readable summary: list each check's status (ok/warn/fail/skip) with its detail, then `actionsTaken`, then `nextSteps`.
- Preserve every `nextSteps` entry verbatim — they carry Codex hook-trust guidance and the acceptance-test instruction.
- If repair ran, show `actionsTaken` so the user sees exactly what changed.
