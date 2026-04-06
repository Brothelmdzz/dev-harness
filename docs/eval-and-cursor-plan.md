# Dev Harness 评测体系 + Cursor 适配 + Meta-Harness 外循环 方案

> 日期：2026-04-05
> 版本：v1.0
> 状态：方案设计

---

## 一、总览

三个并行工作流，共享数据基础：

```
                    ┌─────────────────────────────────────┐
                    │        Dev Harness Eval System        │
                    │                                       │
                    │   数据基础: 结构化执行轨迹 (traces/)   │
                    │                                       │
        ┌───────────┼───────────────┬───────────────────────┤
        │           │               │                       │
   L1 回归层    L2 A/B 对照     Cursor 分支        L3 Meta 外循环
   (eval扩展)   (SEAL双轨)     (跨IDE适配)         (自动优化)
        │           │               │                       │
   每次提交     每个版本         并行开发              v4.1+
   $0          $50-100         独立分支              $200/轮
```

---

## 二、L1 回归层：eval-runner.py 扩展

### 2.1 当前状态

- 21 个测试用例，5 个维度，加权评分 93.9%
- 维度：skill_resolution / state_management / auto_continue / gate_detection / pipeline_routing

### 2.2 新增维度和用例

| 维度 | 新增用例 | 测什么 |
|------|---------|--------|
| **hook_defense** | 6 个 | 六道防线各触发一次验证拦截/放行 |
| hook_defense_01 | rate_limit 关键词检测 | 输入含 "rate limit" 的 last_assistant_message，验证 state.paused=true |
| hook_defense_02 | context overflow 放行 | 输入 context_window.used/total > 80%，验证 output 含 continue |
| hook_defense_03 | 单阶段超时 | 设置 stage.started_at 为 31 分钟前，验证 exit 0 |
| hook_defense_04 | 总时长超时 | 设置 task.started_at 为 2.1 小时前，验证 exit 0 |
| hook_defense_05 | 滑动窗口死循环 | 写入 11 条 5 分钟内的 auto_continue 事件，验证 exit 0 |
| hook_defense_06 | error_count >= max_retries | phase.error_count=3, max_retries=3，验证 exit 0 |
| **session_isolation** | 2 个 | Session ID 隔离 |
| session_isolation_01 | 匹配 session 正常处理 | hook 输入 session_id=X，state session_id=X，验证正常续跑 |
| session_isolation_02 | 不匹配 session 跳过 | hook 输入 session_id=X，state session_id=Y，验证 exit 0 |
| **skill_override** | 3 个 | L1 > L2 > L3 覆盖 |
| skill_override_01 | L1 覆盖 L3 | 项目目录有 .claude/skills/audit/，验证解析到 L1 |
| skill_override_02 | L2 覆盖 L3 | 用户目录有 ~/.claude/skills/audit/，验证解析到 L2 |
| skill_override_03 | L3 兜底 | 无 L1/L2，验证解析到 generic-audit |
| **mode_routing** | 3 个 | 多模式分流（v3.2 实现后） |
| mode_routing_01 | mode=pipeline 创建完整 state | init --mode pipeline，验证 pipeline 数组非空 |
| mode_routing_02 | mode=single 只记录单 skill | init --mode single --skill test，验证 single_skill=test |
| mode_routing_03 | mode=conversation 不创建 state | init --mode conversation，验证不写文件 |

### 2.3 目标

从 21 个扩展到 **35+ 用例**，6+ 维度。加权通过率目标 ≥ 90%。

### 2.4 实施

```python
# eval/eval-runner.py 新增场景注册示例

def test_hook_defense_rate_limit():
    """防线 1: rate limit 检测"""
    state = create_test_state(current_stage="implement", status="IN_PROGRESS")
    hook_input = {
        "session_id": state["session_id"],
        "last_assistant_message": "I've hit your rate limit. The limit resets in 15 minutes.",
    }
    result = run_stop_hook(state, hook_input)
    # 验证: state 被标记为 paused
    reloaded = load_state()
    assert_eq(reloaded["paused"], True, "should be paused")
    assert_eq(reloaded["pause_reason"], "rate_limit", "reason should be rate_limit")

def test_session_isolation_mismatch():
    """Session ID 不匹配 → 跳过"""
    state = create_test_state(session_id="aaa")
    hook_input = {"session_id": "bbb"}
    exit_code = run_stop_hook(state, hook_input)
    assert_eq(exit_code, 0, "should exit 0 for mismatched session")
```

---

