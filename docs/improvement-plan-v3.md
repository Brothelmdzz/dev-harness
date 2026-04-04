# Dev Harness v3.0 改进方案

> 目标：从「个人后端开发工具」升级为「部门/公司级 AI 开发流水线平台」
> 作者：曹济元
> 日期：2026-04-04
> 版本：v1.0 DRAFT

---

## 一、方案概述

### 1.1 现状评估

Dev Harness v2.0 已具备：
- 三层 Skill 解析 (L1 项目 > L2 用户 > L3 内置) — **独创核心优势**
- YAML 可配置 Pipeline + 路线分级 (B/A/C/C-lite/D)
- 12 个专用 Agent + 14 个 Skill
- Stop Hook 自动续跑 + Rich HUD + Statusline
- 评测框架 (21 测试, 5 维度)

与主流竞品对比：

| 维度 | 当前得分 | 目标得分 | 差距 |
|------|---------|---------|------|
| 核心架构 | 8/10 | 9/10 | 路径发现 + Hook 加固 |
| 后端开发覆盖 | 7/10 | 9/10 | TDD + 回滚 |
| 前端/产品覆盖 | 1/10 | 7/10 | 全新 Skill 套件 |
| 可观测性 | 9/10 | 9/10 | 已领先 |
| 稳定性/安全 | 5/10 | 8/10 | worktree + Hook 加固 |
| 文档/可拓展 | 3/10 | 8/10 | 教程 + 模板 + 贡献指南 |
| 企业治理 | 4/10 | 7/10 | 审计日志 + 成本 + 权限 |

### 1.2 核心改进方向

```
                    Dev Harness v3.0 改进全景图

  ┌─────────────────────────────────────────────────────────────┐
  │                    P0: 基础加固层                            │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
  │  │ 路径稳定 │  │ Hook加固 │  │ Worktree │  │ Rate Limit  │ │
  │  │ $DH_HOME │  │ 防循环   │  │ 隔离执行 │  │ 恢复        │ │
  │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │                    P1: 多角色 Skill 层                       │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
  │  │ 前端开发 │  │ 产品经理 │  │ QA 测试  │  │ DevOps 部署 │ │
  │  │ Skill套件│  │ Skill套件│  │ TDD集成  │  │ Skill套件   │ │
  │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │                    P2: 同事友好层                             │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
  │  │ Skill    │  │ 快速上手 │  │ 配置模板 │  │ 贡献指南    │ │
  │  │ 脚手架   │  │ 教程     │  │ 库       │  │ + 示例      │ │
  │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │                    P3: 企业治理层                             │
  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
  │  │ 审计日志 │  │ 成本追踪 │  │ 权限分级 │  │ 团队看板    │ │
  │  └──────────┘  └──────────┘  └──────────┘  └─────────────┘ │
  └─────────────────────────────────────────────────────────────┘
```

### 1.3 设计原则

1. **约束优于提示** — Harness Engineering 核心理念：用代码约束（Hook/门禁/eval）替代纯 prompt 说教
2. **三层解析是一切的基础** — 所有新 Skill 都遵循 L1>L2>L3 优先级，新角色复用同一套解析机制
3. **同事改得动** — 每个 Skill 是独立的 Markdown 文件，不需要改 Python/JS，改 SKILL.md 就能定制
4. **可验证** — 每项改进都有对应的 eval 测试用例
5. **渐进交付** — P0→P1→P2→P3 分层实施，每层独立可用

---

## 二、实现路径

### Phase 0: 基础加固 (1 周)

> 不改功能，只修基座。没有这层，上面全白搭。

#### 0.1 路径发现稳定化

**问题**：当前每次调用都要 `find ~/.claude/plugins/cache -path "*dev-harness*"` + 嵌套 `bash $(dirname $(find ...))` ，在 Windows/Mac/Linux 上行为不一致，且性能差。

**方案**：

```
改动文件:
  scripts/find-dh-home.sh     — 保留，作为一次性发现脚本
  hooks/stop-hook.py          — 移除 find，改用 __file__ 回溯
  hooks/statusline.js         — 同上，用 __dirname 回溯
  skills/dev/SKILL.md          — 启动时一次 find → 设 DH_HOME 变量 → 后续全用变量
  skills/*/SKILL.md            — 移除所有 find 嵌套，改用 $DH_HOME
```

**实现**：
- `stop-hook.py`：已有 `Path(__file__).parent.parent` 回溯，不需要 find — 确认无误
- `statusline.js`：用 `path.resolve(__dirname, '..')` 回溯 — 确认无误
- `skills/dev/SKILL.md`：启动流程 Step 0 改为：

```bash
# 一次发现，全局复用
DH_HOME=$(bash "$(dirname "$(find ~/.claude/plugins/cache -name find-dh-home.sh -path '*dev-harness*' 2>/dev/null | head -1)")/find-dh-home.sh")
# 后续所有调用:
python "$DH_HOME/scripts/harness.py" ...
python "$DH_HOME/scripts/skill-resolver.py" ...
bash "$DH_HOME/scripts/detect-stack.sh"
```

