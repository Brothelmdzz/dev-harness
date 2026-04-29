# Dev Harness v4 Roadmap — 从围堵到赋能

> 核心转向：**constraint-first → enablement-first**
> OpenAI 原话："Ask what capability is missing, not why the agent is failing."

---

## 设计论据

### 保留什么（4 项 "符合"）

| 原则 | 现有设计 | 判断 |
|------|---------|------|
| A4 Tool 设计 | harness.py CLI JSON 输出 | 继续保持 |
| A6 Progressive Disclosure | L1/L2/L3 三层 Skill | 这是核心差异化，不动 |
| C2 Hook/Prompt 分层 | 确定性 hook + 概率性 SKILL.md | 框架理论基石 |
| O3 机械执行（流程层） | stop-hook 六道防线 | 保留但瘦身 |

### 必须改什么（4 项 "违反"）

| 原则 | 问题 | 改法 |
|------|------|------|
| O2 围堵 vs 赋能 | 续跑反馈信息不足 | 保留续跑机制，改善每次 block 时注入的上下文质量 |
| O4 Agent eyes | HUD 给人看，agent 自己看不到全局 | 注入 pipeline 上下文到 agent prompt |
| O5 Map not manual | SKILL.md 是步骤指令 | 改为 architectural constraint + brief overview |
| C1 单线程 | Orchestrator 多进程绕开设计约束 | 用 Claude Code 原生 subagent 替代自建调度 |

### 可以渐进改的（5 项 "部分"）

| 原则 | 当前 | 目标 |
|------|------|------|
| A1 简单优先 | 9 阶段 + 6 防线 | 核心 3 阶段 + 可选扩展 |
| A2 Workflow/Agent | 两个控制环路 | 单环路：Claude Code loop + hook 增强 |
| A3 Ground truth | 流程级 | 任务级（编译/测试结果注入 state） |
| A5 Eval | 测 harness 基础设施 | 加 end-to-end 项目交付质量评测 |
| O1 Agent 可见性 | SKILL.md 黑盒指令 | agent 可读的执行上下文 |

---

## Phase 1: Agent Eyes（v4.0）

**目标**：让 agent 在每个决策点都能获得 ground truth。

### 1.1 Pipeline Context Injection

**问题**：Claude 不知道自己在 pipeline 的哪个位置、前序阶段产出了什么、距离完成还有多远。它只在 stop-hook block 时才收到一句 reason。

**方案**：PostToolUse hook 检测到 Claude 进入新阶段时，自动注入 pipeline 上下文摘要到 Claude 的 system prompt（通过 hook output）。

```
当前状态：
- Pipeline: plan[DONE] → implement[IN_PROGRESS Phase 2/4] → audit[PENDING]
- Phase 1 产出: src/auth/login.ts, src/auth/oauth.ts (2 files, 156 lines)
- 门禁: build=PASS, test=FAIL (3 failures in auth.test.ts)
- 剩余 Phase: Phase 2(核心逻辑), Phase 3(集成测试), Phase 4(文档)
```

**实现**：
- `hooks/context-injector.py` — 新 PostToolUse hook
- 触发条件：stage 切换 或 phase 切换 时
- 数据源：harness-state.json + gate-checker 结果 + git diff stats
- 输出方式：hook stdout（Claude Code 会注入到上下文）

### 1.2 Gate Result Feedback Loop

**问题**：gate-checker 跑完 build/test，结果写到 state 里，但 Claude 不一定会去读。

**方案**：gate-checker 的结果通过 PostToolUse hook 的 stdout 直接反馈给 Claude，不需要它主动查询。

```python
# gate-checker 跑完后，输出结构化反馈
{
  "gate": "test",
  "status": "FAIL",
  "summary": "3/47 tests failed",
  "failures": [
    "auth.test.ts:42 - expected 200, got 401",
    "auth.test.ts:67 - timeout after 5000ms",
    "oauth.test.ts:15 - missing redirect_uri"
  ],
  "suggestion": "检查 OAuth callback URL 配置"
}
```

