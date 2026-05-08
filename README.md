# Dev Harness

> Self-driving development pipeline for Claude Code & Cursor.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-1.0%2B-purple)](https://claude.ai/code)
[![Cursor](https://img.shields.io/badge/Cursor-2.5%2B-blue)](https://cursor.com)

---

## Why dev-harness

AI coders write code fast, but the *process* still falls back to humans — code review, test execution, audit, documentation. The result is "fast typing, slow shipping."

dev-harness applies **Harness Engineering** — agent scaffolding as load-bearing infrastructure that compensates for what models can't do alone (Anthropic, *Effective harnesses for long-running agents*). One `/dev` command takes a task through research → plan → implement → audit + docs + test → review → remember, with stop-hook defenses that resume the agent when it tries to halt mid-pipeline.

What you get out of the box:

- **One command, full pipeline**: `/dev` resolves the right skill at each stage automatically.
- **Multi-model code review** (v4): three Claude reviewers (sonnet × 2 + opus) plus optional cross-vendor adversarial review via Codex CLI.
- **Six stop-hook defenses**: rate limit, context overflow, timeout, retry storms — never silently dies.

## Quick start

```bash
# Claude Code
/plugin marketplace add brothelmdzz/dev-harness
/plugin install dev-harness && /reload-plugins
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"

# Then in any project
/dev
```

## How it works

```
/dev → skills/dev/SKILL.md (orchestrator)
  → detect-stack.sh + skill-resolver.py + harness.py init
  → Pipeline loop (defaults/pipeline.yml):
        research → prd → plan → implement → [audit | docs | test] → review → remember
                                                  parallel group              three-way
        Each stage completion → harness.py update
        Claude tries to stop → stop-hook.py defenses → blocks if pipeline incomplete
```

**Three-layer skill resolution** — same `/dev`, different projects pick different skills automatically:

```
L1: .claude/skills/{name}/SKILL.md      → project-specific (highest priority)
L2: ~/.claude/skills/{name}/SKILL.md    → user-level overrides
L3: skills/generic-{name}/              → built-in fallback
```

## Core concepts

| Term | One-liner |
|------|-----------|
| **Skill** | A markdown playbook that drives one pipeline stage. Resolved via L1/L2/L3. |
| **Agent** | A specialized sub-agent (12 total) with its own model and tool access. |
| **Hook** | A shell hook into Claude Code's lifecycle (Stop / PostToolUse / SessionStart). |
| **Pipeline** | YAML-defined ordered stages with optional `parallel_group` and `depends_on` DAG. |
| **Route** | Pre-defined pipeline subsets (B = full, C = skip research+prd, C-lite = quick fix). |

## Multi-model code review (v4)

```
Layer 1 — Claude internal heterogeneous (always runs)
  ├─ code-reviewer       (sonnet)   ← code quality, bugs, edge cases
  ├─ security-reviewer   (sonnet)   ← OWASP top 10, secrets, auth
  └─ architect           (opus)     ← architecture, module boundaries

Layer 2 — Cross-vendor adversarial (optional, auto-detect)
  └─ codex exec          (your config)  ← GPT / GLM / o3 / etc. via Codex CLI

Aggregation:
  ≥ 2 channels hit same issue  → high confidence, must fix
  cross-vendor only            → "heterogeneous perspective" section
```

Layer 2 enables itself when `bash scripts/detect-codex.sh` exits 0 and `dev-config.yml` has `review.cross_vendor.enabled: auto` (default). No codex installed? It silently skips.

## Templates & project skeleton

dev-harness ships two kinds of templates under `templates/`:

### Stack-specific configuration (7 presets)

`.claude/dev-config.yml` templates for the most common stacks:

| Template | Stack |
|----------|-------|
| `dev-config-go.yml` | Go (`go build` / `go test`) |
| `dev-config-python.yml` | Python (`uv` / `pytest`) |
| `dev-config-rust.yml` | Rust (`cargo`) |
| `dev-config-nextjs.yml` | Next.js (`npm run build` / `npm test`) |
| `dev-config-springboot.yml` | Spring Boot (`./gradlew`) |
| `dev-config-monorepo.yml` | Multi-package monorepo |
| `dev-config-minimal.yml` | Bare scaffolding (also has v4 `cross_vendor` config example) |

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" --config nextjs
```

### Three-layer regulation skeleton (v4)

`templates/project-skeleton/` — a complete project-level skeleton implementing the "ALL In Code" principle (see [design-philosophy.md](docs/design-philosophy.md) principle 4). Copy it into a new project so the agent finds the context it needs at every stage:

```
.claude/
├── rules/                    constraint layer — naming / style / comments
│                             / structure / safety (5 counter-example-immune samples)
├── code-design/              demonstration layer — api-handler /
│                             react-component / crud-page templates
├── ui-design/                visual layer — HTML high-fidelity mockup
├── handbooks/                operations — deployment / 3rd-party integration
├── runbooks/                 incident response playbooks
└── pitfall-journal.jsonl     failure log (auto-populated by v4 stop-hook)

docs/release-notes/           release notes
```

20 files across 8 directories, each with a README explaining what gap it compensates for. The three layers come from Dewu's [Spec Coding methodology](docs/external-references-2026-05.md); the skeleton bundles in handbooks / runbooks / pitfall-journal from Alibaba's "ALL In Code" approach.

## Comparison: bare Claude Code vs Dev Harness

| Capability | Bare Claude Code | + Dev Harness |
|------------|------------------|---------------|
| Multi-stage pipeline | manual orchestration | one `/dev` runs full flow |
| Skill resolution | global skills only | three-layer (project > user > built-in) |
| Stop discipline | trust the agent | six defenses + auto-resume on incomplete |
| Code review | one model, one pass | 3 Claude reviewers + optional codex cross-vendor |
| Pitfall learning | manual | journal → ground-truth injection on resume |
| State observability | conversation only | live state file + Web HUD |
| Parallel agents | manual subagent calls | orchestrator mode auto-triggers when phases > 3 |

## Documentation

- [Design Philosophy](docs/design-philosophy.md) — eight principles + nine red lines
- [External References (May 2026)](docs/external-references-2026-05.md) — distilled methodologies from 5 industry case studies
- [Quick Start](docs/quickstart.md) — first-time walkthrough
- [Contributing](docs/contributing.md)
- [Known Issues](docs/known-issues.md)
- [Changelog](CHANGELOG.md)

## Installation

### Claude Code

```bash
/plugin marketplace add brothelmdzz/dev-harness
/plugin install dev-harness && /reload-plugins
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

### Cursor 2.5+

```bash
/add-plugin brothelmdzz/dev-harness
bash "${CURSOR_PLUGIN_ROOT}/scripts/setup.sh"
```

### Manual (Codex / Gemini / other Agent Skills compatible tools)

```bash
git clone https://github.com/brothelmdzz/dev-harness.git ~/.claude/plugins/dev-harness
bash ~/.claude/plugins/dev-harness/scripts/setup.sh
```

setup.sh creates an isolated `.venv` inside the plugin directory. No global Python is touched, no `~/.claude/` writes, no `settings.json` modifications.

## Commands

| Command | Mode | When | Pipeline |
|---------|------|------|----------|
| `/dev` | pipeline | New feature, mid-large change | full |
| `/fix` | single | Bug fix, small change | implement + test |
| `/test` | single | Verify existing code | test only |
| `/audit` | single | Quality/spec audit | audit only |
| `/review` | single | PR review | three-way (+ optional codex) |
| `/ask` | conversation | Q&A, no code change | none, stop-hook stays out |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Hook path stale after upgrade | `bash "${CLAUDE_PLUGIN_ROOT}/scripts/fix-hook-path.sh"` |
| `implement` halts mid-stage | check `.claude/harness-state.json` phases — empty triggers plan-watcher fallback automatically |
| Web HUD has no data | `harness.py web-hud --project /path` |
| Cross-vendor review never runs | `bash scripts/detect-codex.sh -v` to see why |

## CLI reference

<details>
<summary>Click to expand</summary>

```bash
# State management
harness.py init "task" --route C [--mode pipeline|single|conversation]
harness.py update <stage> <status> [--phase N] [--gate build=pass]
harness.py detect-mode
harness.py analyze-deps

# Worker management (orchestrator mode)
harness.py worker-report <id> --phase <N> --status DONE [--branch <b>]
harness.py worker-status
harness.py worker-cleanup

# Visualization
harness.py web-hud [--port 1603] [--bind 127.0.0.1] [--project /path]
harness.py hud --watch --rich

# Skill resolution
skill-resolver.py <stage> [--profile frontend] [--verbose]
skill-resolver.py --all

# v4 ABC tooling
bash scripts/detect-codex.sh                    # check codex CLI for cross-vendor review
python scripts/pitfall-analyze.py --threshold 3 # promote recurring failures into rules

# Notification + team report + skill suggest
notify.py --title "X" --message "Y" --level success [--lark]
team-report.py [--json] [-o report.md]
skill-suggest.py [--threshold 80] [--consecutive 3]

# Version sync
bash scripts/sync-plugin-meta.sh [3.4.1]
```

</details>

## Project configuration

Optional `.claude/dev-config.yml`:

```yaml
project: my-project
gates:
  build: "./gradlew build -x test"
  test:  "./gradlew test"

# v4: cross-vendor review (optional)
review:
  cross_vendor:
    enabled: auto    # auto | true | false
    provider: codex

# Defense limits (override defaults)
limits:
  stage_timeout: 1800
  max_duration:  7200
  max_retries:   3

# Skill overrides
skill_overrides:
  audit: my-custom-audit
```

Templates live in `templates/dev-config-{go,python,rust,nextjs,springboot,monorepo,minimal}.yml`.

## Compatibility

Built on the [Agent Skills](https://agentskills.io) open standard. SKILL.md format is portable across:

Claude Code · Cursor · Gemini CLI · GitHub Copilot · VS Code · OpenAI Codex · OpenHands · Roo Code · 30+ platforms

## Acknowledgments

This project's design draws from:

- Anthropic — [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps), [Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- OpenAI — [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/), [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/), [Unlocking the Codex harness](https://openai.com/index/unlocking-the-codex-harness/)
- Industry case studies (digested in [docs/external-references-2026-05.md](docs/external-references-2026-05.md)) — Dewu × 2, Tencent × 2, Alibaba

See [docs/design-philosophy.md](docs/design-philosophy.md) for how these inform the eight design principles and nine architectural red lines.

## License

MIT — see [LICENSE](LICENSE).
