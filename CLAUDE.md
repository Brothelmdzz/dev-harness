# CLAUDE.md

## 项目概述

Dev Harness 是一个 Claude Code 插件，将 Claude Code 变成自驱动开发流水线。用户输入 `/dev`，自动走完 research → plan → implement → audit → test → review → remember 全流程。核心差异化：三层 Skill 解析 + YAML 可配置 Pipeline + Stop Hook 自动续跑。

## 常用命令

```bash
# 状态管理
python scripts/harness.py init "task-name" --route C --session-id abc123
python scripts/harness.py update <stage> <status> [--phase N] [--gate build=pass]
python scripts/harness.py hud --watch --rich

# Web HUD
python scripts/harness.py web-hud

# Skill 解析
python scripts/skill-resolver.py <stage_name>
python scripts/skill-resolver.py --all

# 技术栈检测
bash scripts/detect-stack.sh

# 评测
python eval/eval-runner.py run-all                       # 全套
ls eval/scenarios/                                       # v4 起步 5 条 scenarios

# v4 ABC 三件事配套工具
bash scripts/detect-codex.sh                             # 检测 codex cli 是否就绪（A 阶段）
python scripts/pitfall-analyze.py --threshold 3          # 提炼候选规则（B 阶段）

# v4.5 setup 体检
python scripts/setup_report.py --json [--fix]                # 或 /dev-harness:setup

# 版本同步
bash scripts/sync-plugin-meta.sh
```

## 架构

### 核心流

```
/dev → skills/dev/SKILL.md (name: dev-pipeline，编排器)
  → detect-stack.sh + skill-resolver.py + harness.py init
  → Pipeline 循环: 按 pipeline.yml 定义的阶段依次执行
    每步完成 → harness.py update（自带 hud 快照输出，不必再单独调用 hud；独立的
    hud-context hook 已移除，快照下沉进 update 自身）
    Claude 想停 → Stop 事件双 hook 并行、OR-block ⇒ AND-to-stop：
      command hook（stop-hook.py，确定性地板：真实 gate/DAG/错误计数）
      prompt hook（haiku 完成裁判，只读 transcript 里的 hud 表格判断语义是否真完成）
      任一 block 即续跑，全部 allow 才真停
```

`${CLAUDE_PLUGIN_ROOT}` 定位所有脚本。Cursor 用 `${CURSOR_PLUGIN_ROOT}`，`session-init.py` 自动映射。

### 三层 Skill 解析

优先级: L1 项目层 (.claude/skills/) > L2 用户层 (~/.claude/skills/) > L3 内置层 (skills/generic-*)

### 状态文件

`.claude/harness-state.json` — pipeline 唯一状态源。关键字段: session_id, mode, current_stage, pipeline[].status, metrics, activity。

### Agents (12)

architect, code-reviewer, planner, executor, debugger, qa-tester, security-reviewer, wiki-syncer, auto-loop, explore, gate-checker, skill-router。

**模型策略（v4 改为异构）**：
- `code-reviewer` `security-reviewer`: **sonnet**（review 量大但单点不深）
- `architect` 及其他: **opus**（架构推理需要深度）
- 这是 generic-review 的 Layer 1 异构基础，详见 `docs/design-philosophy.md` 原则 7

### Code Review 双层架构（v4 ABC 阶段 A 引入）

```
Layer 1: Claude 内部三路并行（必跑）
  ├─ code-reviewer (sonnet)
  ├─ security-reviewer (sonnet)
  └─ architect (opus)

Layer 2: 跨厂商对抗审查（可选，detect-codex.sh 决定）
  └─ codex exec --output-last-message ...   ← 用户 codex 配置的非 Claude 模型
```

启用条件：`dev-config.yml` 中 `review.cross_vendor.enabled` = `auto`（默认）+ codex cli 就绪。

### Pitfall Journal 闭环（v4 ABC 阶段 B 引入）

```
build/test 失败 → stop-hook capture_failure() → .claude/pitfall-journal.jsonl
                                                  ↓
                                        续跑前 build_pitfall_context()
                                                  ↓
                                        作为 ground truth 注入下一轮 prompt
                                                  ↓
                                        ≥3 条同类 → pitfall-analyze.py
                                                  ↓
                                        生成 .claude/rules/auto-*.md.candidate
                                                  ↓
                                        人工 review 后改名 .md 才生效
```

代码位置：`scripts/lib/pitfall.py`（核心库）+ `scripts/pitfall-analyze.py`（CLI）。