## 三、L2 A/B 对照层：SEAL 双轨评测

### 3.1 评测设计

**核心方法论**：SEAL 双轨制（同一任务集，对照 harness 配置）

```
四组对照（2×2 矩阵）:

          │  Cursor           │  Claude Code CLI
──────────┼────────────────────┼──────────────────
  裸模型   │  A: Cursor bare   │  B: CC bare
  +Harness │  C: Cursor+DH     │  D: CC+DH

每组跑同一批任务，记录:
  · 功能指标（build/test pass）
  · 效率指标（token 消耗、耗时）
  · 质量指标（LLM-as-Judge 评分）
  · 自主性指标（人工干预次数）
```

### 3.2 任务集

#### Task Set A: SWE-bench Lite 子集（20 题，有标准答案）

选取标准：
- 涵盖 Python/JavaScript 两种语言（各 10 题）
- 难度分布：easy 5 / medium 10 / hard 5
- 单实例预算 ≤ $3（Sonnet 计价）

执行方式：
```bash
# 使用 jimmc414/claudecode_n_codex_swebench 工具
# 对照组: bare Claude Code
python swe_bench.py run --limit 20 --agent bare

# 实验组: Claude Code + Dev Harness
python swe_bench.py run --limit 20 --agent dev-harness
```

需要编写 adapter 脚本将 Dev Harness Pipeline 包装为 swe_bench.py 兼容接口。

#### Task Set B: 真实任务（5 题，无标准答案）

由用户提供。每个任务需包含：
- 需求描述（自然语言）
- 起始 commit（git SHA）
- 用户最终实现（作为 reference，非 ground truth）
- 技术栈标注

评判方式：
```
功能指标: build pass? test pass? lint pass?
LLM Judge: Opus 对 {需求, 对照组代码, 实验组代码, 参考实现} 打分
  维度: 需求覆盖(1-10) / 代码质量(1-10) / 架构(1-10) / 测试(1-10)
  方法: pairwise comparison（哪个更好）+ 绝对评分
```

#### Task Set C: 消融分析（复用 Task Set A）

| 配置 | 关闭什么 | 测什么 |
|------|---------|--------|
| full | 无 | baseline |
| no-stophook | stop-hook.py 返回空 | 自动续跑的价值 |
| no-skill-resolve | 强制用 generic-* | 三层解析的价值 |
| no-gate | 跳过 build/test 门禁 | 门禁检查的价值 |
| no-audit | 跳过 audit 阶段 | 审计阶段的价值 |
| bare | 全部关闭 | 纯模型 baseline |

每个配置跑同样 20 题，产出 delta 表：
```
配置          pass@1    token_avg    time_avg
full          75%       85k          4m30s
no-stophook   60%       92k          6m10s     ← 续跑贡献 15pt
no-skill      70%       88k          5m00s     ← Skill 贡献 5pt
no-gate       65%       78k          3m50s     ← 门禁贡献 10pt
no-audit      72%       82k          4m20s     ← 审计贡献 3pt
bare          55%       95k          7m00s     ← 框架总贡献 20pt
```

### 3.3 执行轨迹记录格式

**关键设计（来自 Meta-Harness 论文）：未压缩执行轨迹是自动优化的数据基础。**

每次评测运行产出一个 trace 文件：

```
eval/traces/{task_id}_{config}_{timestamp}.json
```

```json
{
  "meta": {
    "task_id": "swe-bench-lite-django-001",
    "config": "full",
    "ide": "cursor",
    "model": "claude-sonnet-4-6",
    "timestamp": "2026-04-05T10:00:00Z"
  },
  "result": {
    "pass": true,
    "build_pass": true,
    "test_pass": true,
    "tokens_total": 85000,
    "time_total_sec": 270,
    "human_interventions": 0,
    "stop_hook_triggers": 2,
    "auto_continues": 2
  },
  "stages": [
    {
      "name": "plan",
      "skill_resolved": "L2:create_plan",
      "duration_sec": 45,
      "tokens": 12000,
      "output_summary": "Identified 2 files to modify..."
    },
    {
      "name": "implement",
      "skill_resolved": "L2:implement_plan",
      "duration_sec": 180,
      "tokens": 55000,
      "phases": [
        {
          "name": "Phase 1: Fix import",
          "status": "DONE",
          "gates": {"build": true, "test": false},
          "retries": 1,
          "error": "test_foo failed: expected 42 got 41",
          "fix_applied": "Off-by-one in line 127"
        },
        {
          "name": "Phase 2: Update test",
          "status": "DONE",
          "gates": {"build": true, "test": true},
          "retries": 0
        }
      ]
    },
    {
      "name": "test",
      "skill_resolved": "L3:generic-test",
      "duration_sec": 30,
      "tokens": 8000,
      "test_results": {"passed": 142, "failed": 0, "skipped": 3}
    }
  ],
  "judge": {
    "model": "claude-opus-4-6",
    "scores": {
      "completeness": 9,
      "code_quality": 7,
      "architecture": 8,
      "test_coverage": 6
    },
    "pairwise_vs_bare": "harness",
    "reasoning": "Harness version correctly identified the off-by-one error..."
  }
}
```