- 每个 generic-* SKILL.md 的脚本引用统一改为 `$DH_HOME/scripts/...`
- **eval 新增**：`test_dh_home_resolution()` — 验证 5 种安装路径都能正确发现

#### 0.2 Stop Hook 防循环加固

**问题**：当前只有 `error_count >= 3` 和 `stop_hook_active` 两道防线，缺少时间维度保护。

**方案**：在 `stop-hook.py` 增加三道防线：

```python
# ==================== 防循环加固 ====================

# 防线 1: 上下文使用率（已有 ccData 可读）
context_pct = hook_input.get("context_window", {}).get("used_pct", 0)
if context_pct > 80:
    # 触发 remember 保存进度，然后停止
    state["current_stage"] = "remember"
    save_state(state, state_file)
    output_block("上下文使用率 > 80%，保存进度后停止。", state, project_root)
    return

# 防线 2: 阶段超时（单阶段超过 30 分钟未完成 → 可能卡住）
if stage.get("started_at"):
    started = datetime.fromisoformat(stage["started_at"].replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if elapsed > 1800:  # 30 分钟
        sys.exit(0)  # 让 Claude 停下来

# 防线 3: 总运行时长（超过 max_duration 强制停止）
task_started = state.get("task", {}).get("started_at", "")
if task_started:
    t0 = datetime.fromisoformat(task_started.replace("Z", "+00:00"))
    total_elapsed = (datetime.now(timezone.utc) - t0).total_seconds()
    max_duration = state.get("metrics", {}).get("max_duration", 7200)  # 默认 2h
    if total_elapsed > max_duration:
        sys.exit(0)

# 防线 4: 滑动窗口频率限制（5 分钟内触发 > 10 次 → 可能死循环）
eval_log = project_root / ".claude" / "harness-eval.jsonl"
if eval_log.exists():
    recent_count = count_recent_events(eval_log, minutes=5)
    if recent_count > 10:
        sys.exit(0)
```

**eval 新增**：
- `test_context_overflow_stop()` — 模拟 context > 80% 时应停止
- `test_stage_timeout_stop()` — 模拟阶段超时应停止
- `test_sliding_window_stop()` — 模拟高频触发应停止

#### 0.3 Git Worktree 隔离

**问题**：当前 implement 阶段直接在工作目录改代码，门禁失败 3 次后代码处于不可控状态。

**方案**：

```
新增文件:
  scripts/worktree.sh          — worktree 创建/清理脚本
```

```bash
#!/bin/bash
# worktree.sh — implement 阶段的代码隔离
# 用法:
#   bash worktree.sh create <branch-name>   → 创建 worktree 并输出路径
#   bash worktree.sh merge                  → 合并回主分支
#   bash worktree.sh cleanup                → 清理 worktree

ACTION=$1
BRANCH=${2:-"dh-implement-$(date +%Y%m%d-%H%M%S)"}
WT_DIR=".claude/worktrees/$BRANCH"

case $ACTION in
  create)
    git worktree add "$WT_DIR" -b "$BRANCH" 2>/dev/null
    echo "$WT_DIR"
    ;;
  merge)
    CURRENT=$(git branch --show-current)
    cd "$(git rev-parse --show-toplevel)"
    git merge --no-ff "$BRANCH" -m "merge: implement via dev-harness"
    ;;
  cleanup)
    git worktree remove "$WT_DIR" --force 2>/dev/null
    git branch -D "$BRANCH" 2>/dev/null
    ;;
esac
```

**集成到 Pipeline**：
- `skills/dev/SKILL.md` 的 implement 阶段：开始前 `create` → 结束后 `merge`
- 门禁失败 3 次时 `cleanup` 回到干净状态
- 在 `harness-state.json` 中记录 `worktree_path` 和 `worktree_branch`

**降级**：如果 `git worktree` 不可用（非 git 项目），回退到当前行为（直接在工作目录操作）。

**eval 新增**：`test_worktree_isolation()` — 验证创建/合并/清理流程

#### 0.4 Rate Limit 恢复

**问题**：OMC 有 rate limit 自动恢复，你还没有。

**方案**：在 `stop-hook.py` 检测 Claude 的最后消息是否包含 rate limit 关键词：

```python
last_msg = hook_input.get("last_assistant_message", "")
if any(kw in last_msg.lower() for kw in ["rate limit", "hit your limit", "resets"]):
    # 写入状态: paused + resume_at 时间
    state["paused"] = True
    state["pause_reason"] = "rate_limit"
    state["resume_at"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    save_state(state, state_file)
    sys.exit(0)  # 不续跑，等 rate limit 恢复
```

