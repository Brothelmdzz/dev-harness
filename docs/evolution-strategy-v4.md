# Dev Harness v4.0 进化战略

> 研究日期：2026-04-04
> 基于：4 个并行研究 Agent 的调研结果综合
> 核心命题：从「后端全流程 Pipeline 工具」进化为「多角色多场景 AI 开发基础设施」

---

## 一、核心洞察

### 1.1 当前架构的根本假设

**"所有操作都是多阶段流水线"** — 这是 Dev Harness v3 的唯一运行模式。

```
用户输入 → /dev → init state → pipeline 循环 → commit
```

这个假设在以下场景中是错误的：
- 问一个技术问题（没有 pipeline）
- 修一个 typo（不需要 plan/audit/review）
- 写一个 PRD（不需要 implement/test）
- 跑一轮测试（不需要 research/plan）
- 审计一段代码（原子操作）

### 1.2 市场空白

> **没有任何竞品实现了"自动复杂度感知"** — 全部依赖用户手动选择模式。
> 
> - Superpowers：强制走完整流程（宁可过度流程化）
> - Cursor：Ask/Agent 手动下拉切换
> - Cline：Plan/Act 手动 toggle
> - Aider：/ask /code /architect 手动切换
> - OpenHands：Plan/Code/Headless 三级手动

**如果 Dev Harness 能自动判断任务复杂度并选择流程深度，这将是独一无二的差异化。**

### 1.3 三个进化方向

```
                    ┌─────────────────────────────────┐
                    │       Dev Harness v4.0           │
                    │   "AI 开发基础设施平台"           │
                    ├─────────┬──────────┬─────────────┤
                    │  多模式  │  多角色  │  可组合     │
                    │         │         │             │
                    │ pipeline│ backend │ Skill DAG   │
                    │ single  │ frontend│ 条件路由    │
                    │ convo   │ QA      │ I/O 契约    │
                    │         │ product │ 跨 IDE      │
                    │         │ business│             │
                    └─────────┴──────────┴─────────────┘
```

---

## 二、多模式架构（打破 Pipeline 唯一性）

### 2.1 三种运行模式

| 模式 | 语义 | state 行为 | stop-hook 行为 | 入口 |
|------|------|-----------|---------------|------|
| **pipeline** | 多阶段全流程 | 完整 pipeline 状态 | 六道防线 + 阶段推进 | `/dev` |
| **single** | 单个 Skill 执行 | 记录 skill + 完成状态 | 只检查 skill 是否完成 | `/fix` `/test` `/audit` `/prd` |
| **conversation** | 纯对话问答 | 不创建 state | 不介入 | `/ask` |

### 2.2 智能路由（自动复杂度感知）

借鉴 OMC 的 keyword-detector + Aider 的模式概念，但自动化：

```
用户输入 → 意图分类器（5 行 prompt）
  │
  ├─ "这个 API 怎么调？"      → mode: conversation → 不走 harness
  ├─ "帮我修一下这个 bug"      → mode: single(fix) → implement + test
  ├─ "写个 PRD"               → mode: single(prd) → prd skill
  ├─ "跑一下测试"             → mode: single(test) → test skill
  ├─ "新增一个用户模块"        → mode: pipeline(C) → plan→implement→...
  └─ "微服务拆分"             → mode: pipeline(B) → research→...→review
```

**关键设计**：分类结果可被用户覆盖。输出分类理由，用户可说"不，这个比较复杂，走完整流程"。

### 2.3 轻量入口 Skill 设计

每个轻量入口本质上是预设了 mode + profile + 单阶段的快捷方式：

| 入口 | 等价于 | 实现方式 |
|------|--------|---------|
| `/ask` | mode=conversation | 10 行 SKILL.md，不调用 harness |
| `/fix` | mode=single, skill=implement, auto-detect stack | 15 行 SKILL.md，委托 generic-implement |
| `/test` | mode=single, skill=test | 10 行 SKILL.md，委托 generic-test |
| `/audit` | mode=single, skill=audit | 10 行 SKILL.md，委托 generic-audit |
| `/prd` | mode=single, skill=prd | 10 行 SKILL.md，委托 create_prd |
| `/review` | mode=single, skill=review | 10 行 SKILL.md，委托 generic-review |
| `/dev` | mode=pipeline（现有） | 不变 |

### 2.4 state 结构演进

```json
{
  "version": "2.0",
  "mode": "pipeline | single | conversation",
  "session_id": "abc123",

  // mode=pipeline 时
  "pipeline": [...],
  "current_stage": "implement",

  // mode=single 时
  "single_skill": "test",
  "single_status": "IN_PROGRESS | DONE",

  // 共享
  "task": { "name": "...", "started_at": "..." },
  "metrics": { ... }
}
```

---

