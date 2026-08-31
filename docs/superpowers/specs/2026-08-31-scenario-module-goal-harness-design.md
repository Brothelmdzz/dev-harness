# Dev Harness v5：场景纵向交付、模块横向收敛与原生 Goal 协作设计

> 状态：`REVIEW_READY · IMPLEMENTATION_NOT_STARTED`
>
> 日期：2026-08-31
>
> 目标分支：`codex/v5-scenario-module-harness`（基于 `dev@a238387`）

## 1. 设计结论

Dev Harness v5 的用户工作模型从“按 research、prd、plan、implement、test、review 阶段推进”改为：

```text
一次架构确认
  → 场景纵向交付
  → 人工集中验收
  → 模块横向收敛
  → 多项目证据充分后组件化
```

Pipeline、Review、测试和 Loop 仍然存在，但降为 Agent 内部执行机制。用户每次只需要把注意力放在一个具体对象上：架构、场景、验收或模块逻辑。

原生 Goal 负责长任务跨 turn 持续执行；Dev Harness 负责目标内的工程契约、验证证据和人工 Gate；Loop Engine 只负责当前 ChangeSet 内部的确定性反馈循环，不承担 Goal 的暂停、恢复或长期续跑职责。

## 2. 要解决的问题

当前 Dev Harness 的阶段化工作流存在四个结构性问题：

1. PRD 和 Plan 都可能要求多轮人工确认，但确认对象主要是文档和 Phase，不是可直接操作的业务场景。
2. 人工确认不能证明实现没有 Bug，后续修改也没有把已验收行为稳定地转化成回归边界。
3. 验证范围由模型临场判断时，模型容易把“谨慎”等同于“重复跑全量测试”，即使只改一行也消耗大量时间。
4. 状态、配置、日志和 Skill 路径大量绑定 `.claude/`，不适合作为同时服务 Claude Code、Codex 和 Cursor 的插件内核。

v5 的目标不是增加更多阶段，而是改变一级交付对象、压缩人工打断、让验证与影响范围绑定，并将宿主能力与插件工程契约分层。

## 3. 核心原则

### 3.1 场景是主要交付单位

场景描述一个用户可以从头到尾操作和观察的结果。每个场景必须有前置条件、操作步骤、预期结果、异常出口、涉及模块、自动验证范围和预计人工验收时间。

一个场景批次的人工验收时间应控制在约 40–60 分钟。Agent 在批次内连续执行，不在场景之间询问“是否继续”。

### 3.2 模块是横向收敛单位

场景开发只补齐当前场景需要的最小模块能力，不顺手进行无关的大重构。多个已完成场景暴露重复逻辑、职责混乱或边界问题后，创建独立的 `module_refactor` ChangeSet。

模块重构不增加业务行为。完成标准是公共契约保持不变，并且所有关联场景继续通过。若必须修改公共契约，则转换为架构变更并请求人工确认。

### 3.3 人确认稳定边界，不冻结内部实现

初始架构确认锁定系统边界、模块职责、依赖方向、公共契约和关键非功能红线。函数实现、命名和模块内部结构可以由 Agent 自主演进。

只有改变模块职责、公共契约、依赖方向、数据语义或已验收用户行为时，才重新触发架构确认。

### 3.4 验收行为成为长期回归契约

场景通过人工验收后进入 `ACCEPTED`。后续发现 Bug 时进入 `REOPENED`，先固化失败案例，再执行最小修复和受影响范围验证。内部实现变化不要求重新验收；用户可观察行为变化才要求重新确认。

### 3.5 原生 Goal 管长期执行

Dev Harness 不重复实现宿主已经提供的长任务续跑、暂停和恢复能力。一个 Goal 对应一个稳定目标，通常是一批约一小时可验收的场景、一个模块重构、一次架构基线建立或一次已批准的架构变更。

Goal 的停止条件必须到达人类下一步可以接手的边界，例如 `READY_FOR_ACCEPTANCE`，而不是让 Agent 代替用户宣布 `ACCEPTED`。