在 `skills/dev/SKILL.md` 启动时检查 `pause_reason == "rate_limit"` → 判断是否已过恢复时间 → 自动恢复。

---

### Phase 1: 多角色 Skill 套件 (2 周)

> 从「后端开发者工具」扩展为「研发团队工具」

#### 1.1 角色-Skill 映射设计

```yaml
# 新增 skill-map.yml 条目

# ==================== 前端开发 ====================
frontend_research:
  - frontend-research
  - generic-research          # 降级到通用

frontend_implement:
  - frontend-implement
  - generic-implement         # 降级到通用

frontend_test:
  - frontend-test
  - generic-test              # 降级到通用

# ==================== 产品经理 ====================
product_prd:
  - product-prd
  - prd
  - generic-prd               # 降级到通用

product_review:
  - product-review
  - generic-review             # 降级到通用

# ==================== QA 工程 ====================
qa_test:
  - qa-e2e
  - test-apis
  - generic-test

qa_regression:
  - qa-regression
  - generic-test
```

#### 1.2 新增 Skill: generic-frontend-implement

```
新增文件: skills/generic-frontend-implement/SKILL.md
```

核心内容:
- 检测前端技术栈 (React/Vue/Angular/Next.js)
- 组件实现 → 样式实现 → 路由配置 → 状态管理
- 门禁: `npm run build` → `npm run lint` → `npm test`
- 浏览器快照验证（如有 Playwright Skill 则调用）
- 遵循项目已有的组件规范和设计系统

#### 1.3 新增 Skill: generic-frontend-research

```
新增文件: skills/generic-frontend-research/SKILL.md
```

核心内容:
- 三路并行 Explore Agent:
  - A: 组件层（扫描组件树、Props 定义、状态管理）
  - B: 路由/页面层（扫描路由配置、页面结构、权限控制）
  - C: API 集成层（扫描 API 调用、数据流、错误处理）
- 输出 `.claude/research/{topic}-frontend.md`

#### 1.4 新增 Skill: generic-product-prd

```
新增文件: skills/generic-product-prd/SKILL.md
```

核心内容:
- 面向产品经理的需求对齐流程
- 关注点: 用户故事、验收标准、优先级矩阵、数据埋点
- 多轮对话模板:
  - 第 1 轮: 用户画像、使用场景、核心价值
  - 第 2 轮: 功能列表、优先级 (P0/P1/P2)、MVP 边界
  - 第 3 轮: 交互流程、异常场景、降级方案
  - 第 4 轮: 验收标准、数据指标、上线计划
- 输出 PRD 包含: 用户故事地图 + 功能矩阵 + 验收 checklist

#### 1.5 新增 Skill: generic-tdd

```
新增文件: skills/generic-tdd/SKILL.md
```

核心内容（学习 Superpowers 的 TDD 理念）:
- RED-GREEN-REFACTOR 循环:
  1. RED: 先写一个会失败的测试
  2. GREEN: 写最小代码让测试通过
  3. REFACTOR: 优化代码（测试仍绿）
- 与 implement 阶段集成: 每个 Phase 的变更清单中标注测试优先级
- 门禁加强: build → **test(新增)** → test(已有) → validate

**集成方式**:
- 在 `skill-map.yml` 中 `implement` 的别名列表加入 `tdd-implement`
- 项目可通过 `.claude/dev-config.yml` 选择是否启用 TDD 模式:

```yaml
# .claude/dev-config.yml
tdd: true     # 启用 TDD 模式，implement 阶段强制先写测试
# tdd: false  # 传统模式（默认）
```

#### 1.6 Pipeline 路由扩展

当前路线只区分任务复杂度 (B/A/C/C-lite/D)，不区分角色。改为二维路由:

```yaml
# defaults/pipeline.yml 扩展

# 维度 1: 复杂度路线（保持不变）
routes:
  B: [research, prd, plan, implement, audit, docs, test, review, remember]
  A: [prd, plan, implement, audit, docs, test, review, remember]
  C: [plan, implement, audit, docs, test, review, remember]
  C-lite: [implement, test, remember]
  D: [implement, test, remember]

# 维度 2: 角色 profile（新增，影响 Skill 解析的别名查找）
profiles:
  backend:                       # 默认
    skill_prefix: ""             # 沿用现有别名
  frontend:
    skill_prefix: "frontend_"   # research → frontend_research
  product:
    skill_prefix: "product_"    # prd → product_prd
  fullstack:
    skill_prefix: ""            # 用通用别名，但 detect-stack 检测前后端
  qa:
    skill_prefix: "qa_"         # test → qa_test
```

**使用方式**:
```
/dev                             # 默认后端
/dev --profile frontend          # 前端模式
/dev --profile product           # 产品经理模式
/dev --profile qa                # QA 模式
```

**实现**: `skill-resolver.py` 的 `SKILL_ALIASES` 查找时，先尝试 `{profile_prefix}{stage}`，再 fallback 到无前缀。

---