**关键**：这不是"告诉 Claude 该做什么"，而是"给 Claude 看到测试结果，让它自己决定怎么修"。这就是 enablement vs constraint 的区别。

### 1.3 Diff Awareness

**问题**：每个 Phase 结束后，Claude 不知道自己改了什么文件、改了多少行。

**方案**：Phase 完成时，PostToolUse hook 自动运行 `git diff --stat` 并注入。

```
Phase 1 变更摘要:
  src/auth/login.ts    | 42 ++++++++++++
  src/auth/oauth.ts    | 87 +++++++++++++++++++++
  src/config/auth.yml  |  8 +++
  3 files changed, 137 insertions(+)
```

---

## Phase 2: Map not Manual（v4.1）

**目标**：SKILL.md 从步骤指令改为架构约束 + 简要指引。

### 2.1 SKILL.md 瘦身

**当前**（manual 风格）：
```markdown
## 执行步骤
1. 运行 `skill-resolver.py` 确认用哪个 Skill
2. 读取 `.claude/plans/` 下最新的 plan 文件
3. 找到当前待执行的 Phase（status=PENDING 的第一个）
4. 执行 Phase 内容，完成后运行门禁命令
5. 更新 harness-state.json: `harness.py update implement IN_PROGRESS --phase N`
6. 如果门禁失败，修复后重新运行
7. 所有 Phase 完成后: `harness.py update implement DONE`
```

**目标**（map 风格）：
```markdown
## 约束
- 每次只执行一个 Phase，完成后用 `harness.py update` 上报
- 门禁命令在 `dev-config.yml` 的 `gates` 段定义，必须全部 PASS 才能推进
- 不修改 plan 文件，plan 是 read-only 合约

## 边界
- 不跨 Phase 修改文件（Phase 2 不应改 Phase 1 的产出）
- 不引入 plan 未列出的新依赖
- 不跳过门禁
```

**关键洞察**：OpenAI 说 *"Architectural invariants are often expressed as 'something does not exist here'"*。约束比指令更有效，因为 Claude 4.x 已经知道怎么写代码，它需要知道的是**什么不能做**。

### 2.2 CLAUDE.md 精简

当前 CLAUDE.md 210 行，包含了大量架构细节。按 OpenAI "A map, not a manual" 原则：

- 保留：目录结构、核心概念（pipeline/skill/hook）、常用命令
- 删除：所有实现细节（"v3.4 新增"列表、具体函数名、代码行数）
- 那些细节属于代码注释和 git log，不属于 map

目标：100 行以内。

---

## Phase 3: 简化控制环路（v4.2）

**目标**：消除 dev-harness 和 Claude Code 的控制环路冲突。

### 3.1 Stop Hook — 保留 6 道防线，改善反馈质量

**核心认知修正**：Claude Code 被设计为交互式工具，每完成一个逻辑单元就会试图停下。stop-hook 的 block 机制是 pipeline 模式存在的前提 —— 没有它就没有自治流水线。6 道防线不是"围堵 agent"，而是**对续跑机制自身的 safeguard**：强制续跑可能失控，防线确保失控时能安全停下。

**保留全部 6 道**，但改善每道防线触发时给 agent 的反馈质量：

| 防线 | 当前行为 | 改进 |
|------|---------|------|
| Context overflow | 放行 compact | 不变 |
| Rate limit | 暂停 N 分钟 | 不变 |
| 单阶段超时 | 直接放行退出 | 放行前注入 advisory："你在此阶段已 30 分钟，建议 compact 或拆分" |
| 总运行时长 | 直接放行退出 | 放行前注入 advisory + 自动触发 remember |
| 滑动窗口 | 直接放行退出 | 放行前注入上下文摘要，帮助 agent 下次续跑时定位问题 |
| error_count | 直接放行退出 | 放行前注入失败历史摘要，说明哪些方法已试过 |

**原则**：防线的"停"不变，但"停之前说什么"要从空白变为有用信息。这是 enablement —— 不是阻止 agent 停下，而是让 agent 下次被续跑时有更好的上下文。

### 3.2 并行执行：三层策略替代自建 Orchestrator