## 4. 双轴工作模型

### 4.1 初始横向架构

项目或重大里程碑开始时，Agent 先整理：

- 系统上下文和外部依赖；
- 模块清单、职责和依赖方向；
- 公共契约与架构红线；
- 已知场景目录；
- 首批准备开发场景的详细验收手册。

用户集中确认一次架构基线和首批场景边界。后续在基线内的场景不再重复进行 PRD/Plan 审批。

### 4.2 纵向场景开发

```text
读取架构基线和场景手册
  → 确定涉及模块与最小能力
  → 实现一个端到端场景
  → 执行影响范围验证
  → 生成可操作验收包
  → READY_FOR_ACCEPTANCE
```

场景任务禁止混入不阻塞当前场景的横向大重构。发现的横向问题记录到模块收敛候选，不改变当前 ChangeSet 的目标。

### 4.3 横向模块收敛

```text
读取模块契约和关联场景
  → 明确本轮不新增业务行为
  → 消除重复、收敛职责和内部接口
  → 执行模块契约与关联场景回归
  → COMPLETE 或 NEEDS_ARCHITECTURE_APPROVAL
```

### 4.4 跨项目组件化

模块只有在多个独立场景乃至多个项目中出现稳定、可参数化的共同语义，并具备真实样本、回归证据、版本与回滚边界后，才考虑提取为组件或产品。v5 只保留关系数据和扩展点，不自动完成跨项目提取。

## 5. 项目设计 SSOT

长期项目事实放在可读、可版本控制的文档中：

```text
docs/dev-harness/
├─ architecture.md       # 架构基线与模块地图
├─ scenarios.yml         # 场景目录、优先级、状态和验收时长
├─ scenarios/
│  └─ S-xxx-*.md         # 准备开发或已交付场景的详细验收手册
└─ decisions/            # 重大架构变更记录
```

### 5.1 架构基线

`architecture.md` 至少包含：

- 系统边界和外部依赖；
- 模块职责和依赖方向；
- 稳定公共契约；
- 数据、安全、性能等红线；
- 触发重新确认的变化类型；
- 基线版本号。

初始阶段不为每个模块创建空洞的完整设计文档。只有模块形成公共契约或进入独立重构时，才增加详细模块说明。

### 5.2 场景目录

先枚举全部已知场景的粗粒度信息，只对当前开发批次展开详细手册。目录至少包含场景 ID、用户目标、涉及模块、优先级、状态和预计验收时间。

### 5.3 场景验收手册

详细手册必须在实现前完成，至少包含：

- 使用者与目标；
- 前置条件、环境、账号和样本数据；
- 人工操作步骤；
- 每一步可观察的预期结果；
- 异常路径和失败出口；
- 涉及模块；
- 验证等级和命令映射；
- 预计人工验收时间；
- 实现证据与最终验收结果。

场景状态：

```text
PROPOSED
  → READY
  → IMPLEMENTED
  → READY_FOR_ACCEPTANCE
  → ACCEPTED
  → REOPENED
  → READY_FOR_REACCEPTANCE
```

聊天记录和运行状态不得覆盖设计 SSOT。

## 6. 宿主中立目录

插件核心数据不再写死在 `.claude/`：

```text
.dev-harness/
├─ config.yml                  # 提交：宿主中立项目配置
├─ skills/                     # 提交：跨宿主项目 Skill
├─ state.json                  # 忽略：当前运行状态
├─ verification-ledger.jsonl   # 忽略：验证指纹和证据索引
├─ workers/                    # 忽略：并行工作状态
├─ logs/                       # 忽略：完整执行与测试日志
└─ cache/                      # 忽略：可重建的影响关系缓存
```

用户级项目注册表迁移为 `~/.dev-harness/sessions.json`。