### Phase 2: 同事友好层 (1 周)

> 让同事 10 分钟上手，30 分钟写出自己的 Skill。

#### 2.1 Skill 脚手架命令

新增一个辅助脚本 `scripts/scaffold.sh`:

```bash
#!/bin/bash
# 创建新 Skill 的脚手架
# 用法: bash scaffold.sh <skill-name> [--role frontend|backend|product|qa]

SKILL_NAME=$1
ROLE=${2:-backend}
TARGET=".claude/skills/$SKILL_NAME"

mkdir -p "$TARGET"
cat > "$TARGET/SKILL.md" << 'TEMPLATE'
---
name: {{SKILL_NAME}}
description: {{一句话描述。Use when: 用户说"xxx"。}}
---

# {{SKILL_NAME}}

## 角色
你是 [角色名]。你的职责是 [一句话描述职责]。

## 执行流程

### 第一步: [动作]
[具体步骤]

### 第二步: [动作]
[具体步骤]

### 第三步: [动作]
[具体步骤]

## 产出
保存到 `.claude/reports/{{skill-name}}-{date}.md`

## 约束
- [约束 1]
- [约束 2]
TEMPLATE

# 替换占位符
sed -i "s/{{SKILL_NAME}}/$SKILL_NAME/g" "$TARGET/SKILL.md"

echo "已创建: $TARGET/SKILL.md"
echo "编辑 SKILL.md 后，/dev 会自动识别为 L1 项目级 Skill"
```

**使用**:
```bash
# 同事想为自己的项目写一个定制审计 Skill
bash $DH_HOME/scripts/scaffold.sh my-audit

# 生成的骨架在 .claude/skills/my-audit/SKILL.md
# 编辑后立即生效（L1 优先级）
```

#### 2.2 配置模板库

```
新增目录: templates/
  templates/dev-config-springboot.yml   — Spring Boot 项目配置模板
  templates/dev-config-nextjs.yml       — Next.js 项目配置模板
  templates/dev-config-python.yml       — Python 项目配置模板
  templates/dev-config-monorepo.yml     — Monorepo 配置模板
  templates/dev-config-minimal.yml      — 最小化配置模板
```

每个模板包含:
- 项目名、技术栈
- 门禁命令 (build/test/lint)
- Skill 覆盖 (哪些阶段用项目自定义 Skill)
- Wiki 配置 (Confluence/飞书)
- 注释说明每个字段的作用

**使用**: `bash $DH_HOME/scripts/scaffold.sh --config springboot` → 复制模板到 `.claude/dev-config.yml`

#### 2.3 快速上手教程

```
新增文件: docs/quickstart.md
```

结构:
1. 5 分钟安装验证 (截图 + 命令)
2. 第一个 /dev 任务 (手把手走一遍 C-lite 路线)
3. 写第一个 L1 Skill (用 scaffold 生成 → 编辑 → 验证)
4. 配置项目 dev-config.yml (复制模板 → 修改)
5. 查看 HUD (Rich 面板截图 + 字段说明)
6. 常见问题 (FAQ)

#### 2.4 贡献指南

```
新增文件: docs/contributing.md
```

结构:
1. Skill 编写规范:
   - SKILL.md 结构 (frontmatter + 角色 + 流程 + 产出 + 约束)
   - 命名规范 (`generic-{role}-{stage}` / `{project}-{stage}`)
   - 单文件原则 (一个 Skill 一个文件，不要有外部依赖)
   - 测试要求 (每个 Skill 至少 2 个 eval 用例)
2. Agent 编写规范:
   - model 选择 (haiku: 快速搜索 / sonnet: 标准实现 / opus: 深度推理)
   - tools 最小化原则 (只声明需要的工具)
   - 约束模板 (必须有「不做什么」的约束)
3. Pipeline 扩展规范:
   - 新增阶段: 在 `pipeline.yml` 加条目 + `skill-map.yml` 加映射
   - 新增路线: 在 `harness.py` 的 `ROUTE_STAGES` 加条目
4. 提交流程:
   - Fork → Branch → eval 通过 → PR

#### 2.5 Skill 可视化索引

新增 `scripts/skill-index.py` — 自动扫描所有 L1/L2/L3 Skill 并输出索引:

```
$ python skill-index.py

Dev Harness Skill 索引
========================

Pipeline 阶段映射:

  research    L1: audit-research (项目)    → 代码库深度调研
              L3: generic-research (内置)  → 通用代码库扫描

  implement   L2: implement_plan (用户)    → 按计划文档执行
              L3: generic-implement (内置) → 通用计划执行

  audit       L1: audit-logic (项目)       → EHub 业务逻辑审计
              L3: generic-audit (内置)     → 通用代码审计

  ...

自定义方式:
  项目层: 在 .claude/skills/{name}/SKILL.md 创建
  用户层: 在 ~/.claude/skills/{name}/SKILL.md 创建
  脚手架: bash $DH_HOME/scripts/scaffold.sh <name>
```