### 目录结构

| 目录 | 职责 |
|------|------|
| `commands/` | v4.5 新增：7 个用户专属入口命令（dev/fix/ask/run-tests/run-audit/run-review/setup），薄壳委托对应 skill，不占 skills 隐式匹配预算 |
| `skills/dev/` | `/dev` 入口编排器，frontmatter `name: dev-pipeline`（目录名未变，技能名已改避免与 `dev` 泛名碰撞）|
| `skills/fix/` `test-skill/` `audit-skill/` `review-skill/` `ask/` | 轻量入口 Skill；`test-skill`/`audit-skill`/`review-skill` 的 `name` 字段已改为 `run-tests`/`run-audit`/`run-review`（目录名未变）|
| `skills/generic-*/` | L3 内置 Skill |
| `.codex-plugin/` | v4.5 新增：Codex 插件清单（`interface` 块），故意不声明 `hooks` 字段以启用 hooks.json 的约定发现 |
| `scripts/` | Python/Shell 工具脚本（含 v4 `detect-codex.sh` `pitfall-analyze.py`，v4.5 新增 `setup_report.py`）|
| `scripts/lib/` | 共享库: state / compat / pipeline / plan / project / config / utils / hook_trace / **pitfall** (v4) |
| `hooks/` | stop-hook + plan-watcher + activity-watcher + session-init + hooks.json（v4.5 起移除独立 hud-context：hud 快照改由 harness.py update 自带输出）|
| `agents/` | 12 个 Agent 定义 |
| `defaults/` | pipeline.yml + skill-map.yml |
| `templates/` | 项目配置模板 + `project-skeleton/` 三层规范骨架（v4 C 阶段，20 个文件）+ **`goal-automation/`** v4.5 新增：`/goal` 咒语与 CC routine / Codex automation.toml 模板 |
| `eval/` | 评测框架 + `scenarios/` 任务级真实任务 + **`scenarios/skill-behavior/`** v4.5 新增：技能行为回归（RED-GREEN-REFACTOR）|
| `docs/` | 文档：`design-philosophy.md` (公开) + `external-references-2026-05.md` (公开) + 内部研究文档（私有）|
| `.design/` | 内部设计研究（`.gitignore` 排除）|

## 注意事项

- Skill 目录中只有 SKILL.md，执行逻辑由 Claude Code 解释 Markdown 指令完成
- 所有 Skill 中的脚本引用统一使用 `${CLAUDE_PLUGIN_ROOT}/scripts/xxx`
- Windows 环境下 `python3` 可能是应用商店存根，脚本应使用 `python`
- Windows cmd 默认 GBK 编码：Python 脚本输出中文需 `sys.stdout.reconfigure(encoding='utf-8')`（见 `scripts/pitfall-analyze.py` 顶部）
- state 写入使用原子操作（.tmp + os.replace），所有路径统一走 `lib/state.py`
- `filelock` 缺失时并行模式会被 `require_filelock()` 阻断
- hook 超时通过面包屑机制追踪（lib/hook_trace.py）
- `dev-config.yml` 的 `limits` 段支持配置防线参数，极端值自动 clamp
- `pipeline.yml` 每个 stage 支持 `depends_on` 字段，基于 DAG 拓扑推进
- **设计哲学是最高准则**：任何架构决策先对照 `docs/design-philosophy.md` 八大原则 + 九条架构红线
- **docs/ 公开范围**：`docs/` 整体被 `.gitignore` 排除，仅 `design-philosophy.md` `external-references-2026-05.md` `quickstart.md` `contributing.md` `known-issues.md` 白名单公开
- **`defaults/skill-map.yml` 与 `scripts/skill-resolver.py` 的 `SKILL_ALIASES` 是双源**（历史遗留，尚未合一）：改一处必须同步改另一处，否则 resolver 与文档声明的别名会漂移
- **SKILL description 与 `commands/*.md` 是跨平台触发面，优先英文书写**——这是对全局『文档文案中文』规则的项目级有意豁免：Codex 的隐式技能匹配依赖英文前置触发词，中文描述会降低跨平台命中率
- **`hooks/hooks.json` 的 `command` 字符串是 Codex 信任冻结契约**：Codex 按整个 hook 块计算信任哈希，`command` 一行不变则改 `stop-hook.py`/`hud-context.py` 等 `.py` 内容不会触发用户重批准；反之只要动了 `command` 行本身（哪怕只加个空格），Codex 侧就要求用户重新走一次 `/hooks` 批准