**当前**：`harness.py detect-mode` → Phase > 3 → 启动多个独立 Claude Code 进程 → Worker 在 worktree 里跑 → 通过 worker-*.json 汇报。

**问题**：
- 违反 Claude Code 单线程原则
- Worker 之间无法共享上下文
- 合并 worktree 时冲突率高
- 调试困难（多进程 + 多 worktree）
- 重新发明了 Claude Code 已有的原生能力

**三层策略（按复杂度递增）**：

**Layer 1 — Subagent（Phase 内子任务）**：
- 单个 Phase 内的研究/验证用 `Agent tool` + `run_in_background`
- 结果摘要回传父级，不污染主上下文
- 替代：无（v3.4 已在 review 三路并行中使用）

**Layer 2 — Agent Teams（跨 Phase 并行）**：
- Phase > 3 时，用 Agent Teams 替代自建 Orchestrator
- 共享 task list = 天然的 Phase 状态管理（替代 worker-*.json）
- Inter-agent messaging = Worker 间可以协调（v3.4 做不到）
- `TaskCompleted` hook = 天然的门禁检查点
- `TeammateIdle` hook = 天然的续跑机制
- 注意：Agent Teams 仍是实验性功能，需 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`

**Layer 3 — Claude Agent SDK（终极方案）**：
- 如果需要完全控制 agent loop（像 OpenAI Codex 一样），用 Agent SDK 重写外层编排
- SDK 提供 `max_turns`、`max_budget_usd`、session resume/fork
- Pipeline 推进逻辑从 stop-hook 迁移到你自己的 Python async loop
- stop-hook 的 6 道防线变成你代码里的 if/else
- 保留 SKILL.md + CLAUDE.md + hooks 作为 agent 环境（SDK 支持 `setting_sources=["project"]`）

**迁移路径**：
- v4.0-4.2：保持 CLI plugin 架构，用 Agent Teams 替代 Orchestrator
- v4.3+：评估 Agent SDK 方案，如果 Teams 的实验性限制太多则迁移
- 终态：外层用 SDK 控制 loop，内层用 Claude Code 的 tools 和 skills

**削减代码**（Agent Teams 方案）：
- 删除：`cmd_worker_report`、`cmd_worker_status`、`cmd_worker_cleanup`、`WORKERS_DIR`、`_inject_workers_into_state`、`worktree.sh`
- 约减少 300 行 + 一个 shell 脚本

### 3.3 Pipeline 阶段精简

当前 9 阶段对大多数任务是过度工程。

**核心阶段**（不可跳过）：
- `plan` → `implement` → `verify`

**可选阶段**（按需启用）：
- `research`（route B/A 启用）
- `prd`（route B 启用）
- `review`（PR 场景启用）

**合并**：
- `audit` + `test` + `docs` → 合并为 `verify`（一个阶段内并行跑三件事）
- `remember` → 不再是 pipeline 阶段，改为 session 结束时的 PostStop hook

**结果**：默认 3 阶段（plan → implement → verify），最多 6 阶段。

---

## Phase 4: 真实 Eval（v4.3）

**目标**：从"测 harness 基础设施"进化到"测 agent 交付质量"。

### 4.1 End-to-End Project Eval

创建 `eval/projects/` 目录，每个子目录是一个最小但真实的项目：

```
eval/projects/
├── todo-api/          # Flask REST API，要求加 OAuth
│   ├── setup.py
│   ├── src/
│   ├── tests/
│   └── TASK.md        # "给这个 TODO API 加 Google OAuth 登录"
├── react-dashboard/   # React 项目，要求加图表组件
│   └── ...
└── cli-tool/          # Python CLI，要求加新子命令
    └── ...
