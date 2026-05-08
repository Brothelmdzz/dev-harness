# dev-harness 设计哲学 (Design Philosophy)

> **本文档的角色**：长期 north star。任何后续设计决策都可引用它做论证或反驳。
> **不在此范围**：具体落地实操（→ `external-references-2026-05.md`）、版本路线图（→ `roadmap-v4.md`）、当前任务（→ `SESSION-HANDOFF.md`）。
> **修订频率**：大版本（v4→v5）一次；或 Anthropic/OpenAI 发布新 harness 论文；或我们某次架构决策反驳了某条原则。
> **首次落地**：2026-05-08。

---

## 一、本文档的定位

哲学文档 vs 落地参考的分工：

| 类型 | 来源 | 性质 | 寿命 |
|------|------|------|------|
| **哲学**（本文） | Anthropic 工程博客 + OpenAI Codex 博客 + 我的长期想法 | 长期、不易过时、不可妥协 | 多年 |
| **参考** (`external-references-2026-05.md`) | 国内大厂（得物/腾讯/阿里）实践文章 | 短期、随产品迭代过期 | 6-18 个月 |

所有外部素材在 `.design/`：
- `.design/deep-research-harness-engineering-2026.md` — 自做的深度调研
- `.design/openai-harness-eng-zh.txt`、`.design/openai-unrolling-zh.txt`、`.design/openai-unlocking-zh-raw.txt` — OpenAI 三篇官方简体中文版

---

## 二、核心命题：什么是 Harness

合成定义（取自 Anthropic + OpenAI）：

> **Harness = 包裹模型的运行时框架。它由编排层（agent loop / pipeline）、上下文层（rules / skills / docs）、工具层（ACI）、反馈层（evals / pitfall）组成；每个组件都编码了一条「模型自己做不到什么」的假设，能力进步就要重审。**

两边的原话：