`.claude/`、`.codex/`、`.cursor/` 和插件 manifest 目录只承担各宿主要求的命令、Hook、manifest、原生 Skill 或设置适配。核心状态路径、ChangeSet 语义和项目 SSOT 不因宿主变化而变化。

## 7. ChangeSet 模型

`/dev` 保持为唯一主入口，通过自然语言和项目状态识别四种 ChangeSet：

| 类型 | 目标 | 默认人工 Gate |
|---|---|---|
| `architecture` | 建立架构基线、模块地图和场景目录 | `READY_FOR_ARCHITECTURE_APPROVAL` |
| `scenario` | 纵向交付一个或一批场景 | `READY_FOR_ACCEPTANCE` |
| `module_refactor` | 在行为不变前提下横向收敛模块 | 无；契约变化时升级 |
| `fix` | 修复 `REOPENED` 场景或局部缺陷 | `READY_FOR_REACCEPTANCE` 或 `COMPLETE` |

运行状态示例：

```yaml
change:
  id: CHG-20260831-001
  kind: scenario
  scenarios: [S-012, S-013, S-014]
  modules: [M-auth, M-message]
  architecture_baseline: v3
  verification_tier: V2
  status: READY_FOR_ACCEPTANCE
```

现有 research、prd、plan、implement、test 和 review 降为 ChangeSet 内部活动。处于已批准架构基线内的场景 Plan 自动继续，不再默认执行 2–4 轮人工确认。

## 8. 原生 Goal、Dev Harness 与 Loop Engine

### 8.1 三层职责

```text
原生 Goal
  └─ 稳定目标、跨 turn 持续执行、暂停/恢复和完成判断

Dev Harness ChangeSet
  └─ 工程范围、场景/模块契约、验证证据和人工 Gate

Loop Engine
  └─ 当前 ChangeSet 内的 next → execute → report → evaluate 反馈循环
```

用户明确使用 Goal 时，Dev Harness 为当前宿主生成并绑定 Goal Contract；检测到已有 Goal 时，不再创建第二个长期任务；没有 Goal 时，普通 `/dev` 仍可运行，也不自行模拟 Goal。

Goal Contract 至少包含唯一目标、范围、排除项、必须先读的 SSOT、验证范围、架构暂停条件和可验证停止条件。

### 8.2 Loop Engine 定位

Loop Engine 不负责防止模型停止，也不替代 Goal。它只提供确定性工程接口：

```text
harness next
harness report
harness evaluate
harness status
harness status --json
```

四类 ChangeSet 对应 `architecture.yml`、`scenario.yml`、`module-refactor.yml` 和 `fix.yml` 剧本。剧本描述循环形状、允许的状态转换和退出条件，不写死模型名或具体测试命令。

保留现有 v5 Loop Engine 方案中的契约解释、预算、上下文卫生、风险 Review lane、Fix 剧本和 Pitfall Journal；调整为 ChangeSet/场景预算，并去掉与 Claude Stop Hook 的核心绑定。

Claude Stop Hook 只作为可选宿主兼容层，不再承担核心编排和强制续跑。Codex、Claude Code 和 Cursor 适配器都调用同一个宿主中立内核。

## 9. 影响驱动验证

验证决策由 Harness 根据显式的“文件/模块/场景/命令”关系确定，不交给模型临场扩大范围。

| 级别 | 适用变化 | 必须执行 |
|---|---|---|
| V0 | 文档、注释、非运行时文本 | diff/格式检查，不跑测试 |
| V1 | 模块内部小改动且契约不变 | 相关文件或最小单元测试 |
| V2 | 一个纵向场景的行为变化 | 当前场景测试与最短验收路径 |
| V3 | 模块重构或公共接口变化 | 模块契约测试与全部关联场景 |
| V4 | 架构、认证、迁移、共享基础设施或发布 | 全量门禁，在出口执行一次 |

规则：