### 3.4 报告输出

每轮评测生成 markdown 报告：

```
eval/reports/eval-{date}-{config}.md

# Dev Harness Evaluation Report

## Summary
- Date: 2026-04-05
- Task Set: SWE-bench Lite x20 + Real Tasks x5
- Model: claude-sonnet-4-6

## Results: Harness vs Bare

| Metric         | Bare  | +Harness | Delta   |
|---------------|-------|----------|---------|
| Pass@1 (SWE)  | 55%   | 75%      | **+20** |
| Avg Tokens     | 95k   | 85k      | **-11%** |
| Avg Time       | 7m    | 4m30s    | **-36%** |
| Human Intervene| 4.2   | 0.8      | **-81%** |

## Ablation Analysis
[消融表格]

## LLM Judge Scores (Real Tasks)
[Judge 评分表格]

## Trace Archive
[链接到 eval/traces/ 目录]
```

---

## 四、Cursor 分支：跨 IDE 适配

### 4.1 分支策略

```bash
git checkout -b cursor-adaptation
```

独立开发，不影响 master 上的 Claude Code 主线。成熟后 cherry-pick 回 master。

### 4.2 适配架构

```
dev-harness/
├── .claude-plugin/           # Claude Code 插件清单
│   ├── plugin.json
│   └── marketplace.json
├── .cursor-plugin/           # Cursor 插件清单（新增）
│   ├── plugin.json
│   └── marketplace.json
├── hooks/
│   ├── hooks.json            # Claude Code hooks（12 事件）
│   ├── cursor-hooks.json     # Cursor hooks（6 事件子集，新增）
│   └── stop-hook.py          # 共享（两边都调用）
├── skills/                   # 共享（Cursor 原生支持 SKILL.md）
├── agents/                   # 共享（Cursor 支持 Subagents）
├── rules/                    # Cursor Rules（新增，.mdc 格式）
│   ├── pipeline-guide.mdc    # Pipeline 编排指导（降级版）
│   ├── skill-resolution.mdc  # Skill 解析规则
│   ├── code-quality.mdc      # 代码质量规则
│   └── auto-continue.mdc     # 续跑行为指导
└── scripts/                  # 共享
```

### 4.3 能力降级矩阵

