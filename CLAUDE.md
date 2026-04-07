# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

Dev Harness 是一个 Claude Code 插件，将 Claude Code 变成自驱动开发流水线��用户输入 `/dev`，自动走完 research → plan → implement → audit → test → review → wiki → remember 全流��。核心差异化��三层 Skill 解析 + YAML 可配置 Pipeline + AutoLoop 自动续跑。

## 常用命令

```bash
# 评测（38 个测试用例，10 维度）
python eval/eval-runner.py run-all
python eval/eval-runner.py report
python eval/eval-runner.py compare <before.json> <after.json>

# 技术栈检测
bash scripts/detect-stack.sh

# Skill 三层解析
python scripts/skill-resolver.py <stage_name>           # 单阶段
python scripts/skill-resolver.py --all                   # 全部阶段
python scripts/skill-resolver.py audit --profile frontend # 带角色

# 状态管理
python scripts/harness.py init "task-name" --route C --session-id abc123
python scripts/harness.py update <stage> <status>
python scripts/harness.py hud --watch --rich
python scripts/harness.py check-continue

# Web HUD 可视化面板
python scripts/harness.py web-hud              # 默认 localhost:1603
python scripts/harness.py web-hud --port 8080  # 自定义端口

# Worktree 隔离
bash scripts/worktree.sh create [branch-name]
bash scripts/worktree.sh merge
bash scripts/worktree.sh cleanup

# Skill 脚手架
bash scripts/scaffold.sh <skill-name>                    # 创建 L1 Skill
bash scripts/scaffold.sh --config springboot             # 复制项目配置模板

# 安装验证
bash scripts/setup.sh
```

## 架构

### 路径机制

插件安装后，所有脚本通过 Claude Code 官方环境变量 `${CLAUDE_PLUGIN_ROOT}` 定位。该变量在 Skill/Agent/Hook 内容中自动替换，在子进程中作为环境变量导出。

**Hook 注册机制（两层）**：
1. 首次安装：Claude Code 发现 `hooks/hooks.json` → 展开 `${CLAUDE_PLUGIN_ROOT}` 写入 `settings.json`
2. 版本升级防护：`scripts/setup.sh` 部署 wrapper（`~/.claude/hooks/dev-harness-stop.py`）→ 通过 `installed_plugins.json` 动态查找实际路径，避免版本号硬编码失效

### 核心流

```
/dev 命令 → skills/dev/SKILL.md (编排器)
  ↓
  scripts/detect-stack.sh          # 检测 gradle/node/python/rust/go...
  scripts/skill-resolver.py        # 三层 Skill 解析: L1 项目 > L2 用户 > L3 内置
  scripts/harness.py init          # 初始化 harness-state.json（含 session_id）
  ↓
  Pipeline 循环: 按 defaults/pipeline.yml 定义的阶段依次执行
    每个阶段 → skill-resolver 找到对应 Skill → 调用执行
    每步完成 → harness.py update 更新状态
    Claude 想停 → hooks/stop-hook.py 检查状态，未完成则 block 续跑
    implement 阶段 → worktree.sh 隔离 + gate-checker 门禁
```

### 三层 Skill 解析

优先级: L1 项目层 (.claude/skills/) > L2 用户层 (~/.claude/skills/) > L3 内置层 (skills/generic-*)

`defaults/skill-map.yml` 定义每个阶段的别名候选列表，`scripts/skill-resolver.py` 按层级逐一尝试匹配。角色 profile (backend/frontend/product/qa) 可额外注入 profile 专用别名。

### Pipeline 路线

路线决定跳过哪���阶段（`scripts/harness.py` 中的 `ROUTE_STAGES`）���
- **B**: 全流程（含 research + prd）
- **A**: 跳 research
- **C**: 跳 research + prd（最常用）
- **C-lite**: 仅 implement + test + remember
- **D**: 同 C-lite

### Stop Hook 六道防线