---

### Phase 3: 企业治理层 (2 周)

> 管理者关心的不是代码怎么写，是「可控、可审、可量化」。

#### 3.1 结构化审计日志

当前的 `harness-eval.jsonl` 只记录 event + detail。扩展为完整审计日志:

```json
{
  "timestamp": "2026-04-04T10:30:00Z",
  "session_id": "abc-123",
  "user": "caojiyuan",
  "project": "ehub-integrated-platform",
  "task": "permit-extension",
  "stage": "implement",
  "phase": "Phase 2",
  "event": "gate_check",
  "detail": {
    "gate": "build",
    "command": "./gradlew build -x test",
    "result": "PASS",
    "duration_sec": 45,
    "exit_code": 0
  },
  "model": "claude-opus-4-6",
  "token_estimate": 15000,
  "cost_estimate": 0.45
}
```

**新增字段**: `session_id`, `user`, `model`, `token_estimate`, `cost_estimate`

#### 3.2 成本追踪

在 `statusline.js` 中已有 `ccData.cost.total`，扩展到 harness 状态:

```python
# harness.py update 时从环境变量/hook 输入读取成本信息
# 每次 update 写入 state["metrics"]["estimated_cost"]
```

在 HUD 面板底部显示:
```
Cost: $2.45 (Opus: $1.80, Sonnet: $0.55, Haiku: $0.10)
```

在 eval 报告中汇总:
```
平均每任务成本: $3.20
平均每阶段成本: implement $1.50 > review $0.80 > audit $0.40 > ...
```

#### 3.3 权限分级

通过 `dev-config.yml` 控制各阶段的自治权限:

```yaml
# .claude/dev-config.yml
permissions:
  auto_fix: true           # 允许自动修复 (默认 true)
  auto_continue: true      # 允许自动续跑 (默认 true)
  max_auto_phases: 5       # 最多自动续跑多少个 Phase (默认无限)
  require_approval:
    - prd                  # PRD 需要人审批
    - plan                 # 计划需要人审批
  block_stages:
    - wiki                 # 禁止 wiki 自动同步（需手动触发）
```

在 `stop-hook.py` 和 `skills/dev/SKILL.md` 中读取并遵守。

#### 3.4 团队看板数据导出

新增 `scripts/team-report.py`:

```bash
# 汇总团队所有成员的 harness-eval.jsonl
python team-report.py --scan /c/work/*/  --output team-report.md
```

输出:
```markdown
# Dev Harness 团队周报 (2026-W14)

## 总览
| 成员 | 任务数 | 阶段完成 | 自动修复 | 阻塞 | 成本 |
|------|--------|---------|---------|------|------|
| 张三 | 5 | 32 | 8 | 2 | $12.50 |
| 李四 | 3 | 21 | 5 | 1 | $8.30 |

## Skill 使用率
L1 (项目): 45%  L2 (用户): 15%  L3 (内置): 40%

## 门禁通过率
build: 92%  test: 78%  audit: 85%
```

---

## 三、预期效果

### 3.1 量化指标

| 指标 | 当前 (v2.0) | 目标 (v3.0) | 衡量方式 |
|------|------------|------------|---------|
| 新项目接入时间 | 30min+ (需手写 config) | **5min** (scaffold + 模板) | 从安装到第一次 /dev 成功 |
| 同事写 L1 Skill | 2h+ (从零开始) | **30min** (scaffold + 教程) | 从决定写到 eval 通过 |
| Pipeline 自动完成率 | ~60% (常因 Hook/路径问题中断) | **>85%** (加固后) | DONE stages / total stages |
| 门禁失败后恢复 | 不可控 (直接在工作目录) | **干净回滚** (worktree) | 失败后 git status 是否干净 |
| 覆盖角色 | 1 (后端) | **4** (后端/前端/产品/QA) | 可用 --profile 数量 |
| eval 测试用例 | 21 | **35+** | eval run-all 用例数 |
| 死循环发生率 | 偶发 (缺时间窗口) | **接近 0** (四道防线) | eval 中死循环测试全过 |

### 3.2 定性效果

**对开发者**:
- `/dev` 一条命令跑完全流程，不管什么项目都能用（只是深度不同）
- 写 Skill 像写 Markdown 一样简单，不需要学 Python/JS
- 失败了有 worktree 兜底，不怕代码被搞乱

**对 Tech Lead**:
- HUD + 审计日志看得到每个人的 Pipeline 执行情况
- 成本追踪知道 AI 辅助到底花了多少钱
- 三层 Skill 让项目级约束自动生效，不依赖口头规范

**对管理者**:
- 团队看板量化 AI 辅助效率
- 权限分级控制自治边界
- 评测框架证明质量不是黑箱

---

## 四、评估方案

### 4.1 Eval 框架扩展