| Dev Harness 能力 | Claude Code | Cursor | 降级策略 |
|-----------------|------------|--------|---------|
| Skills/SKILL.md | 原生 | 原生 | 无需降级 |
| Agents/*.md | 原生 | Subagents | 格式兼容 |
| stop-hook 六道防线 | 12 事件全覆盖 | 6 事件 ~60% | stop 事件有，缺 pre/post-tool-use |
| 三层 Skill 解析 | skill-resolver.py 运行时 | Rules 静态指导 | .mdc 规则描述优先级，AI 自行遵循 |
| Pipeline 编排 | harness.py 状态驱动 | Rules 指导 + Agent 自主 | pipeline-guide.mdc 描述流程，不强制 |
| harness-state.json | 脚本读写 | Agent 自主维护 | .mdc 规则指导 Agent 更新 state 文件 |
| Web HUD | harness.py web-hud | 共享（同一脚本） | 无需降级 |
| gate 门禁 | 脚本自动运行 | Rules 指导 Agent 跑门禁 | auto-continue.mdc |

### 4.4 关键 .mdc 文件设计

#### rules/pipeline-guide.mdc

```markdown
---
description: "Dev Harness Pipeline 编排指导。当用户说 dev/开发/继续开发 时自动激活。"
globs: []
alwaysApply: false
---

# Dev Harness Pipeline 指导

当用户要求开发功能时，遵循以下流程：

## 检测阶段
1. 读取 .claude/harness-state.json 判断是否续接
2. 运行 detect-stack.sh 检测技术栈
3. 如有 .claude/dev-config.yml 读取项目配置

## 路线选择
- 大功能（需调研）→ 路线 B: research → prd → plan → implement → audit → test → review
- 标准功能 → 路线 C: plan → implement → audit → test → review
- 小改动/bug fix → 路线 D: implement → test
- 纯问答 → 不走 pipeline

## 每阶段完成后
- 更新 .claude/harness-state.json
- 运行门禁（build + test）
- 不等用户，继续下一阶段

## 死循环保护
- 同一步骤失败 3 次 → 停下报告用户
```

#### rules/skill-resolution.mdc

```markdown
---
description: "Skill 解析优先级规则。执行任何开发 Skill 前自动激活。"
globs: [".claude/skills/**", ".cursor/skills/**"]
alwaysApply: false
---

# Skill 解析优先级

执行开发任务时，按以下优先级查找可用的 Skill：

1. **L1 项目层**: .claude/skills/{name}/SKILL.md — 最高优先级
2. **L2 用户层**: ~/.claude/skills/{name}/SKILL.md
3. **L3 内置层**: 本插件自带的 generic-{name} Skill

如果在高优先级层找到了 Skill，不要使用低优先级层的同名 Skill。
```

### 4.5 Cursor Marketplace 发布

```json
// .cursor-plugin/plugin.json
{
  "name": "dev-harness",
  "version": "3.1.0",
  "description": "Harness Engineering pipeline for Cursor. Three-layer skill resolution, auto-loop, Web HUD.",
  "author": "brothelmdzz",
  "components": {
    "skills": "skills/",
    "rules": "rules/",
    "hooks": "cursor-hooks.json",
    "agents": "agents/",
    "mcp": null
  }
}
```

### 4.6 评测中的 Cursor 角色

Cursor 适配完成后，L2 评测的 2×2 矩阵才能填满：

```
组 A: Cursor Agent Mode，无 Dev Harness 插件
  → cursor --agent "Fix this issue: ..."

组 C: Cursor Agent Mode + Dev Harness 插件
  → cursor --agent "Fix this issue: ..." (插件自动激活)

对比 A vs C = Cursor 上的 harness 增量
对比 C vs D = 跨 IDE 一致性
```

---

## 五、L3 Meta-Harness 外循环

### 5.1 概念

引自 Stanford 论文 (ArXiv 2603.28052)：

> Model harness = 决定 LLM 看到什么信息的代码
> Meta-Harness = 自动优化 harness 的外层循环
> 关键发现：执行轨迹 > 压缩摘要（34.6% → 50.0%）

Dev Harness 的 pipeline.yml + skill-resolver + stop-hook 就是 harness。
Meta-Harness 外循环 = 用 AI 自动优化这些配置和代码。

### 5.2 数据基础（L2 产出）

外循环的输入是 L2 积累的执行轨迹：

```
eval/traces/
├── swe-001_full_20260405.json
├── swe-001_bare_20260405.json
├── swe-001_no-stophook_20260405.json
├── swe-002_full_20260405.json
├── ...
└── real-005_full_20260405.json
```

每个 trace 包含：阶段执行序列、token 消耗、错误链、修复记录、门禁结果。

### 5.3 外循环架构

```
                ┌──────────────────────┐
                │   Opus Proposer      │
                │   (coding agent)     │
                │                      │
                │ 输入:                 │
                │ · traces/ (执行轨迹)  │
                │ · pipeline.yml       │
                │ · skill-map.yml      │
                │ · stop-hook.py       │
                │ · eval scores        │
                │                      │
                │ 输出:                 │
                │ · 修改建议 (diff)     │
                │ · 理由分析            │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Apply & Evaluate   │
                │                      │
                │ 1. 应用 diff          │
                │ 2. 跑 L1 回归（门禁） │
                │ 3. 跑 L2 A/B 对照    │
                │ 4. 对比 before/after  │
                └──────────┬───────────┘
                           │
                           ▼
                ┌──────────────────────┐
                │   Archive & Decide   │
                │                      │
                │ · 记录到 Pareto 前沿  │
                │   (准确率 vs token)   │
                │ · 优于当前 → 采纳     │
                │ · 劣于当前 → 归档     │
                │ · 下一轮迭代          │
                └──────────────────────┘
```

### 5.4 Proposer Prompt 模板

```markdown
你是 Dev Harness 的优化 Agent。你的目标是分析评测执行轨迹，
找到框架配置/代码中可以改进的地方，提出具体修改。

## 你可以访问的文件

- eval/traces/ — 所有评测的完整执行轨迹
- defaults/pipeline.yml — Pipeline 阶段定义
- defaults/skill-map.yml — Skill 别名映射
- hooks/stop-hook.py — 续跑六道防线
- skills/*/SKILL.md — 各 Skill 的指令