## 三、多角色架构（Profile 从别名前缀升级为角色模型）

### 3.1 角色模型设计

借鉴 Notion Custom Agents 的"角色 = 人格 + 指令 + 权限边界"：

```yaml
# defaults/profiles.yml
profiles:
  backend:
    description: "后端开发工程师"
    default_route: C
    default_mode: pipeline
    pipeline: [plan, implement, audit, docs, test, review, remember]
    skills_whitelist: "*"  # 全部可用

  frontend:
    description: "前端开发工程师"
    default_route: C
    default_mode: pipeline
    pipeline: [plan, implement, audit, test, review, remember]
    skill_aliases:
      implement: [frontend-implement, generic-implement]
      test: [frontend-test, generic-test]

  qa:
    description: "测试工程师"
    default_route: null  # QA 不走标准路线
    default_mode: single
    pipeline: [test, audit, review, remember]
    preferred_skills: [generic-test, generic-audit]
    forbidden_stages: [implement]  # QA 不写生产代码

  product:
    description: "产品经理"
    default_route: null
    default_mode: single
    pipeline: [research, prd, review, remember]
    preferred_skills: [create_prd, research_codebase]
    forbidden_stages: [implement, test]  # PM 不碰代码

  business:
    description: "业务分析师/运营"
    default_route: null
    default_mode: conversation
    pipeline: [research, remember]
    preferred_skills: [research_codebase]
    forbidden_stages: [implement, test, audit]
```

### 3.2 Profile → Pipeline 映射

当前：route 决定阶段集合，profile 只影响 Skill 别名。

进化后：**route × profile 二维决策**。

```python
def resolve_pipeline(route, profile):
    # profile 定义可用阶段上界
    profile_stages = PROFILES[profile]["pipeline"]
    # route 定义复杂度下界
    route_stages = ROUTE_STAGES[route]
    # 取交集
    return [s for s in profile_stages if s in route_stages]
```

例如：
- `qa + route C` → `[test, review, remember]`（qa 的 pipeline ∩ route C 的 stages）
- `product + route B` → `[research, prd, review, remember]`
- `backend + route C` → `[plan, implement, audit, docs, test, review, remember]`（现有行为不变）

### 3.3 测试工程师专用流

借鉴 OpenObserve 的"8 子 Agent 委员会"模式 + TestCollab MCP：

```
QA 用户: /test "登录功能有 bug，点击后没反应"

→ mode: single(test)
→ Skill: generic-test
→ 自动流程:
    1. 从 PRD 提取登录功能验收标准
    2. 分析代码定位登录相关逻辑
    3. 生成边界测试用例 + 异常场景
    4. 运行测试
    5. 定位失败点 → 输出 bug 报告
    6. (可选) 生成修复建议
```

### 3.4 产品经理专用流

借鉴 ChatPRD 的"一句话 → 完整 PRD"：

```
PM 用户: /prd "我们需要一个会员积分系统"

→ mode: single(prd)
→ Skill: create_prd (增强版)
→ 自动流程:
    1. 多轮追问：目标用户？核心场景？与现有系统关系？
    2. 竞品参考（如 WebSearch）
    3. 生成结构化 PRD
    4. 模拟 CPO 审查（找战略缺口）
    5. 输出 .claude/project-design/*-prd.md
    6. (可选) 从 PRD 自动派生测试矩阵
```

---

## 四、可组合架构（Pipeline 进化为 Skill DAG）

### 4.1 从线性流水线到有向图

借鉴 LangGraph 的 StateGraph + GitHub Actions 的条件执行：

```yaml
# defaults/pipeline.yml (v4.0)
stages:
  - name: research
    when: "route in [B]"

  - name: prd
    when: "route in [A, B]"
    human: true

  - name: plan
    when: "route in [A, B, C]"
    human: true

  - name: implement
    when: "route in [A, B, C, C-lite, D]"
    loop: true
    gate: [build, test]
    max_retries: 3
    on_failure: debug   # 新增：失败时跳转到 debug 节点

  - name: debug         # 新增：条件节点
    when: "implement.failed"
    next:
      fixed: implement  # 修好了回到 implement（环形）
      stuck: review     # 修不好跳到 review 求助

  - name: audit
    parallel_with: [docs, test]  # 新增：多路并行

  - name: docs
    when: "changed_api"

  - name: test
    auto_fix: true

  - name: review
    when: "route in [A, B, C]"

  - name: remember
    when: "always"
```

### 4.2 Skill 接口契约

借鉴 MCP 能力发现 + GitHub Actions 的 inputs/outputs：

