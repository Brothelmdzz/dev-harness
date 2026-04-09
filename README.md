# Dev Harness

> Harness Engineering pipeline for Claude Code & Cursor.
> Three-layer skill resolution · Multi-agent parallel · AutoLoop · Web HUD · 12 agents.

Dev Harness 把 AI 编码助手变成**自驱动开发流水线**。输入 `/dev`，自动走完 research → plan → implement → [audit + docs + test 并行] → review → remember。

---

## Installation

### Claude Code

```bash
# 1. 添加 Marketplace
/plugin marketplace add brothelmdzz/dev-harness

# 2. 安装插件
/plugin install dev-harness
/reload-plugins

# 3. 初始化环境（创建 venv + 安装依赖）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

### Cursor 2.5+

```bash
# 1. 安装插件
/add-plugin brothelmdzz/dev-harness

# 2. 初始化环境
bash "${CURSOR_PLUGIN_ROOT}/scripts/setup.sh"
```

### 手动安装（Codex CLI / Gemini CLI / 其他 Agent Skills 兼容工具）

```bash
# 1. Clone 到本地
git clone https://github.com/brothelmdzz/dev-harness.git ~/.claude/plugins/dev-harness

# 2. 初始化环境
bash ~/.claude/plugins/dev-harness/scripts/setup.sh
```

> **环境隔离**: setup.sh 在插件目录内创建 `.venv`，所有依赖安装到隔离环境。不修改全局 Python，不修改 settings.json，不往 `~/.claude/` 写文件。

### 安装后验证

首次启动新会话时，SessionStart Hook 会自动检测环境。如果 venv 未初始化，会提示运行 setup.sh。

```bash
# 可选：运行完整评测（43 用例，12 维度）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" --with-eval
```

---

## Quick Start

```bash
# 在任何项目目录中
/dev
```

Claude 会自动：
1. 检测技术栈（Gradle / npm / Python / Rust / Go...）
2. 解析最佳 Skill（项目级 > 用户级 > 内置）
3. 按 Pipeline 自动推进全流程
4. 中途不停（Stop Hook + 六道防线）

---

## Commands

Dev Harness 提供 **3 种运行模式**和 **6 个入口命令**，按任务规模选择：

| 命令 | 模式 | 场景 | 执行内容 |
|------|------|------|---------|
| **`/dev`** | pipeline | **完整流程** — 新功能/中型改动 | research → plan → implement → audit + docs + test → review → remember |
| **`/fix`** | single | **快速修复** — Bug 修复/小改动 | implement + test（跳过所有其他阶段） |
| **`/test`** | single | **只跑测试** — 验证现有代码 | 自动检测测试框架并运行 |
| **`/audit`** | single | **只做审计** — 代码质量检查 | 对比 plan 与实现，输出审计报告 |
| **`/review`** | single | **只做审查** — PR 代码审查 | 三路并行：code + security + architecture |
| **`/ask`** | conversation | **对话问答** — 不改代码 | 纯 Q&A，stop-hook 不介入，不创建 pipeline |

### 模式对比

| 模式 | state 行为 | stop-hook | 典型耗时 |
|------|-----------|-----------|---------|
| **pipeline** | 完整 pipeline 状态机 | 六道防线 + 阶段自动推进 | 10 分钟 ~ 2 小时 |
| **single** | 只记录指定阶段 | 只检查指定阶段完成 | 1 ~ 15 分钟 |
| **conversation** | 创建但不介入 | 直接放行 | 实时 |

### 使用示例

```bash
# 大型重构 - 走完整流程
/dev
# → 实现"用户中心支持 OAuth 登录"

# 小 bug 修复 - 跳过 plan/audit/review
/fix
# → "修复 login 页面按钮点击无响应"

# CI 挂了想先跑一遍测试
/test

# PR review
/review
# → 三路并行审查 + 汇总报告到 .claude/reports/final-review.md

# 只是想聊聊架构
/ask
# → "解释一下这个项目的三层 Skill 解析机制"
```

---

## What's Inside

### Skills (18)

| Skill | 描述 |
|-------|------|
| **`/dev`** | 入口编排器，管理全流程 |
| `generic-research` | 并行 subagent 代码库研究 |
| `generic-implement` | 按 plan 逐 Phase 实现 + 门禁 |
| `generic-audit` | 代码审计，对比 plan 与实现 |
| `generic-review` | 三路并行审查（code + security + arch） |
| `generic-test` | 自动检测测试框架并运行 |
| `generic-docs` | API 文档自动更新 |
| + 11 more | frontend / tdd / prd / wiki / remember... |

### Agents (12)

全部 **Opus** 模型：architect, planner, code-reviewer, security-reviewer, executor, debugger, qa-tester, auto-loop, wiki-syncer, explore, gate-checker, skill-router

### Hooks (3)

| Hook | 事件 | 作用 |
|------|------|------|
| `session-init.sh` | SessionStart | 检测 venv，未初始化时引导用户 |
| `stop-hook.py` | Stop | 六道防线阻止 Pipeline 中途停下 |
| `plan-watcher.py` | PostToolUse(Write/Edit) | Plan 文件写入时自动注册 phases |

### Scripts (8)

| 脚本 | 作用 |
|------|------|
| `dh-python.sh` | 统一 Python 入口（优先 venv → fallback 系统） |
| `harness.py` | 状态管理 + Web HUD + Worker 管理 |
| `skill-resolver.py` | 三层 Skill 解析 |
| `detect-stack.sh` | 技术栈自动检测 |
| `worktree.sh` | Git Worktree 隔离 |
| `setup.sh` | 安装验证 + venv 初始化 |
| `scaffold.sh` | Skill 脚手架生成 |
| `fix-hook-path.sh` | 修复升级后 hook 路径失效 |

---

## Pipeline

```
research → prd → plan → implement → [ audit + docs + test ] → review → remember
                           │              并行组 ⫘                三路并行
                           │
                      Phase > 3 ?
                      ├─ yes → Orchestrator 模式（多 Worker 并行 worktree）
                      └─ no  → 串行模式