在现有 5 维度 21 测试基础上，扩展为 8 维度 35+ 测试:

```python
# eval-runner.py 新增测试

METRICS = {
    # === 现有 ===
    "skill_resolution":   { "weight": 1.0 },  # 三层解析
    "state_management":   { "weight": 1.0 },  # 状态读写
    "auto_continue":      { "weight": 2.0 },  # 自动续跑（核心）
    "gate_detection":     { "weight": 0.5 },  # 构建检测
    "pipeline_routing":   { "weight": 1.0 },  # 路线判断

    # === 新增 ===
    "safety_guards":      { "weight": 2.0 },  # 防循环四道防线
    "worktree_isolation": { "weight": 1.5 },  # worktree 创建/合并/清理
    "multi_profile":      { "weight": 1.0 },  # 多角色 profile 解析
}
```

新增测试用例:

| 测试 | 维度 | 验证内容 |
|------|------|---------|
| `test_context_overflow_stop` | safety_guards | context > 80% 时正确停止 |
| `test_stage_timeout_stop` | safety_guards | 单阶段超 30min 正确停止 |
| `test_total_duration_stop` | safety_guards | 总时长超限正确停止 |
| `test_sliding_window_stop` | safety_guards | 高频触发正确停止 |
| `test_rate_limit_pause` | safety_guards | rate limit 时正确暂停 |
| `test_worktree_create` | worktree_isolation | worktree 创建成功 |
| `test_worktree_merge` | worktree_isolation | worktree 合并回主分支 |
| `test_worktree_cleanup_on_failure` | worktree_isolation | 失败时正确清理 |
| `test_worktree_fallback` | worktree_isolation | 非 git 项目降级 |
| `test_frontend_profile_resolution` | multi_profile | --profile frontend 正确路由 |
| `test_product_profile_resolution` | multi_profile | --profile product 正确路由 |
| `test_profile_fallback` | multi_profile | 未知 profile 降级到默认 |
| `test_dh_home_resolution_windows` | skill_resolution | Windows 路径发现 |
| `test_dh_home_resolution_mac` | skill_resolution | macOS 路径发现 |

### 4.2 实战验证矩阵

| 项目 | Profile | 路线 | 验证点 |
|------|---------|------|--------|
| ehub-integrated-platform | backend | C | L1 audit-logic 命中 + 门禁 |
| ehub-portal-front (前端) | frontend | C | L3 generic-frontend 降级 |
| 新 Python 项目 | backend | B | 全流程从 research 到 wiki |
| 产品需求对齐 | product | A | PRD 多轮对话质量 |

### 4.3 验收标准

| 里程碑 | 标准 | 验证方式 |
|--------|------|---------|
| P0 完成 | eval 加权分 >= 90% | `python eval-runner.py run-all` |
| P1 完成 | 4 个 profile 可用 + 新 Skill eval 通过 | `python skill-resolver.py --all --profile frontend` |
| P2 完成 | 新同事 30min 内完成 quickstart | 邀请 2 位同事实测 |
| P3 完成 | 团队看板可生成 | `python team-report.py --scan ...` |

---

## 五、后续演进

### 5.1 路线图

```
v3.0 (本次)            v3.1                    v3.5                   v4.0
─────────────────  ──────────────────  ─────────────────────  ────────────────────
P0 基础加固         通知系统             跨平台 Skill 兼容      AI Agent 自进化
P1 多角色 Skill     (桌面通知/飞书/      (Codex/Gemini CLI      (Skill 自动生成
P2 同事友好          Slack webhook)       /Cursor 兼容)          /自动优化/自动
P3 企业治理         CI/CD 集成                                   淘汰低效 Skill)
                    (GitHub Actions      自定义 Pipeline
                     hook)               DSL (YAML → 可视化
                                         编辑器)
                    Skill 市场
                    (团队内部共享
                     + 评分)
```

### 5.2 v3.1 规划 — 通知 + CI/CD

**通知系统**:
- Pipeline 完成/失败时发送通知
- 渠道: 桌面通知 (node-notifier) / 飞书 webhook / Slack webhook
- 在 `dev-config.yml` 配置:

```yaml
notifications:
  on_complete: [desktop, lark]
  on_failure: [desktop, lark]
  lark_webhook: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

**CI/CD 集成**:
- GitHub Actions / GitLab CI pre-commit hook
- PR 创建时自动触发 `generic-review` (三路审查)
- CI 失败时自动触发 `debugger` agent 诊断

### 5.3 v3.5 规划 — 跨平台兼容

当前 Dev Harness 只能在 Claude Code 中运行。目标: SKILL.md 遵循 Agent Skills 开放标准，让同一套 Skill 在 Codex / Gemini CLI / Cursor 中也能用。

**策略**:
- Pipeline 编排层 (harness.py, stop-hook.py) 保持 Claude Code 专用
- Skill 内容层 (SKILL.md) 遵循开放标准，不依赖 Claude Code 专有语法
- 三层解析的 L3 内置 Skill 可以直接被其他工具加载

### 5.4 v4.0 展望 — Skill 自进化

基于 eval 数据，让框架自己优化:
- Skill 效果评分 (门禁通过率、自动修复率、用户满意度)
- 低效 Skill 自动标注，建议替换
- 高效 Skill 自动推荐给其他项目
- 基于历史数据自动调整路线判断 (什么任务走 B 什么走 C)

---

## 六、可拓展性设计

> 核心设计目标: 同事只需要会写 Markdown，就能定制自己的开发流水线。

### 6.1 扩展点清单

```
同事可以改什么                          怎么改                           在哪里改
────────────────────────────  ─────────────────────────────  ──────────────────────────
① 某个阶段的执行逻辑           编辑/创建 SKILL.md              .claude/skills/{name}/SKILL.md
② 项目的门禁命令              编辑 YAML                      .claude/dev-config.yml
③ 跳过/增加 Pipeline 阶段      编辑 YAML routes 条目           .claude/dev-config.yml
④ 替换某阶段用的 Agent         编辑 Agent frontmatter          复制 agent → 修改 model/tools
⑤ 新增一个全新角色             写 profile + 一组 Skill         skill-map.yml + skills/
⑥ 调整自动化边界              编辑 YAML permissions           .claude/dev-config.yml
⑦ 接入新的 Wiki 平台          编辑 generic-wiki SKILL.md      添加新的优先级判断
⑧ 添加通知渠道                编辑 YAML notifications         .claude/dev-config.yml
```

### 6.2 三层隔离保证

```
改动范围        影响范围        回滚方式
──────────  ──────────────  ──────────────
L1 项目层    只影响当前项目   删除 .claude/skills/{name}/ 即可
L2 用户层    影响个人所有项目  删除 ~/.claude/skills/{name}/ 即可
L3 内置层    影响所有人       /plugin update dev-harness 回滚
```

同事在 L1 层怎么折腾都不会影响其他人，**这是三层解析最大的安全网**。

### 6.3 Skill 编写规范 (同事速查)

```markdown
一个好的 SKILL.md 必须包含:

1. frontmatter (3 行)
   ---
   name: 唯一名称
   description: 一句话。Use when: 触发条件。
   ---

2. 角色定义 (1 段)
   你是 [xxx]。你的职责是 [xxx]，不做 [xxx]。

3. 执行流程 (3-5 步)
   每步: 标题 + 具体命令/操作 + 预期产出

4. 产出定义 (1 段)
   保存到哪里，格式是什么

5. 约束 (3-5 条)
   不做什么、什么时候停下来、什么时候找人

一个好的 SKILL.md 不应该包含:
- Python/JS 代码（Skill 是指令，不是程序）
- 超过 200 行（太长会浪费上下文）
- 依赖外部工具安装（应在约束中声明依赖，降级处理）
```

### 6.4 dev-config.yml 完整参考

```yaml
# ==================== 项目配置模板 ====================
# 文件位置: .claude/dev-config.yml
# 所有字段都是可选的，有合理默认值

# ==================== 基础信息 ====================
project: my-project                    # 项目名（用于 HUD 和报告）
tech_stack: spring-boot                # 技术栈提示（可选，detect-stack.sh 会自动检测）

# ==================== 门禁命令 ====================
# 覆盖自动检测的构建/测试命令
gates:
  build: "./gradlew build -x test"     # 构建命令
  test: "./gradlew test"               # 测试命令
  lint: ""                             # 代码检查命令（可选）
  e2e: "bash scripts/e2e/run.sh"       # E2E 测试（可选）

# ==================== Skill 覆盖 ====================
# 指定某个阶段使用特定的 L1 Skill（跳过三层解析）
skill_overrides:
  audit: my-custom-audit               # audit 阶段用 .claude/skills/my-custom-audit/
  test: my-e2e-test                    # test 阶段用 .claude/skills/my-e2e-test/

# ==================== TDD 模式 ====================
tdd: false                             # true: implement 阶段强制先写测试

# ==================== 角色 Profile ====================
default_profile: backend               # 默认 /dev 使用的角色
# 可选: backend / frontend / product / qa / fullstack

# ==================== 自动化权限 ====================
permissions:
  auto_fix: true                       # 允许自动修复门禁失败
  auto_continue: true                  # 允许 Stop Hook 自动续跑
  max_auto_phases: 10                  # 最多自动续跑多少个 Phase
  max_duration: 7200                   # 最大运行时长（秒），默认 2h
  require_approval:                    # 需要人审批的阶段
    - prd
    - plan
  block_stages:                        # 完全禁用的阶段
    # - wiki                           # 取消注释则禁用 wiki 同步

# ==================== Wiki 同步 ====================
wiki:
  type: confluence                     # confluence / lark / none
  base_url: "http://wiki.example.com/confluence"
  space_key: MYPROJ
  # lark_token: "xxx"                  # 飞书 token（如果 type=lark）

