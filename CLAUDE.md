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

# 评测（64 用例，16 维度）
python eval/eval-runner.py run-all

# 版本同步
bash scripts/sync-plugin-meta.sh
```

## 架构

### 核心流

```
/dev → skills/dev/SKILL.md (编排器)
  → detect-stack.sh + skill-resolver.py + harness.py init
  → Pipeline 循环: 按 pipeline.yml 定义的阶段依次执行
    每步完成 → harness.py update
    Claude 想停 → stop-hook.py 检查防线，未完成则 block 续跑
```

`${CLAUDE_PLUGIN_ROOT}` 定位所有脚本。Cursor 用 `${CURSOR_PLUGIN_ROOT}`，`session-init.py` 自动映射。

### 三层 Skill 解析

优先级: L1 项目层 (.claude/skills/) > L2 用户层 (~/.claude/skills/) > L3 内置层 (skills/generic-*)

### 状态文件

`.claude/harness-state.json` — pipeline 唯一状态源。关键字段: session_id, mode, current_stage, pipeline[].status, metrics, activity。

### Agents (12)

architect, code-reviewer, planner, executor, debugger, qa-tester, security-reviewer, wiki-syncer, auto-loop, explore, gate-checker, skill-router — 全部 opus 模型。

### 目录结构

| 目录 | 职责 |
|------|------|
| `skills/dev/` | `/dev` 入口编排器 |
| `skills/fix/` `test-skill/` `audit-skill/` `review-skill/` `ask/` | 轻量入口 Skill |
| `skills/generic-*/` | L3 内置 Skill |
| `scripts/` | Python/Shell 工具脚本 |
| `scripts/lib/` | 共享库: state / compat / pipeline / plan / project / config / utils / hook_trace |
| `hooks/` | stop-hook + plan-watcher + activity-watcher + session-init + hooks.json |
| `agents/` | 12 个 Agent 定义 |
| `defaults/` | pipeline.yml + skill-map.yml |
| `templates/` | 项目配置模板 |
| `eval/` | 评测框架 |

## 注意事项

- Skill 目录中只有 SKILL.md，执行逻辑由 Claude Code 解释 Markdown 指令完成
- 所有 Skill 中的脚本引用统一使用 `${CLAUDE_PLUGIN_ROOT}/scripts/xxx`
- Windows 环境下 `python3` 可能是应用商店存根，脚本应使用 `python`
- state 写入使用原子操作（.tmp + os.replace），所有路径统一走 `lib/state.py`
- `filelock` 缺失时并行模式会被 `require_filelock()` 阻断
- hook 超时通过面包屑机制追踪（lib/hook_trace.py）
- `dev-config.yml` 的 `limits` 段支持配置防线参数，极端值自动 clamp
- `pipeline.yml` 每个 stage 支持 `depends_on` 字段，基于 DAG 拓扑推进
