# Dev Harness

> Harness Engineering development pipeline for Claude Code.
> Three-layer skill resolution · AutoLoop iteration · Web HUD · 12 specialized agents.

## What is Dev Harness?

Dev Harness turns Claude Code into a **self-driving development pipeline**. Type `/dev` and it automatically:

1. Detects your tech stack (Gradle, npm, Python, Rust, Go...)
2. Resolves the best Skill for each stage (your project's custom Skill > user-level > built-in generic)
3. Runs through the full pipeline: research → plan → implement → audit → test → review → wiki → commit
4. Auto-continues between phases (Stop Hook prevents Claude from stopping)
5. Self-fixes build failures, test failures, and audit issues (up to 3 retries)

**Inspired by** [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (autonomous experiment loop) and [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) (constraints > prompts).

---

## Installation

### Prerequisites

- **Claude Code** (CLI or Desktop)
- **Python 3.8+** — stop hook 和状态管理脚本需要
- **Rich** (可选) — `pip install rich`，增强版终端 HUD 需要

### Step 1: 添加 Marketplace 并安装插件

```bash
# 在 Claude Code 中执行
/plugin marketplace add https://github.com/brothelmdzz/dev-harness
/plugin install dev-harness
```

安装后，插件文件会被复制到 `~/.claude/plugins/cache/dev-harness-marketplace/dev-harness/{version}/`。

### Step 2: 验证安装

```bash
# 验证 Python 可用
python --version

# 运行安装验证脚本（在 Claude Code 中执行）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

### Step 3: 确认自动注册的 Hook

Dev Harness 通过 `hooks/hooks.json` **自动注册** Stop Hook，无需手动修改 `settings.json`。

验证方法：启动新的 Claude Code 会话后，Stop Hook 即自动生效。

### 安装完成后的文件结构

```
~/.claude/plugins/cache/dev-harness-marketplace/dev-harness/{version}/
├── .claude-plugin/
│   ├── plugin.json          # 插件元数据（版本、名称）
│   └── marketplace.json     # Marketplace 定义
├── hooks/
│   ├── hooks.json           # 自动注册 Stop Hook（Claude Code 自动发现）
│   └── stop-hook.py         # 六道防线续跑逻辑
├── scripts/
│   ├── harness.py           # 状态管理 + HUD + Web HUD + CLI
│   ├── skill-resolver.py    # 三层 Skill 解析
│   ├── detect-stack.sh      # 技术栈自动检测
│   ├── worktree.sh          # Git Worktree 隔离
│   ├── scaffold.sh          # Skill 脚手架生成
│   ├── find-dh-home.sh      # Fallback 路径发现
│   ├── setup.sh             # 安装验证
│   └── skill-index.py       # Skill 索引
├── skills/                  # 18 个内置 Skill
│   ├── dev/                 # /dev 入口编排器
│   ├── generic-audit/       # 通用代码审计
│   ├── generic-implement/   # 通用计划执行
│   ├── generic-research/    # 通用代码库研究
│   ├── generic-review/      # 三路联合审查
│   ├── generic-test/        # 通用测试执行
│   └── ...
├── agents/                  # 12 个 Agent 定义
├── defaults/                # pipeline.yml + skill-map.yml
├── templates/               # 项目配置模板
└── eval/                    # 评测框架
```

### 环境变量

Claude Code 为已安装的插件提供两个环境变量：

| 变量 | 说明 |
|------|------|
| `${CLAUDE_PLUGIN_ROOT}` | 插件安装目录的绝对路径。在 Skill/Agent/Hook 内容中自动替换，在子进程中作为环境变量导出。 |
| `${CLAUDE_PLUGIN_DATA}` | 插件持久化数据目录，跨版本更新存活。用于缓存、配置等。 |

### 更新插件

```bash
# 在 Claude Code 中执行
/plugin update dev-harness
```

更新后需要**重启 Claude Code 会话**才能生效（缓存机制）。

### 卸载

```bash
/plugin uninstall dev-harness
```

---

## Quick Start

```bash
# 在任何项目中输入
/dev

# AutoLoop 模式（全自主）
/dev --auto-loop

# 在另一个终端打开 Web HUD（实时可视化面板）
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" web-hud
# 然后打开浏览器访问 http://localhost:1603
```

## Three-Layer Skill Resolution

```
Priority: L1 Project > L2 User > L3 Built-in

L1: .claude/skills/{name}/    → Your project's deep audit (Spring Boot, Django, etc.)
L2: ~/.claude/skills/{name}/  → Your personal audit customization
L3: generic-audit (built-in)  → Works for any project out of the box
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
| review | 3-way review (Codex x2 + Claude) | CRITICAL issues |
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

## Web HUD

实时可视化面板，替代 statusline，独立运行在浏览器中：

```bash
# 在另一个终端启动
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" web-hud

# 自定义端口
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" web-hud --port 8080
```

打开 `http://localhost:1603`，自动 2 秒刷新，显示：
- Pipeline 各阶段状态和耗时
- implement 的 Phase 级进度和门禁结果
- 错误计数、自动续跑次数、自动修复次数
- Session ID 标识

### 终端 HUD（备选）

```bash
# 基础版
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" hud --watch

# Rich 增强版（需要 pip install rich）
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" hud --watch --rich
```

## Session ID Isolation

v3.1 新增。每次 `harness.py init` 时生成唯一 session_id，写入 `harness-state.json`。Stop Hook 只处理匹配当前 session 的状态，防止多个 Claude Code 会话操作同一项目时互相干扰。

```bash
# 自动生成 session_id
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" init "task-name" --route C

# 手动指定 session_id
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" init "task-name" --route C --session-id my-session
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

Templates available: `springboot`, `python`, `nextjs`, `monorepo`, `minimal`

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" --config springboot
```

## Creating Custom Skills

```bash
# 创建项目层 L1 Skill（最高优先级）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" my-audit
# → .claude/skills/my-audit/SKILL.md
```

## Evaluation Framework

```bash
# 运行全部测试（21 test cases, 5 dimensions）
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" run-all

# 生成报告
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" report

# 对比两次评测
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" compare <before> <after>
```

## Troubleshooting

### Stop Hook 不生效

1. 确认 `hooks/hooks.json` 存在于插件目录中
2. **重启 Claude Code 会话**（Hook 在会话启动时加载）
3. 验证 Python 可用：`python --version`

### Web HUD 无数据

Web HUD 读取当前工作目录下的 `.claude/harness-state.json`。确保：
1. 在目标项目目录中启动 web-hud
2. 已通过 `/dev` 或 `harness.py init` 初始化过状态

### 插件更新后行为未变

Claude Code 缓存插件文件。更新后必须重启会话。如仍有问题，手动清理缓存：

```bash
rm -rf ~/.claude/plugins/cache/dev-harness-marketplace/dev-harness/
# 然后重新安装
/plugin install dev-harness
```

## License

MIT