# ==================== 通知 (v3.1) ====================
# notifications:
#   on_complete: [desktop]
#   on_failure: [desktop, lark]
#   lark_webhook: "https://open.feishu.cn/..."
```

### 6.5 同事接入流程 (SOP)

```
Step 1: 安装 (1 分钟)
  /plugin marketplace add https://github.com/brothelmdzz/dev-harness
  /plugin install dev-harness

Step 2: 验证 (1 分钟)
  输入 /dev，看到技术栈检测和 Skill 解析输出即成功

Step 3: 配置项目 (3 分钟)
  bash $DH_HOME/scripts/scaffold.sh --config springboot
  # 编辑 .claude/dev-config.yml 中的门禁命令

Step 4: 第一个任务 (5 分钟)
  /dev
  → 选择路线 C-lite (最简)
  → 看 Pipeline 自动跑完

Step 5 (可选): 写自定义 Skill
  bash $DH_HOME/scripts/scaffold.sh my-audit
  # 编辑 .claude/skills/my-audit/SKILL.md
  # 下次 /dev 时 audit 阶段自动使用你的 Skill (L1 优先级)
```

---

## 附录

### A. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/find-dh-home.sh` | 保留 | 一次性路径发现 |
| `scripts/worktree.sh` | **新增** | worktree 隔离 |
| `scripts/scaffold.sh` | **新增** | Skill 脚手架 |
| `scripts/skill-index.py` | **新增** | Skill 可视化索引 |
| `scripts/team-report.py` | **新增** | 团队看板导出 |
| `scripts/harness.py` | 修改 | 增加成本追踪、profile 支持 |
| `scripts/skill-resolver.py` | 修改 | 增加 profile 前缀解析 |
| `scripts/detect-stack.sh` | 修改 | 增加前端框架检测 |
| `hooks/stop-hook.py` | 修改 | 四道防循环防线 + rate limit |
| `hooks/statusline.js` | 修改 | 增加成本显示 |
| `skills/dev/SKILL.md` | 修改 | DH_HOME 变量 + profile + worktree |
| `skills/generic-*/SKILL.md` | 修改 | 路径引用统一用 $DH_HOME |
| `skills/generic-frontend-implement/` | **新增** | 前端实现 Skill |
| `skills/generic-frontend-research/` | **新增** | 前端研究 Skill |
| `skills/generic-product-prd/` | **新增** | 产品 PRD Skill |
| `skills/generic-tdd/` | **新增** | TDD 模式 Skill |
| `defaults/pipeline.yml` | 修改 | 增加 profiles 定义 |
| `defaults/skill-map.yml` | 修改 | 增加多角色映射 |
| `eval/eval-runner.py` | 修改 | 新增 3 维度 14 测试 |
| `templates/` | **新增** | 配置模板库 (5 个模板) |
| `docs/quickstart.md` | **新增** | 快速上手教程 |
| `docs/contributing.md` | **新增** | 贡献指南 |
| `docs/improvement-plan-v3.md` | **新增** | 本文档 |
| `README.md` | 修改 | 更新功能列表和竞品对比 |

### B. 竞品关键差异总结

```
Dev Harness 独有:
  ✓ 三层 Skill 解析 (L1>L2>L3)
  ✓ YAML Pipeline 可配置 + 路线分级
  ✓ 内置评测框架 (加权评分)
  ✓ Rich HUD + Statusline 双层可观测
  ✓ 三路代码审查 (Codex×2 + Claude)

Superpowers 独有:
  ✓ TDD 强制 (RED-GREEN-REFACTOR)
  ✓ Git Worktree 隔离
  ✓ Socratic Brainstorming 方法论
  ✓ 跨平台 (Codex + OpenCode)
  ✓ 93k stars 社区

OMC 独有:
  ✓ tmux 5-worker 并行 (Ultrapilot)
  ✓ 32 agents 多角色覆盖
  ✓ 5 种执行模式
  ✓ Rate limit 自动恢复

DeerFlow 独有:
  ✓ Docker 容器隔离
  ✓ 模型无关 (任何 LLM)
  ✓ 长时任务 (分钟到小时级)
  ✓ 字节跳动背书
```

### C. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| 同事不愿学新工具 | 高 | 推广失败 | scaffold + 模板 降低学习成本到 10min |
| Stop Hook 仍有死循环 | 中 | 浪费 token + 代码被搞乱 | 四道防线 + worktree 隔离 |
| Skill 质量参差不齐 | 高 | 体验不一致 | eval 测试 + 编写规范 + 代码审查 |
| Claude Code API 变更 | 低 | Hook/Statusline 失效 | 抽象层隔离 + 版本锁定 |
| 竞品快速迭代追平 | 中 | 差异化消失 | 深耕三层解析 + 企业治理（竞品不关注） |