1. 按影响范围判断，不按改动行数判断。
2. 首版影响图由场景和模块显式声明，不实现复杂静态分析器。
3. `verification-ledger.jsonl` 保存命令、输入指纹、影响集合、结果和时间。
4. 同一验证命令在相关输入最后一次变化后已经通过时，直接复用证据。
5. 从 V1/V2 升级到 V3/V4 必须记录公共契约变化、未知影响关系或定向验证暴露跨模块问题等原因。
6. 全量测试不再是每个阶段的固定出口。
7. 完整日志落文件，对话只注入摘要。

## 10. 人工打断和错误处理

Agent 不因实现不确定、单次测试失败、中间进度汇报或场景批次切换而打断用户。只有以下状态允许暂停：

| 状态 | 条件 |
|---|---|
| `NEEDS_ARCHITECTURE_APPROVAL` | 修改职责、契约、依赖、数据语义或已验收行为 |
| `READY_FOR_ACCEPTANCE` | 场景批次具备环境、手册和自动验证证据 |
| `NEEDS_EXTERNAL_ACTION_APPROVAL` | 推送、生产部署、迁移、删除、凭证或其他外部副作用 |
| `BLOCKED` | 至少三种不同方案仍被同一结构性条件阻断 |

外部副作用授权独立于设计批准和 Goal 授权。Goal 不得扩大原始权限范围。

Bug 重开流程：

```text
ACCEPTED
  → REOPENED
  → 固化失败案例
  → 最小修复
  → V1/V2 影响范围验证
  → READY_FOR_REACCEPTANCE
```

若 Bug 暴露架构或契约错误，则升级为 `NEEDS_ARCHITECTURE_APPROVAL`。

## 11. 可观测性与 Web HUD 退出

正式可观测性收敛为：

1. 原生 Goal UI：展示长期任务运行、暂停和完成状态；
2. `harness status`：展示当前场景、模块、检查点、验证结果和人工 Gate；
3. 项目 SSOT：保存架构、场景、验收与变更的长期事实。

`harness status --json` 提供机器可读输出，详细日志保存在 `.dev-harness/logs/`。

v5 不重写 Web HUD，也不接入新的 Goal/ChangeSet/场景状态。旧实现可保留一个迁移版本作为 legacy，但不再增加字段、SSE、兼容逻辑或验收要求。后续版本删除 Web 服务、多项目发现、前端页面和相关维护代码。

## 12. 兼容与迁移

v5 保留一个迁移周期：

- 旧 `/dev`、`/fix`、`/test` 和 `/review` 命令继续可用；
- 旧 Pipeline 作为 `legacy-pipeline` 剧本运行；
- 新 `.dev-harness/` 优先；
- 新目录不存在时识别旧 `.claude/harness-state.json`、`dev-config.yml`、plans 和 logs；
- `setup --migrate` 原子复制并验证，旧文件保留为历史备份；
- 迁移完成后只写新目录，禁止双写；
- 新旧状态冲突时，以项目 SSOT和新 `.dev-harness/` 为准；
- `.claude/skills` 继续作为 Claude 宿主层，`.dev-harness/skills` 承担跨宿主 Skill；
- Codex、Claude Code 和 Cursor 的 manifest 版本与能力描述必须机械同步；
- 最早到 v6 才删除 legacy Pipeline 和旧路径读取。

## 13. v5 第一版交付切片

v5 用自身倡导的纵向方式实现：

| 场景 | 交付结果 | 人工验收重点 |
|---|---|---|
| S1 宿主中立初始化 | 创建新目录、识别宿主、完成单向迁移 | CC/Codex 看到同一项目事实 |
| S2 架构与场景设计 | 生成基线、模块地图、场景目录和首批手册 | 文档可确认、手册可操作 |
| S3 场景纵向开发 | `/dev` 连续开发场景批次至验收边界 | 不反复确认，可集中验收 |
| S4 模块横向重构 | 按关联场景收敛模块，契约变化才暂停 | 行为不变、逻辑收敛 |
| S5 Goal 与验证集成 | 原生 Goal + V0–V4 + 证据复用 | 不重复造续跑，不重复全量验证 |