## 分析流程

1. 读取最近 N 轮的执行轨迹
2. 找出失败案例，分析根因链：
   - 是 Skill 指令不够清晰导致 Agent 偏离？
   - 是门禁检查遗漏了某类错误？
   - 是 Pipeline 路线选择不当（应走 B 但走了 C）？
   - 是续跑时机不对（太早/太晚）？
3. 对比成功和失败案例的差异
4. 提出具体的代码/配置修改（给出 diff）

## 约束

- 每轮最多修改 3 个文件
- 修改必须通过 L1 回归测试
- 给出修改理由和预期收益
```

### 5.5 Pareto 前沿记录

```json
// eval/pareto-frontier.json
{
  "frontier": [
    {
      "version": "v3.1.0-baseline",
      "date": "2026-04-05",
      "pass_rate": 0.75,
      "avg_tokens": 85000,
      "avg_time_sec": 270,
      "config_hash": "abc123"
    },
    {
      "version": "v3.1.0-meta-iter-1",
      "date": "2026-04-12",
      "pass_rate": 0.78,
      "avg_tokens": 79000,
      "avg_time_sec": 250,
      "config_hash": "def456",
      "changes": "Optimized stop-hook sliding window from 5min to 3min"
    }
  ]
}
```

### 5.6 启动条件

Meta-Harness 外循环在以下条件满足后启动：

1. L2 A/B 对照已跑过 ≥ 3 轮，积累 ≥ 50 条 trace
2. L1 回归测试稳定在 90%+ 
3. 消融分析确认各组件有正向贡献（非负面）

---

## 六、实施时间线

```
Week 1 (v3.1 收尾):
  ├── commit 当前 v3.1 改动到 master
  ├── L1: 扩展 eval-runner.py 新增 14 个用例
  └── L2: 设计 trace 记录格式 + eval/traces/ 目录结构

Week 2 (L2 首轮):
  ├── L2: 编写 swe-bench adapter
  ├── L2: 选取 20 个 SWE-bench Lite 实例
  ├── L2: 跑首轮 bare vs harness 对照
  └── 用户提供 5 个真实任务

Week 3 (Cursor 分支):
  ├── git checkout -b cursor-adaptation
  ├── 创建 .cursor-plugin/ 目录和 plugin.json
  ├── 编写 4 个核心 .mdc 规则文件
  ├── 适配 cursor-hooks.json (6 事件子集)
  └── Cursor 上跑 L2 评测（组 A + 组 C）

Week 4 (L2 完整 + 报告):
  ├── L2: 2×2 矩阵四组全部跑完
  ├── L2: 消融分析 6 个配置
  ├── L2: 生成评测报告
  └── README 更新评测数据

Week 5+ (L3 启动):
  ├── 确认 L2 数据足够（≥50 traces）
  ├── 编写 Proposer prompt
  ├── 跑首轮 Meta-Harness 外循环
  └── 记录 Pareto 前沿
```

---

## 七、文件变更清单

### master 分支

| 文件 | 操作 | 说明 |
|------|------|------|
| eval/eval-runner.py | 修改 | 新增 14 个测试用例 + trace 记录 |
| eval/traces/ | 新增目录 | 执行轨迹归档 |
| eval/reports/ | 已有 | 评测报告输出 |
| eval/pareto-frontier.json | 新增 | Pareto 前沿记录 |
| eval/judge-prompt.md | 新增 | LLM-as-Judge 的 rubric |
| eval/swe-bench-adapter.py | 新增 | SWE-bench 接入适配器 |
| scripts/harness.py | 修改 | trace 记录功能 |

### cursor-adaptation 分支

| 文件 | 操作 | 说明 |
|------|------|------|
| .cursor-plugin/plugin.json | 新增 | Cursor 插件清单 |
| .cursor-plugin/marketplace.json | 新增 | Cursor Marketplace 注册 |
| hooks/cursor-hooks.json | 新增 | Cursor 6 事件 Hook 配置 |
| rules/pipeline-guide.mdc | 新增 | Pipeline 编排指导规则 |
| rules/skill-resolution.mdc | 新增 | Skill 解析优先级规则 |
| rules/code-quality.mdc | 新增 | 代码质量规则 |
| rules/auto-continue.mdc | 新增 | 续跑行为指导规则 |