```yaml
# skills/generic-test/SKILL.md 增加 frontmatter
---
name: generic-test
description: 通用测试执行
inputs:
  - name: tech_stack
    description: 技术栈检测结果
    source: detect-stack  # 或上游 Skill 输出
  - name: plan_file
    description: 计划文件路径（可选）
    optional: true
outputs:
  - name: test_report
    path: .claude/reports/test-*.md
  - name: pass_rate
    type: number
---
```

好处：
1. Skill 可独立测试（给定 inputs，验证 outputs）
2. Skill 解析器可根据 inputs/outputs 自动连线
3. Web HUD 可展示数据流向

### 4.3 跨 IDE 兼容

借鉴 AGENTS.md 标准 + rule-porter 转换工具：

```
Dev Harness 输出:
├── AGENTS.md           ← 通用规则（所有 AI 工具可读）
├── CLAUDE.md           ← Claude 专属（@import、Hook）
├── .cursor/rules/*.mdc ← Cursor 格式（自动生成）
└── .github/copilot-instructions.md ← Copilot 格式（自动生成）
```

实现方式：在 `/dev` 完成时（或通过 hook），自动从 CLAUDE.md 生成其他格式的衍生文件。

---

## 五、实施路线图

### Phase 1: 多模式基础（v3.2, 2 周）

改动量：~100 行

| 任务 | 文件 | 行数 |
|------|------|------|
| state 增加 mode 字段 | harness.py | ~30 |
| stop-hook 按 mode 分支处理 | stop-hook.py | ~20 |
| /ask 轻量入口 | skills/ask/SKILL.md | ~10 |
| /fix 轻量入口 | skills/fix/SKILL.md | ~15 |
| /test 轻量入口 | skills/test-only/SKILL.md | ~10 |
| /audit 轻量入口 | skills/audit-only/SKILL.md | ~10 |

**验收标准**：用户可以 /ask 问问题不触发 pipeline，/fix 修 bug 只跑 implement+test。

### Phase 2: 多角色（v3.3, 2 周）

改动量：~150 行

| 任务 | 文件 | 行数 |
|------|------|------|
| profiles.yml 角色定义 | defaults/profiles.yml | ~60 |
| harness.py init --profile 感知 | harness.py | ~30 |
| route × profile 二维决策 | harness.py | ~20 |
| /dev 启动时 profile 选择 UI | skills/dev/SKILL.md | ~20 |
| QA 专用流提示词 | skills/generic-test/SKILL.md | ~20 |

**验收标准**：`/dev --profile qa` 只走 test→review→remember。

### Phase 3: 智能路由（v4.0, 3 周）

改动量：~200 行

| 任务 | 文件 | 行数 |
|------|------|------|
| 意图分类器 prompt | skills/dev/SKILL.md | ~30 |
| 自动 mode 选择逻辑 | skills/dev/SKILL.md | ~40 |
| session-start Hook | hooks/session-start.py | ~50 |
| user-prompt-submit Hook（关键词路由） | hooks/prompt-router.py | ~50 |
| hooks.json 注册新 Hook | hooks/hooks.json | ~10 |
| Web HUD 展示模式/角色 | harness.py | ~20 |

**验收标准**：用户说"帮我看看这个函数"自动走 conversation 模式，说"新增用户模块"自动走 pipeline 模式。

### Phase 4: 可组合进化（v4.1, 长期）

| 任务 | 说明 |
|------|------|
| Pipeline DAG（条件边 + 环形） | pipeline.yml 支持 on_failure 跳转 |
| Skill I/O 契约 | SKILL.md frontmatter 增加 inputs/outputs |
| 并行阶段执行 | subagent 并发 audit+docs+test |
| 跨 IDE 规则同步 | sync-rules hook 生成 .cursorrules / AGENTS.md |
| Web HUD → 开发者门户 | Skill 目录浏览 + 操作触发 |

---

## 六、核心设计原则

1. **Pipeline 是场景之一，不是唯一模式** — conversation/single/pipeline 三种模式平等共存
2. **角色决定权限边界** — QA 不碰生产代码，PM 不执行 git push
3. **复杂度自动感知，人可覆盖** — 默认智能路由，用户一句话可切换
4. **Skill 是原子单元** — 有明确的 inputs/outputs，可独立执行，可自由组合
5. **跨 IDE 是输出格式问题，不是架构问题** — 核心逻辑在 Claude Code，其他 IDE 通过规则文件同步

---

## 七、竞争定位演进

```
v3.0: "后端开发 Pipeline 工具"
  → 竞品: OMC, Superpowers (同赛道正面竞争)

v4.0: "AI 开发基础设施平台"
  → 定位: 可组合的 Skill DAG + 多角色 Profile + 智能路由
  → 竞品: 无直接对标（Backstage 理念 + Superpowers 方法论 + OMC 编排）
  → 与 Superpowers/OMC 的关系: 从竞争变为互补（它们的 Skill 可接入 DH 的三层解析）
```
