# Dev Harness

> Harness Engineering development pipeline for Claude Code.
> Three-layer skill resolution · Multi-agent parallel · Web HUD · 12 specialized agents.

## What is Dev Harness?

Dev Harness turns Claude Code into a **self-driving development pipeline**. Type `/dev` and it automatically:

1. Detects your tech stack (Gradle, npm, Python, Rust, Go...)
2. Resolves the best Skill for each stage (your project's custom Skill > user-level > built-in generic)
3. Runs through the full pipeline: research → plan → implement → [audit + docs + test 并行] → review → remember
4. Auto-continues between phases (Stop Hook prevents Claude from stopping)
5. Self-fixes build failures, test failures, and audit issues (up to 3 retries)
6. Phase > 3 时自动触发 Orchestrator 模式，多 Worker 并行在独立 worktree 中执行

**Inspired by** [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) (autonomous experiment loop) and [OpenAI's Harness Engineering](https://openai.com/index/harness-engineering/) (constraints > prompts).

---

## Installation

### Prerequisites

- **Claude Code** (CLI or Desktop)
- **Python 3.8+** — `python --version` 验证
- **filelock** — `pip install filelock`（多 Agent 并行状态保护，必需）
- **Rich** (可选) — `pip install rich`，增强版终端 HUD

### Step 1: 添加 Marketplace 并安装插件

**Claude Code:**
```bash
/plugin marketplace add brothelmdzz/dev-harness
/plugin install dev-harness
/reload-plugins
```

**Cursor 2.5+:**
```bash
/add-plugin brothelmdzz/dev-harness
```

> Dev Harness 同时支持 Claude Code 和 Cursor（Agent Skills 开放标准）。Skills、Hooks、Agents 格式通用，无需适配。

### Step 2: 运行安装验证

```bash
# 在 Claude Code 中执行（自动检测依赖 + 部署 hook wrapper + 运行评测）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

setup.sh 会做以下事情：
1. 检查 Python、filelock、Rich 依赖
2. 验证插件文件完整性
3. **部署 Stop Hook wrapper** 到 `~/.claude/hooks/dev-harness-stop.py`（解决版本升级后路径失效）
4. 自动修正 `settings.json` 中的 hook 路径
5. 运行 43 个评测用例验证功能正确

### Step 3: 确认 Hook 自动注册

Dev Harness 通过 `hooks/hooks.json` **自动注册** 两个 Hook：
- **Stop Hook** — 阻止 Pipeline 中途停下，六道防线保护
- **PostToolUse Hook (plan-watcher)** — Plan 文件写入时自动注册 phases

验证方法：启动新的 Claude Code 会话后，Hook 即自动生效。

### 安装完成

```
✅ Python 3.x
✅ filelock
✅ Rich (可选)
✅ 插件文件完整
✅ Stop Hook wrapper 已部署
✅ 43/43 评测通过
```

---

## Quick Start

### 基本使用

```bash
# 在任何项目目录中输入
/dev

# Claude 会自动:
#   1. 检测技术栈
#   2. 询问任务名称和类型
#   3. 按 Pipeline 自动推进全流程
#   4. 中途不停（Stop Hook 续跑）
```

### 指定路线

Pipeline 有 5 条路线，控制流程深度：

| 路线 | 阶段 | 适用场景 |
|------|------|---------|
| **B** | research → prd → plan → implement → audit → docs → test → review → remember | 大型新功能 |
| **A** | prd → plan → implement → audit → docs → test → review → remember | 中型功能 |
| **C** | plan → implement → audit → docs → test → review → remember | **最常用** |
| **C-lite** | implement → test → remember | 小修复 |
| **D** | implement → test → remember | 同 C-lite |

Claude 会根据任务复杂度自动选择路线，也可手动指定。

### Web HUD（实时可视化面板）

在另一个终端启动，实时查看 Pipeline 进度：

```bash
# 方法 1: 直接用 Windows 路径启动（CMD/PowerShell）
python C:\Users\<你的用户名>\.claude\plugins\cache\dev-harness-marketplace\dev-harness\<版本号>\scripts\harness.py web-hud

# 方法 2: 在 Claude Code 中用 ! 前缀运行
! python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" web-hud

# 方法 3: Git Bash 中
python ~/.claude/plugins/cache/dev-harness-marketplace/dev-harness/*/scripts/harness.py web-hud
```

然后打开浏览器访问 **http://localhost:1603**

**Web HUD 特性**：
- 多项目 tab 切换（同时监控多个 /dev 会话）
- Pipeline 各阶段进度条 + 状态颜色
- implement Phase 级进度 + 门禁结果 + error 计数
- parallel_group 标注
- 自动从 session 索引发现活跃项目，无需指定路径
- 2 秒自动刷新

```bash
# 自定义端口
python harness.py web-hud --port 8080
```

### 终端 HUD（备选）

```bash
# 基础版
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" hud --watch

# Rich 增强版
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" hud --watch --rich
```

---

## Core Architecture

### Three-Layer Skill Resolution

```
优先级: L1 项目层 > L2 用户层 > L3 内置层

L1: .claude/skills/{name}/SKILL.md    → 项目专用 Skill（最高优先级）
L2: ~/.claude/skills/{name}/SKILL.md  → 用户级自定义
L3: generic-{name} (插件内置)          → 通用兜底
```

同一个 `/dev` 命令，不同项目自动使用不同深度的 Skill。新项目零配置，成熟项目深度定制。

### Multi-Agent Parallel (v3.2)

**Layer 1 — 阶段级并行**

implement 完成后，audit + docs + test 三个阶段同时启动（各自一个 background Agent），全部完成后进入 review。

```
implement DONE
    ↓
┌───────┬───────┬───────┐
│ audit │ docs  │ test  │  ← parallel_group: post-implement
└───────┴───────┴───────┘
    ↓ 全部 DONE
  review（内部三路并行: code + security + arch）
```

**Layer 2 — 任务级并行 (Orchestrator 模式)**

Plan 中 Phase > 3 个时自动触发：
1. Orchestrator 分析 Phase 依赖关系
2. 无依赖的 Phase 分为并行批次
3. 每个 Worker Agent 在独立 worktree 中执行
4. Worker 通过 `.claude/workers/worker-*.json` 汇报状态
5. 批次完成后合并 worktree，继续下一批次

### Deterministic Phases Registration

SKILL.md 指引是"概率性"的，但 phases 注册是**确定性**的：

1. **PostToolUse Hook (plan-watcher.py)** — 监听 Write/Edit → 检测 `.claude/plans/*.md` → 自动解析 Phase 标题注册到 state
2. **Stop Hook fallback** — phases 为空时从 plan 文件主动解析
3. **空 phases + 无 plan** — 不干预，放行

### Stop Hook 六道防线

| 防线 | 条件 | 行为 |
|------|------|------|
| Rate Limit | 检测到 "rate limit" 关键词 | 暂停 15 分钟 |
| 上下文溢出 | context > 80% | 放行（让 compact） |
| 阶段超时 | 单阶段 > 30 分钟 | 放行 |
| 总时长超限 | 总运行 > 2 小时 | 放行 |
| 死循环检测 | 5 分钟内 > 10 次续跑 | 放行 |
| 错误上限 | error_count >= max_retries | 放行 |

### Session ID Isolation

每次 `harness.py init` 生成唯一 session_id。Stop Hook 只处理匹配当前 session 的状态，防止多个 Claude Code 会话互相干扰。

中央索引 `~/.claude/dev-harness-sessions.json` 记录 session → 项目路径映射，供 Web HUD 自动发现项目。

### Hook 版本追踪

Claude Code 安装插件时将 `${CLAUDE_PLUGIN_ROOT}` 展开为含版本号的绝对路径。升级后旧路径失效。

**解决方案**: `~/.claude/hooks/dev-harness-stop.py` 是稳定入口（由 setup.sh 部署），通过 `installed_plugins.json` 动态查找实际路径。升级后自动追踪，无需手动维护。

---

## Pipeline Stages

| Stage | What it does | Parallel | Auto-fix |
|-------|-------------|----------|----------|
| research | 并行 subagent 代码库研究 | — | — |
| prd | 多轮需求对齐 | — | — |
| plan | 交互式 Phase 规划 | — | — |
| implement | 代码变更 + 门禁检查 (build/test) | Orchestrator 模式 | Build/test 失败 |
| audit | 代码审计 + 业务逻辑检查 | ⫘ post-implement | HIGH 级问题 |
| docs | API 文档更新 | ⫘ post-implement | — |
| test | 完整测试 + E2E 验证 | ⫘ post-implement | P0 bug |
| review | 三路联合审查 (code/security/arch) | 内部三路并行 | CRITICAL 问题 |
| remember | 保存进度到记忆系统 | — | — |

## 12 Specialized Agents

全部使用 **Opus** 模型：
architect, planner, code-reviewer, executor, debugger, qa-tester, security-reviewer, wiki-syncer, auto-loop, explore, gate-checker, skill-router

---

## Project Configuration

可选的 `.claude/dev-config.yml`：

```yaml
project: my-project
tech_stack: spring-boot

gates:
  build: "./gradlew build -x test"
  test: "./gradlew test"

skill_overrides:
  audit: my-custom-audit
  test: my-e2e-test
```

配置模板：`springboot` / `python` / `nextjs` / `monorepo` / `minimal`

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
# 运行全部测试（43 用例, 12 维度）
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" run-all

# 查看历史报告
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" report

# 对比两次评测
python "${CLAUDE_PLUGIN_ROOT}/eval/eval-runner.py" compare <before.json> <after.json>
```

12 个评测维度：skill_resolution / state_management / auto_continue / gate_detection / pipeline_routing / hook_defense / session_isolation / skill_override / parallel_group / worker_management / plan_watcher / phases_fallback

---

## Troubleshooting

### Stop Hook 不生效

1. 运行 `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"` 部署 wrapper
2. **重启 Claude Code 会话**（Hook 在会话启动时加载）
3. 验证 Python 可用：`python --version`
4. 验证 filelock 已安装：`python -c "import filelock"`

### 插件升级后 Stop Hook 路径失效

运行 `bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"`，自动部署 wrapper 到 `~/.claude/hooks/dev-harness-stop.py`。后续升级无需再处理。

### implement 阶段中途停下

可能是 phases 未注册。检查 `.claude/harness-state.json` 中 implement 的 phases 数组是否为空。

**解决**: v3.2 已通过 PostToolUse hook (plan-watcher) + Stop hook fallback 双重保障 phases 注册。确保 hooks.json 中的 PostToolUse 已注册。

### Web HUD 无数据

Web HUD 会自动从 session 索引和常见工作目录发现活跃项目。如果仍无数据：
1. 确认已通过 `/dev` 或 `harness.py init` 初始化过状态
2. 手动指定：`python harness.py web-hud --project /path/to/project`

### 插件更新后行为未变

Claude Code 缓存插件文件。更新后必须重启会话。如仍有问题：

```bash
rm -rf ~/.claude/plugins/cache/dev-harness-marketplace/dev-harness/
/plugin install dev-harness
/reload-plugins
```

---

## CLI Reference

```bash
# 状态管理
python harness.py init "task-name" --route C [--session-id ID]
python harness.py update <stage> <status> [--phase N] [--gate build=pass]
python harness.py check-continue

# Worker 管理 (Layer 2)
python harness.py worker-report <id> --phase <N> --status DONE [--branch <branch>]
python harness.py worker-status
python harness.py worker-cleanup

# 可视化
python harness.py web-hud [--port 1603] [--project /path]
python harness.py hud --watch [--rich] [--project /path]

# Skill 解析
python skill-resolver.py <stage> [--profile frontend] [--verbose]
python skill-resolver.py --all

# 技术栈检测
bash detect-stack.sh

# Worktree 隔离
bash worktree.sh create [branch-name]
bash worktree.sh merge
bash worktree.sh cleanup
bash worktree.sh status
```

## License

MIT
