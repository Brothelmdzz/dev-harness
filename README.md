# Dev Harness

> Harness Engineering development pipeline for Claude Code.
> Three-layer skill resolution · AutoLoop iteration · Visual HUD · 12 specialized agents.

## What is Dev Harness?

Dev Harness turns Claude Code into a **self-driving development pipeline**. Type `/dev` and it automatically:

1. Detects your tech stack (Gradle, npm, Python, Rust, Go...)
2. Resolves the best Skill for each stage (your project's custom Skill > user-level > built-in generic)
3. Runs through the full pipeline: research → plan → implement → audit → test → review → wiki → commit
4. Auto-continues between phases (Stop Hook prevents Claude from stopping)
5. Self-fixes build failures, test failures, and audit issues (up to 3 retries)

**Inspired by** [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (autonomous experiment loop) and [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) (constraints > prompts).

## Quick Start

```bash
# Install
/plugin marketplace add https://github.com/brothelmdzz/dev-harness
/plugin install dev-harness

# Start developing (any project)
/dev

# AutoLoop mode (fully autonomous)
/dev --auto-loop

# Watch HUD in another terminal
python ~/.claude/plugins/dev-harness/scripts/harness.py hud --watch --rich
```

## Three-Layer Skill Resolution

```
Priority: L1 Project > L2 User > L3 Built-in

L1: .claude/skills/audit-logic/    → Your project's deep audit (Spring Boot, Django, etc.)
L2: ~/.claude/skills/my-audit/     → Your personal audit customization
L3: generic-audit (built-in)       → Works for any project out of the box
```

Same `/dev` command, different depth per project. Zero config for new projects, deep customization for mature ones.

## Pipeline Stages

| Stage | What it does | Auto-fix |
|-------|-------------|----------|
| research | Parallel subagent code scanning | — |
| prd | Multi-turn requirements alignment | — |
| plan | Interactive phase-based planning | — |
| implement | Code changes + gate checks (build/test) | Build failures, test failures |
| audit | Code quality + business logic review | HIGH severity issues |
| docs | API documentation updates | — |
| test | Full test suite + E2E validation | P0 bugs |
| review | 3-way review (Codex×2 + Claude) | CRITICAL issues |
| wiki | Confluence/Lark knowledge sync | — |
| remember | Save progress to semantic memory | — |

## 12 Specialized Agents

| Agent | Model | Role |
|-------|-------|------|
| architect | opus | Architecture review |
| planner | opus | Task decomposition |
| code-reviewer | opus | Logic defect detection |
| executor | sonnet | Standard code implementation |
| debugger | sonnet | Root cause analysis |
| qa-tester | sonnet | Test strategy & case generation |
| security-reviewer | sonnet | OWASP vulnerability detection |
| wiki-syncer | sonnet | Knowledge base synchronization |
| auto-loop | sonnet | Autonomous pipeline iteration |
| explore | haiku | Fast code search |
| gate-checker | haiku | Build/test gate verification |
| skill-router | haiku | Three-layer skill resolution |

## AutoLoop Mode

Inspired by Karpathy's autoresearch: **execute → evaluate → keep/discard → repeat**.

```
/dev --auto-loop

Claude autonomously:
  Phase 1: write code → build ✓ → test ✓ → keep → Phase 2
  Phase 2: write code → build ✗ → auto-fix → build ✓ → keep → Phase 3
  ...
  All phases done → audit (auto-fix HIGH) → test (auto-fix P0) → review → wiki → done

Stops when:
  - All stages DONE (success)
  - Same step fails 3 times (dead loop)
  - Running > 2 hours (configurable)
  - Context > 80% (saves progress)
```

## Visual HUD

### Layer 1: Claude Code Statusline
```
opus-4-6 ctx:34% $0.42 | DH: permit-ext [implement P2/4] 3/9 E:1 AC:3
```

### Layer 2: Rich Terminal Dashboard
```bash
python ~/.claude/plugins/dev-harness/scripts/harness.py hud --watch --rich
```

## Project Configuration

Optional `.claude/dev-config.yml` for project-specific overrides:

```yaml
project: my-project
tech_stack: spring-boot

gates:
  build: "./gradlew build -x test"
  test: "./gradlew test"

skill_overrides:
  audit: my-custom-audit
  test: my-e2e-test

wiki:
  type: confluence
  base_url: "http://wiki.example.com/confluence"
  space_key: MYPROJ
```

## Evaluation Framework

```bash
# Run all tests (21 test cases, 5 dimensions)
python ~/.claude/plugins/dev-harness/eval/eval-runner.py run-all

# Compare before/after
python ~/.claude/plugins/dev-harness/eval/eval-runner.py compare
```

## vs oh-my-claudecode (OMC)

| Feature | OMC | Dev Harness |
|---------|-----|-------------|
| Three-layer Skill resolution | No | **Yes** |
| Configurable YAML pipeline | No (fixed) | **Yes** |
| AutoLoop (autoresearch-style) | No | **Yes** |
| Auto tech stack detection | No | **Yes (7 stacks)** |
| Evaluation framework | No | **Yes (21 tests)** |
| Agent count | 25+ (generic) | 12 (focused) |
| Rate limit recovery | **Yes** | Not yet |
| Notification system | **Yes** | Not yet |

## License

MIT