```

### 5 条路线

| 路线 | 阶段 | 场景 |
|------|------|------|
| **B** | 全流程 | 大型新功能 |
| **A** | 跳 research | 中型功能 |
| **C** | 跳 research + prd | **最常用** |
| **C-lite** | implement + test + remember | 小修复 |
| **D** | 同 C-lite | 同上 |

---

## Three-Layer Skill Resolution

```
L1: .claude/skills/{name}/SKILL.md    → 项目专用（最高优先级）
L2: ~/.claude/skills/{name}/SKILL.md  → 用户级自定义
L3: generic-{name} (插件内置)          → 通用兜底
```

同一个 `/dev`，不同项目自动使用不同 Skill。

---

## Multi-Agent Parallel

**Layer 1 — 阶段级并行**: implement 完成后，audit + docs + test 三路 background Agent 同时跑。

**Layer 2 — Orchestrator 模式**: Plan 中 Phase > 3 时自动触发。`harness.py analyze-deps` 分析文件依赖，将无依赖的 Phase 分批并行，每个 Worker 在独立 worktree 中执行。

**review 三路并行**: code-reviewer + security-reviewer + architect 在 skill 内部并行。

---

## Web HUD

```bash
# 另一个终端启动（自动发现活跃项目）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" web-hud

# 浏览器打开 http://localhost:1603
```

**v3.3 特性**:
- **SSE 实时推送** — 0.5 秒检测 state 变化，连接失败自动降级为 2 秒轮询
- **Worker 可视化** — Orchestrator 模式下并行批次进度 + Worker 分支名 + 状态
- **评测趋势图** — Canvas 折线图显示 score / pass rate 历史走势
- **移动端适配** — 768px 断点，单列布局 + 下拉选择
- **完成项目过滤** — 默认隐藏已结束任务，勾选 "show completed" 查看全部
- **安全默认** — 绑定 `127.0.0.1`，需外部访问用 `--bind 0.0.0.0`

---

## Stop Hook 六道防线

| # | 防线 | 行为 |
|---|------|------|
| 1 | 上下文 > 80% | 放行让 compact |
| 2 | Rate Limit | 暂停 15 分钟 |
| 3 | 单阶段 > 30 分钟 | 放行 |
| 4 | 总运行 > 2 小时 | 放行 |
| 5 | 5 分钟内 > 10 次续跑 | 放行（死循环） |
| 6 | error_count >= 3 | 放行 |

---

## Deterministic Phases Registration

SKILL.md 是"建议"，Hook 是"约束"：

1. **plan-watcher.py** (PostToolUse): Plan 文件写入 → 自动解析 Phase 标题注册到 state
2. **stop-hook.py fallback**: phases 为空时从 plan 文件主动解析
3. **产出验证**: audit/review DONE 但无报告文件 → 打回 IN_PROGRESS

---

## Project Configuration

可选 `.claude/dev-config.yml`：

```yaml
project: my-project
gates:
  build: "./gradlew build -x test"
  test: "./gradlew test"
skill_overrides:
  audit: my-custom-audit
```

模板：`bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" --config springboot`

---

## Creating Custom Skills

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh" my-audit
# → .claude/skills/my-audit/SKILL.md（L1 最高优先级）
```

---

## CLI Reference

```bash
# 状态管理
harness.py init "task" --route C [--mode pipeline|single|conversation] [--skills implement,test]
harness.py update <stage> <status> [--phase N] [--gate build=pass] [--gate test=pass]
harness.py detect-mode                    # 自动检测 serial/orchestrator
harness.py analyze-deps                   # Phase 依赖分析 + 并行批次

# Worker 管理
harness.py worker-report <id> --phase <N> --status DONE [--branch <b>]
harness.py worker-status
harness.py worker-cleanup

# 可视化
harness.py web-hud [--port 1603] [--bind 127.0.0.1] [--project /path]
harness.py hud --watch [--rich] [--project /path]

# Skill 解析
skill-resolver.py <stage> [--profile frontend] [--verbose]
skill-resolver.py --all

# v3.3 新增: 通知 + 团队看板 + Skill 建议
notify.py --title "X" --message "Y" --level success [--lark]
team-report.py [--json] [-o report.md]
skill-suggest.py [--threshold 80] [--consecutive 3]

# 版本同步
bash sync-plugin-meta.sh [3.4.0]
```

---

## Troubleshooting

### 插件升级后 Hook 路径失效

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/fix-hook-path.sh"
```

### implement 阶段中途停下

检查 `.claude/harness-state.json` 的 implement phases 是否为空。v3.2+ 已通过 plan-watcher + fallback 双重保障。

### Web HUD 无数据

自动从 session 索引发现项目。手动指定：`harness.py web-hud --project /path`

---

## Evaluation

```bash
# 43 用例，12 维度
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh" --with-eval
```

维度：skill_resolution / state_management / auto_continue / gate_detection / pipeline_routing / hook_defense / session_isolation / skill_override / parallel_group / worker_management / plan_watcher / phases_fallback

---

## Compatibility

基于 [Agent Skills](https://agentskills.io) 开放标准。SKILL.md 格式通用于：

Claude Code · Cursor · Gemini CLI · GitHub Copilot · VS Code · OpenAI Codex · OpenHands · Roo Code · 30+ 平台

---

## License

MIT