每个切片独立完成设计、实现、定向验证和人工验收，不在同一交付中同时重写所有模块。

## 14. 第一版明确不做

- 自动把跨项目模块发布成组件产品；
- 自动发现多个项目之间的重复能力；
- 复杂的静态代码影响分析；
- Web HUD 重写或新状态适配；
- 新的多 Agent 编排系统；
- Success Pattern 自动学习；
- 生产部署自动化；
- 用 Loop Engine 替代原生 Goal；
- 为了兼容旧版长期双写两套状态。

## 15. 验收策略

### 15.1 确定性测试

至少覆盖：

- 文档单行变化选择 V0 且不执行测试；
- 模块内部函数变化选择 V1；
- 场景行为变化选择 V2；
- 公共契约变化触发架构 Gate；
- 相关输入未变化时复用已经通过的命令证据；
- 场景批次中间不请求继续；
- 场景 Goal 停在 `READY_FOR_ACCEPTANCE`；
- `ACCEPTED` 场景发现 Bug 后进入 `REOPENED`；
- 旧 `.claude` 项目完成单向迁移；
- 新旧状态冲突时项目 SSOT获胜；
- 外部副作用没有授权时必须暂停。

### 15.2 Skill 行为回归

新增行为场景，专门诱发并禁止以下失败模式：

- 改一行后主动运行全部测试；
- 已有 PASS 证据仍重复执行同一命令；
- 在场景之间询问用户是否继续；
- 把模块内部实现选择升级为人工决策；
- 在 Goal 中混入无关 backlog；
- 将自动验证通过误报为人工验收通过；
- 读取过期 harness state 覆盖设计 SSOT。

### 15.3 双宿主真实验收

同一个 fixture 项目分别由当前 Codex 和 Claude Code 执行：

1. 初始化架构和场景；
2. 启动一个原生 Goal；
3. 完成一个场景批次；
4. 产生相同的 `.dev-harness` 状态和项目 SSOT；
5. 在 `READY_FOR_ACCEPTANCE` 停止；
6. 验证另一个宿主可以从相同项目事实继续。

宿主 Goal API、命令和状态表现允许不同，但项目契约和完成语义必须一致。

## 16. 风险与控制

| 风险 | 控制 |
|---|---|
| 场景优先退化为一次性补丁 | 架构基线、模块契约和独立模块收敛任务 |
| 模块重构混入新功能 | ChangeSet 类型隔离，关联场景行为不变门禁 |
| 显式影响图漏标 | 契约变化升级 V3/V4；发布出口保留一次 V4 |
| 模型过度验证 | Harness 选择命令、验证指纹复用、升级必须记录理由 |
| Goal 变成无限 backlog | 一个稳定目标、明确排除项和可验证停止条件 |
| 宿主能力差异污染核心 | Goal/Hook/manifest 仅在 adapter 层，核心状态宿主中立 |
| 新旧状态分叉 | 单向迁移、禁止双写、SSOT 优先 |
| 文档数量失控 | 全场景粗目录，只有当前批次展开详细手册 |
| Web HUD 形成迁移负担 | 冻结 legacy，不接入新模型，后续删除 |

## 17. v5 设计完成标准

实施计划只有在以下设计条件全部满足后才能开始：

- 本规格经用户确认；
- 场景、模块、ChangeSet、Goal 和 Loop 的职责不存在重叠；
- 人工 Gate 和外部授权边界明确；
- `.dev-harness` 与项目 SSOT 路径明确；
- V0–V4 选择和证据复用规则明确；
- 旧路径单向迁移和 legacy 生命周期明确；
- Web HUD 不进入新架构；
- 第一版非目标明确，能够拆成独立验收切片。

本规格确认后，下一步是为五个交付切片编写依赖明确、可逐场景验收的实施计划。规格确认本身不授权 push、PR、远端发布、生产动作或删除 legacy 资产。