| 来源 | 原话 |
|------|------|
| Anthropic ([effective-harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)) | "Agent scaffolding as load-bearing infrastructure that compensates for model limitations while remaining adaptable as capabilities improve." |
| OpenAI ([harness-engineering](https://openai.com/index/harness-engineering/)) | "It provides the core agent loop and execution logic, the foundation of all Codex experiences." |
| OpenAI 同上 | **"Humans steer. Agents execute."** |

**dev-harness 的产品定位**：把上面这套抽象在 Claude Code 上落地为可复用插件——通过 `/dev` 把 research/plan/implement/review 串成可观测可中断的流水线。

---

## 三、八大原则（按重要性降序）

每条原则的结构：核心命题 → 出处与原话 → 对 dev-harness 的指导 → 反例 / 红线。

### 原则 1：Harness 是承重脚手架，不是装饰

**核心**：每个组件都必须能回答「它补偿了模型的什么缺口」。否则就是技术债。

**出处**：
> "Every component in a harness encodes an assumption about what the model can't do on its own, and those assumptions are worth stress testing." — Anthropic, *Harness design for long-running application development* (2026-03-24)

**对 dev-harness 的指导**：
- 新增 hook / skill / rule 时，PR 描述必须显式回答"补偿了什么缺口"
- 不允许"为了看起来工程化"而加的中间层
- 模型升级（Sonnet 4.6 → Opus 4.7 → Claude N+1）后必须重审现有脚手架，看哪些假设已失效

**反例**：dev-harness 当前 12 个 agent 全部 opus 模型——这是不是给"模型不会路由"打了脚手架？随着模型自带工具选择能力，可能要拆。

---

### 原则 2：Humans Steer, Agents Execute

**核心**：人写规范、人定方向；agent 写代码、agent 执行验证。**不是反过来**。

**出处**：
> "Humans steer. Agents execute. The primary work of software engineering teams is no longer writing code, but designing environments, clarifying intent, and constructing feedback loops." — OpenAI, *Harness Engineering* (2026-02-11)

**对 dev-harness 的指导**：
- `/dev` 入口必须收紧 **意图捕获**（research → prd → plan 三阶段是为了反复确认意图，不是流程繁琐）
- `harness.py` 的状态机不应该让 agent 自己跳阶段——agent 只能 `update`，不能 `init`
- 用户决策点（如"是否进入 audit"）必须显式暴露，不能默默推进

**反例 / 红线**：任何让"用户开口才能继续"的环节被自动化绕过——是危险信号。

---

### 原则 3：Context is Scarce, Disclose Progressively

**核心**：上下文是稀缺资源；用渐进披露而非堆砌。

**出处**：
> "Anything an agent cannot access in context at runtime simply does not exist." — OpenAI, *Harness Engineering*

> "Give Codex a map, not a 1,000-page manual. ... When everything is 'important', nothing is." — OpenAI, 同上

> "JSON 优于 Markdown 作为状态文件——模型不会随便覆写 JSON，符合防呆原则。" — Anthropic, *Effective harnesses* (2025-11-26)

**对 dev-harness 的指导**：
- SKILL.md 不超过 200 行；超过则拆 `references/` 按需加载（这是 v3.5 已落地的"渐进披露"，必须保持）
- AGENTS.md / CLAUDE.md 是**目录**，不是百科——指向 `docs/internal/`、`templates/`、`agents/` 等子目录
- 状态文件（harness-state.json）保持 JSON；防止模型乱改的关键字段加 `# DO NOT EDIT` 注释 + JSON Schema 校验

**反例 / 红线**：任何把"全部规范一次性塞进 system prompt"的做法 = 上下文污染。

---

### 原则 4：Repository as System of Record（ALL In Code）

**核心**：代码仓库是唯一权威源。需求、规范、测试、文档、agent 用的 skills/handbooks——全部进 git。

**出处**：
> "Repository as system of record. Anything an agent needs must live in versioned artifacts." — OpenAI, *Harness Engineering*

> "代码库就是唯一的事实来源，一切需求从代码开始，也在代码中结束，形成闭环。" — 阿里 ·向邦宇, *Agent 时代的生产力悖论* (2026-05-08)

> （这与我自己的长期想法一致——这是设计哲学之一）

**对 dev-harness 的指导**：
- `templates/` 必须提供完整的"ALL In Code 项目骨架"——`.claude/skills/` + `.claude/handbooks/` + `.claude/runbooks/` + `.claude/rules/` + `docs/release-notes/`
- 反对把 PRD/wiki/钉钉文档作为权威源；如果存在外部文档，必须有同步机制把它落到仓库
- 模型版本、prompt 版本、外部 API schema 全部锁定到仓库

**反例 / 红线**：任何让"agent 必须连外部系统才能工作"的设计——必须改造为先把外部数据快照到仓库再用。

---

### 原则 5：Stage Fusion — 反对中心化协调

**核心**：长期看，Coding / CI / CR / CD 应该融合，不是串联。Code Review 应该内嵌到 Coding 而不是独立阶段。

**出处**：
> "我们尝试将许多过程合并为一个连续的阶段——例如在 Coding 阶段就同步完成 Code Review，在 Coding 阶段就同步完成 CI 检查，从而彻底摒弃中心化的 Code Review 系统，将 Code Review 从传统的『以人为主导』的模式，转变为『以 Agent 为主导』的模式。" — 阿里 ·向邦宇, 同上

> （这是我的设计哲学之一——长期方向）

**对 dev-harness 的当前张力**：
- 现状：`pipeline.yml` 把 review 设为独立 stage——这是"按工种切片"的延续
- 长期目标：review 融入 implement 的每个 phase
- 过渡形态（v4）：保留 review stage 做汇总，但 implement 内每 phase 完成后**立即**做轻量异构对抗 CR

**红线**：任何"新增独立 stage"的提议必须先证明"无法融入 implement"——否则不进。pipeline 的 stage 数量上限 = 7。

---

### 原则 6：Generator-Evaluator Separation

**核心**：生产与评判由不同 agent 承担，避免自评偏差。

**出处**：
> "Generator-Evaluator Pattern, inspired by GANs. ... When the same agent generates and judges, you get an inflation bias. Sprint Contracts: implementation の前に generator と evaluator が『完成』の可測定義を交渉する。" — Anthropic, *Harness design for long-running applications* (2026-03-24)

**对 dev-harness 的指导**：
- `generic-review` 已经做到了角色分离（code-reviewer / security-reviewer / architect 三路）
- 但**模型层面还是同一个 Claude**——这是 v4 要补的
- `generic-implement` 内嵌 CR 时，CR agent 必须独立 spawn，不能让 implement agent 自己 review

**反例**：`generic-implement` 完成后让自己跑一遍 review prompt = 严重违反。

---

### 原则 7：Multi-Model Adversarial > Single-Model Self-Reflection

**核心**：多模型异构对抗 + 交叉投票，胜过单模型自反思。

**出处**：
> "3 模型并行独立审查 → 交叉验证（≥2 模型命中=高置信）→ 辩论式讨论 → 全员无新发现自动收敛。解决单模型的『知识盲区 / 注意力盲区 / 确认偏差』。" — 腾讯·LEGO 团队, *Harness Engineering：AI 能在真正"出事会炸"的后端系统里写代码吗？* (2026-04-21)

> （Anthropic / OpenAI 没有直接对应观点——这条是国内补强）

**对 dev-harness 的指导**：
- v4 把 `generic-review` 三路 agent 绑定到不同模型族（Opus / Sonnet / Haiku，或跨厂商 Claude / GPT / Gemini）
- 投票汇总逻辑：≥2 模型命中 = 高置信问题，必须修；只有 1 模型命中 = 标注待人决
- `agents/code-reviewer.md`、`agents/security-reviewer.md`、`agents/architect.md` 各加 `model:` 字段差异化

**反例**：所有审查 agent 都用 opus = 浪费且自评偏差风险。

---

### 原则 8：Harness Moves, Doesn't Shrink

**核心**：模型变强，脚手架不会消失，会向上迁移。dev-harness 的设计必须假设"未来的模型更强"。

**出处**：
> "The space of interesting harness combinations doesn't shrink as models improve. Instead, it moves." — Anthropic, *Harness design* (2026-03-24)

> "Opus 4.6 demonstrated sufficient planning capability to sustain agentic tasks without sprint decomposition that Opus 4.5 required." — Anthropic, 同上

**对 dev-harness 的指导**：
- 每条 rule / skill / hook 必须**版本化**：标注它针对的模型能力上限（如 `model_context: opus-4.6+`）
- 模型升级后跑回归评测（`eval-runner.py`）：哪些组件让 pass_rate 反而下降？候选淘汰
- 不要把 v3 的脚手架当作"永恒资产"——它们是当前模型缺口的临时支架

**反例**：`stop-hook.py` 26.3K 行的"六道防线"——其中有几道在 Claude 4.7 时代已经不需要了？需要 A/B 验证。

---

## 四、架构红线（不可妥协，可机械验证）

每条违反 = PR 自动 reject。

| # | 红线 | 校验方式 |
|---|------|---------|
| 1 | 新功能 PR 必须有"补偿什么缺口"段落 | PR 模板强制 |
| 2 | Agent 写盘产物必须 git-tracked，JSON 优于 Markdown | `.claude/` 内文件 lint |
| 3 | 外部依赖必须版本化锁定（含模型版本） | `dev-config.yml` schema 校验 |
| 4 | SKILL.md 不超过 200 行 | `eval-runner.py --check-skills` |
| 5 | 任何 hook 必须有超时 + 降级路径 | `hooks.json` schema 校验 |
| 6 | Code Review 必须 ≥2 路异构模型 | `generic-review` 内 assert |
| 7 | 任何变更必须有可回滚边界 | ChangeSet 字段校验（v4 引入） |
| 8 | pipeline 的 stage 数量 ≤ 7 | `pipeline.yml` schema |
| 9 | SKILL/Agent prompt 中禁止依赖外部 URL（除非缓存到仓库） | grep 校验 |

---

## 五、当前状态评估（dev-harness v3.5 vs 哲学）

| 原则 | 状态 | 缺口 |
|------|------|------|
| 1 承重脚手架 | ⚠️ 部分 | 12 个 agent 全 opus 缺论证；stop-hook 六道防线缺 A/B |
| 2 Humans Steer | ✅ 符合 | `/dev` 三阶段意图捕获、用户决策点显式 |
| 3 Context Scarce | ✅ 符合 | 三层 Skill 解析 + SKILL.md 200 行限制（v3.5） |
| 4 ALL In Code | ⚠️ 部分 | `templates/` 还没有完整骨架；handbook/runbook 缺位 |
| 5 Stage Fusion | ❌ 违反 | review/audit/test 都是独立 stage；这是 v4 主战场 |
| 6 Generator-Evaluator | ✅ 符合 | `generic-review` 已分角色 |
| 7 Multi-Model Adversarial | ❌ 缺失 | 全 opus 同模型；v4 必补 |
| 8 Harness Moves | ⚠️ 部分 | rule/skill 没有 model 版本标签；模型升级无 A/B |

---

## 六、长期 North Star（3-5 年后的样子，不是 roadmap）

不承诺时间，只描述终态：

1. **没有独立 review 阶段**——融入 implement 每个 phase（原则 5）
2. **ChangeSet 作为一级原语**——替代当前的 `harness-state.json` session 级状态（阿里方向）
3. **Agentic IAM 集成**——agent 有自己的身份和权限（阿里方向）
4. **多模型异构默认开启**——`generic-review` 自动选择最异构的 3 个可用模型（原则 7）
5. **项目骨架自带 ALL In Code 三层目录**——`/dev init` 一键生成（原则 4）
6. **Pitfall Journal 闭环**——失败自动入库，3 条同类自动追加 rule（腾讯 3）
7. **Sprint Contracts**——implement 前 generator/evaluator 协商可测完成定义（Anthropic 方向）
8. **Cache Hits Are Sacred**——pipeline 切换 model/tools 不击穿 prefix cache（OpenAI 方向）

---

## 七、决策框架：当某个新需求来了，先问

按顺序自检（任一项 ❌ 则需要重新设计）：

1. 它对应原则 1-8 中哪几条？
2. 它违反了红线 1-9 中哪几条？
3. 它是补偿了"模型当前的什么缺口"？
4. 当模型升级一档，它会变成累赘吗？如果会，标注 `deprecation_trigger: model >= X`
5. 它把决策权放给了 agent 还是人？（原则 2）
6. 它是把数据搬进仓库还是搬出仓库？（原则 4）

---

## 八、版本与维护

| 字段 | 值 |
|------|---|
| 版本 | v1.0 |
| 首次落地 | 2026-05-08 |
| 主要作者 | dev-harness 团队 |
| 引证来源 | Anthropic ×3 + OpenAI ×3 + 国内 ×5（详见 `external-references-2026-05.md`）+ 用户长期想法 |
| 修订触发 | 大版本 / 新 harness 论文 / 重大架构决策反驳 |
| 修订禁止 | "我现在觉得"的 ad-hoc 修订 |

---

## 九、引证清单

### Anthropic 工程博客
1. [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — 2025-11-26, Justin Young
2. [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) — 2026-03-24, Prithvi Rajasekaran
3. [Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents) — 2024-12-20, Erik Schluntz / Barry Zhang

### OpenAI 工程博客
4. [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) — 2026-02-11, Ryan Lopopolo
5. [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/) — 2026-01-23, Michael Bolin
6. [Unlocking the Codex harness: how we built the App Server](https://openai.com/index/unlocking-the-codex-harness/) — 2026-02-04, Celia Chen

### 国内大厂参考（详见 external-references-2026-05.md）
7. 得物·阳凯, *AI 编程能力边界探索：基于 Claude Code 的 Spec Coding 项目实战* (2026-03-11)
8. 得物·盖伦, *基于 Harness + SDD + 多仓管理模式的 AI 全栈开发实践* (2026-05-06)
9. 腾讯·LEGO, *Harness Engineering：AI 能在真正"出事会炸"的后端系统里写代码吗？* (2026-04-21)
10. 腾讯·审核业务, *从提需求到部署发布，全 AI 全自动化后，研发效能全面跃升* (2026-04-20)
11. 阿里·向邦宇, *Agent 时代的生产力悖论：当协作本身成为最大的瓶颈* (2026-05-08)