```

**评分维度**：
- 代码能编译吗？（`build` gate pass rate）
- 测试能通过吗？（`test` gate pass rate）
- 变更是否在 plan 范围内？（`git diff` vs plan 文件的文件列表对比）
- 有没有引入安全问题？（Semgrep/Bandit 扫描）

### 4.2 Anthropic Eval 方法论对齐

按 [Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) 的建议：

- **pass@k** 和 **pass^k** 双指标（单次成功率 + 一致性）
- **Outcome-based grading**：测产出，不测路径
- **Balanced problem sets**：既测应该成功的场景，也测应该失败的场景（比如"给一个不存在的 API 加功能"应该在 research 阶段就报告不可行）
- **Partial credit**：plan 写对了但 implement 失败 = 比什么都没做好

### 4.3 Regression Suite

把用户报的 bug 转成 eval case：
- activity-watcher truncate bug → 已有 v34_safety 覆盖
- hook 超时静默 → 已有 breadcrumb 测试覆盖
- 未来每个 fix 都必须附带一个 eval case

---

## Phase 5: Mechanical Architecture Enforcement（v4.4）

**目标**：把 OpenAI O3 原则落地 —— 不只约束流程，也约束代码架构。

### 5.1 PostToolUse Linter Hook

新增 `hooks/arch-linter.py`：
- 触发：Write/Edit 工具调用后
- 检查：文件是否在 plan 声明的范围内、import 是否违反依赖方向
- 输出：violation 信息注入 Claude 上下文（advisory，不 block）

```python
# 示例检查：implement 阶段不应修改 test 文件
if current_stage == "implement" and "test" in file_path:
    print(f"[arch-lint] Warning: implement 阶段修改了测试文件 {file_path}，"
          f"测试应在 verify 阶段编写。")
```

### 5.2 dev-config.yml 架构约束声明

```yaml
architecture:
  layers:
    - name: domain
      paths: ["src/domain/**"]
      cannot_import: ["src/infra/**", "src/api/**"]
    - name: api
      paths: ["src/api/**"]
      can_import: ["src/domain/**"]
    - name: infra
      paths: ["src/infra/**"]
      can_import: ["src/domain/**"]
```

Linter hook 读取这个声明，在每次文件写入后检查 import 方向。

---

## 时间线

| Phase | 版本 | 主题 | 核心交付 | 预估工作量 |
|-------|------|------|---------|-----------|
| **1** | v4.0 | Agent Eyes | context-injector hook + gate feedback + diff awareness | 2-3 天 |
| **2** | v4.1 | Map not Manual | SKILL.md 重写 + CLAUDE.md 精简 | 1-2 天 |
| **3** | v4.2 | 简化控制环路 | stop-hook 瘦身 + 去 Orchestrator + 阶段合并 | 3-5 天 |
| **4** | v4.3 | 真实 Eval | e2e project eval + pass@k/pass^k + regression suite | 2-3 天 |
| **5** | v4.4 | 架构约束 | arch-linter hook + dev-config 声明式约束 | 2-3 天 |

**总计**：~10-16 天，建议按 Phase 顺序逐步发布。

---

## 不做什么

1. **不接 Chrome DevTools** — OpenAI 的 agent 是在容器里跑的，可以控制浏览器。Claude Code 是终端工具，给它接 DevTools 不现实。用 gate-checker 的 build/test 结果作为 ground truth 足够。

2. **不做 meta-harness**（生成 harness 的 harness）— revfactory/harness 的方向有趣但太早，当前模型对 harness 本身的理解还不够深。

3. **不加 vector DB 记忆** — mann1x/claude-hooks 用 Qdrant 做记忆。过重，且 Claude Code 自带 memory 系统 + CLAUDE.md 已经足够。

4. **不追求跨平台** — 深耕 Claude Code + Cursor，不为 Codex/Gemini CLI 做适配。三层 Skill 本身是跨平台的（Agent Skills 标准），但 harness 基础设施不是。

---

## 成功标准

v4 完成时，重新用 12 条原则评分：

| 指标 | v3.4 | v4 目标 |
|------|------|--------|
| 符合 | 4/13 | 9/13 |
| 部分 | 5/13 | 4/13 |
| 违反 | 4/13 | 0/13 |

核心验证问题：**一个新用户能否在 5 分钟内理解 dev-harness 在做什么、为什么这么做？**

如果答案是 yes，说明 "map not manual" 落地了。
如果答案是 no，说明复杂度还没降够。