`hooks/stop-hook.py` — 通过 `hooks/hooks.json` 自动注册，阻止 Pipeline 中途停下：
1. Rate Limit 检测 → 暂停并记录恢复时间
2. 上下文 >80% ��� 转入 remember 阶段
3. 单阶段���时 (30min)
4. 总运行时长上限 (2h)
5. 滑动��口频率限��� (5min 内 >10 次 → 判定死循环)
6. error_count >= max_retries → 停止

### Session ID 隔离

`harness-state.json` 中的 `session_id` 字段绑定创建它的会话。stop-hook.py 在收到带 session_id 的 hook 输入时，只处理匹配的 session，防止多 session 互相干扰。

**中央 Session 索引**：`~/.claude/dev-harness-sessions.json` 记录 session_id → 项目路径映射。`web-hud` / `hud` 从索引自动发现活跃项目，无需手动指定 `--project`。索引找不到时 fallback 扫描 `C:\work\*` 等常见目录。评测模式（`DH_EVAL=1`）下跳过注册，防止临时目录污染。

### 状态文件

`.claude/harness-state.json` 是整个流水线的唯一状态源。关键字段：`session_id`, `current_stage`, `pipeline[].status` (PENDING/IN_PROGRESS/DONE/SKIP/FAILED), `metrics`, `worktree`。

### 12 个 Agent

定义在 `agents/` 目录，全部使用 **opus** 模型：
architect, code-reviewer, planner, executor, debugger, qa-tester, security-reviewer, wiki-syncer, auto-loop, explore, gate-checker, skill-router

### 多 Agent 并行

**Layer 1 — 阶段级并行**: pipeline.yml 中 `parallel_group` 字段声明可并行的阶段组。implement 完成后，audit + docs + test 三路同时启动（各自一个 background Agent），全部完成后进入 review。

**Layer 2 — 任务级并行 (Orchestrator 模式)**: 当 Plan 中 Phase > 3 个时自动触发。Orchestrator 分析 Phase 依赖关系，将无依赖的 Phase 分为并行批次，每个 Phase 交给一个 Worker Agent 在独立 worktree 中执行。Worker 通过 `.claude/workers/worker-*.json` 汇报状态，Orchestrator 轮询合并，完成后自动清理 Worker 文件。

**并发安全**: harness-state.json 的读写通过 `filelock` 保护，防止多 Agent 竞态。

**review 三路并行**: 在 generic-review skill 内部完成（code-reviewer + security-reviewer + architect 三个 background Agent），不走 pipeline 层。

### 目录结构职责

| 目录 | 职责 |
|------|------|
| `skills/dev/` | `/dev` 入口编排器 SKILL.md |
| `skills/generic-*/` | L3 内置 Skill（audit/implement/research/review/test/docs/wiki 等） |
| `scripts/` | Python/Shell 工具脚本（状态管理、Skill 解析、技术栈检测、worktree、Web HUD） |
| `hooks/` | stop-hook.py（续跑）+ hooks.json（自动注册）+ stop-hook-wrapper.py（版本追踪） |
| `agents/` | 12 个 Agent 的 Markdown 定义文件 |
| `defaults/` | pipeline.yml（阶段定义）+ skill-map.yml（别名映射） |
| `templates/` | 项目配置模板（springboot/python/nextjs/monorepo/minimal） |
| `eval/` | 评测框架：eval-runner.py + scenarios/ + results/ |
| `.claude-plugin/` | plugin.json（插件元数据）+ marketplace.json |
| `docs/` | 改进方案、竞品研究、贡献指南等 |

## 注意事项

- `scripts/harness.py` 中的 `find_project_root()` 和 `hooks/stop-hook.py` 各自有独立的项目根发现逻辑（后者需处理 Hook cwd 可能不在项目目录的情况）
- Skill 目录中只有 SKILL.md 文件，Skill 的实际执行逻辑由 Claude Code 解释 Markdown 指令完成
- 所有 Skill 中的脚本引用统一使用 `${CLAUDE_PLUGIN_ROOT}/scripts/xxx`
- `scripts/find-dh-home.sh` 仅作为 fallback 发现机制保留
- Windows 环境下 `python3` 可能是应用商店存根，脚本应使用 `python` 而非 `python3`
