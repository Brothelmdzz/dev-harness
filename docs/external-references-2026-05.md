# 外部参考文献（2026-05）

> **本文档的角色**：5 篇国内大厂 AI Coding 实践文章的精华汇总，作为 dev-harness 短期 P0/P1 决策的论据来源、培训材料、对外定位话术。
> **不在此范围**：长期哲学（→ `design-philosophy.md`）、版本路线图（→ `roadmap-v4.md`）。
> **首次落地**：2026-05-08。

---

## 一、索引矩阵

| # | 出品 | 标题（简称） | 时间 | 核心命题 | 关键产物 |
|---|------|-------------|------|---------|---------|
| 1 | 得物·阳凯 | *Spec Coding 实战* | 2026-03-11 | 三层规范体系消除 AI 不确定性 | `.claude/{rules, code-design, ui-design}` 三层目录 |
| 2 | 得物·盖伦 | *Harness + SDD + 多仓全栈* | 2026-05-06 | Harness 思维 + 双 SDD + 多 Agent 并行 | 前后端 contract 对齐、Cursor Composer2 vs CC Subagent/Team |
| 3 | 腾讯·LEGO | *Harness Engineering* | 2026-04-21 | 工程体系比模型更重要，多模型对抗 CR | 五层架构、Pitfall Journal、3 模型对抗 CR |
| 4 | 腾讯·审核业务 | *从需求到部署全 AI 自动化* | 2026-04-20 | L1→L2→L3 演进，交付+治理双轮 | CodeBuddy + PRD-Agent + 评分门禁 + 治理框架 |
| 5 | 阿里·向邦宇 | *Agent 时代生产力悖论* | 2026-05-08 | 瓶颈是协作而非 AI 能力，重塑组织 | ChangeSet + Agent Teams + Agentic IAM + ALL In Code |

**5 个来源的横向定位**：

```
工程层 ←——————————————————————————————→ 组织层

  得物 1     得物 2    腾讯 3    腾讯 4    阿里
  Spec      多仓      Harness   L1→L3    生产力
  Coding    全栈      Engineer  全自动    悖论
                      单系统    端到端    重塑
                      质量      团队      组织
```

---

## 二、逐篇精华

### 文章 1：得物·阳凯，*AI 编程能力边界探索：基于 Claude Code 的 Spec Coding 项目实战*

**核心论点**：AI Coding 的本质不是"用 AI 写代码"，而是用结构化规范+工作流把不确定性消除在执行之前——AI 在确定性空间里高速执行，人负责维护和扩展确定性空间的边界。**规范设计能力是 AI 时代开发者的核心竞争力。**

**最有价值的产物——三层规范体系**：

| 层 | 目录 | 作用 | 文件示例 |
|---|------|------|---------|
| 约束层 | `.claude/rules/` | 告诉 AI"禁止什么、必须怎样" | ts.md / code-names.md / comment.md / lint.md / style.md / pages.md / service.md |
| 示范层 | `.claude/code-design/` | 告诉 AI"标准产出长什么样" | pro-table / pro-form / drawer / component / utils 模板 |
| 视觉层 | `.claude/ui-design/` | 告诉 AI"页面应该长什么样" | HTML 高保真稿 |

**关键洞察**：仅约束层会得到"合法但不地道"的代码；加上示范+视觉层提供对齐锚点。

**按需求颗粒度选择协作模式**：
- 小颗粒（改文案/CSS）→ Cursor Chat 直接对话
- 中颗粒标准化（CRUD 页面）→ Rules / Skills 预设规范
- 中大颗粒复杂功能（重构/新模块）→ OpenSpec 标准 SDD 流程

**实战数据**：109 个 .jsonl 会话、2754 次工具调用、217 条人工指令、25546 行净增代码、提效 36%。

**对 dev-harness 的启发**：
- 直接对应 short-term ABC 中的 **C：三层规范目录脚手架**
- `templates/` 应增加完整 `.claude/{rules, code-design, ui-design}` 骨架
- 这是 SESSION-HANDOFF P0.4「多角色一等公民」的具体落地形态

---

### 文章 2：得物·盖伦，*基于 Harness + SDD + 多仓管理模式的 AI 全栈开发实践*

**核心论点**：让 AI "模仿"已有实现而非"凭空创造"——把前后端代码放进同一工作区，用 SDD 产出前后端两份契约对齐的设计文档，再用多 Agent 并行编码。把传统 6 人日全栈需求压缩到 3 人日，提效 50%+。

**Harness 思维四原则**：

| 原则 | 落地动作 |
|------|---------|
| 找相似实现 | 在代码库中找功能最近的已有实现作为参照 |
| 复用优先 | 直接复用已有组件、接口封装、数据结构 |
| 模仿着复制 | "抄一份改一改"优于用新方式写 Controller/Service/Repository |
| 约束生成范围 | 提示词里明确给参考文件路径与行号（如 `@FeatureTable/index.tsx:53-58`） |

**关键陷阱（必读）**：SDD 只描述"技术怎么实现"，不等于需求文档。AI 模仿参照代码时会**自动复刻隐性功能**（如关闭弹窗清空表单、永久有效自动清除日期、优先级自增）——SDD 里没写但代码里已有。**测试必须主动找差异**。

**Cursor vs Claude Code 实测对比**：

| 维度 | Cursor (Composer2) | Claude Code |
|------|-------------------|-------------|
| 索引 | 语义索引强 | 仅 grep |
| 速度 | 1-3 分钟 | 3-30 分钟 |
| 并行 | 多 Tab 默认并行 | 需手动注册子 Agent |
| 失败成本 | 失败任务不收费 | 易烧 Token |
| 适用 | 快速迭代 | 长链路复杂任务 |

**Subagent vs Team 模式（CC 内部）**：
- Subagent：只向主 Agent 汇报，任务完成即结束
- Team：队友间可直接沟通，共享任务列表自我协调，空闲挂起

**对 dev-harness 的启发**：
- Harness 思维四原则 = SESSION-HANDOFF P2.1 `reference_impl` 字段的**直接论据**
- `templates/plan-template.md` 应增加必填字段 `reference_impl: { backend: ..., frontend: ... }`
- `hooks/plan-watcher.py` 校验缺失则 reject

---

### 文章 3：腾讯·LEGO 团队，*Harness Engineering：AI 能在真正"出事会炸"的后端系统里写代码吗？*

**核心论点**：AI Coding 在超大规模、高风险后端系统（100 万行 C++ + 300 万行第三方库改造）能落地，但前提是"不是用 AI 而是驾驭 AI"——通过 Harness Engineering 给 AI 加上"上下文 + 约束 + 反馈"三层护栏。

**三大实践抓手**：

**1. 上下文建设（消除记忆偏差）—— 四层递进**：
- Agent.md（项目宪法）
- 安全纪律（反例免疫，每条规则配错误/正确写法）
- 领域知识（CR 检查清单 + 编码模式库 + 并发设计模式）
- 专业 Skill（含 38,068 行本地 RFC 原文，避免 AI"回忆"过时协议）

**2. 约束（让 AI"不敢"犯错）—— 三层**：
- Layer 1 权限安全基座
- Layer 2 代码规则即编译器（结构化约束 vs 模糊期望）
- Layer 3 流程约束（TaskList 阻塞顺序：功能实现 → 单元测试 → 代码审查）

**3. 反馈（速度决定进化速度）**：
- 自动采集 Hook
- **Pitfall Journal**（踩坑日志）
- .md 内联反馈
- 闭环：踩坑 → 安全规则 → CR 检查清单 → A/B 实验验证 → 保留或淘汰

**多模型对抗式 CR**（关键差异化）：
- 3 模型并行独立审查
- 交叉验证（≥2 模型命中 = 高置信）
- 辩论式讨论（同意/反对/维持）
- 全员无新发现自动收敛

**关键论点**：
- "工程体系才是核心资产，而不是某个模型或 prompt"——模型每天进化，工程体系价值持续累积
- "AI 的自信会传染：格式工整的输出反而降低人类审查意愿，是最高风险源"
- "结构化约束 > 语言化期望"——「写高质量代码」无效，「热路径禁止全局 mutex，用 per-thread 或分片锁」AI 100% 遵循
- AI 把局部提速做到 3-5 倍，但综合提升仅约 20%（诚实承认）

**对 dev-harness 的启发**：**最高浓度论据来源**——
- A. 多模型对抗 CR：直接对应 `generic-review` 升级方向
- B. Pitfall Journal 闭环：直接对应 `stop-hook.py` 改造方向
- 安全纪律的"反例免疫"格式 → `.claude/rules/` 写法范式

---

### 文章 4：腾讯·审核业务，*从提需求到部署发布，全 AI 全自动化后，研发效能全面跃升*

**核心论点**：研发效能要进入下一个量级，不能只优化 Coding 单点，必须把 AI 自动化从 Coding 同时向上游（需求/方案）和下游（测试/部署）延伸，并以 **"Harness Engineering for AI Coding"** 为骨架把全流程串成端到端闭环，目标 80% 效能提升。

**L1→L2→L3 演进路线**：
- L1 纯人工 → L2 人机协同（"技术方案生成代码"）→ L3 全自动化
- L2 内部三段：① 技术方案→代码 ② 技术方案→交付 ③ 需求→交付端到端

**应对 L3 的核心挑战**：

| 挑战 | 关键举措 |
|------|---------|
| 交付流程标准化 | 流程编排 skill 串联需求/研发/测试/部署且支持回滚 |
| 需求标准化 | 4 段式模板（概述/正文/版本/依赖）+ 评分规则 ≥80 + PRD-Agent |
| Skills 沉淀 | 技术方案生成、代码生成、代码 CR、测试用例执行等标准 skill |
| 知识库 | 业务知识库 + 代码知识库 |
| 代码质量 | 需求评审/方案评审/代码 CR/安全检测多重门禁 |
| 线上治理 | 全自动化治理框架打通日志监测，自动巡检/修复 |

**L3 公式**：
> AI 全自动化交付 = LLM + **Harness Engineering**（工作流程 + 知识库 + skills 管理）+ **Business Engineering**（skills + 知识库的沉淀）

**双轮架构**：
- **AI 全自动化交付框架**：流程串联 + 评审/门禁/MR 卡点 + 闭环反馈与自修复
- **AI 全自动化治理框架**：运行时日志/指标/Spec/中间产物洞察 + 自动巡检修复 + Skills 自动回溯更新

**关键洞察**：AI 编码偏静态生成，对 **架构/性能/可用性** 等运行时属性天然薄弱——**治理框架** 必须与交付框架并行。

**实战数据**：6 个试点需求三轮迭代，需求评分 ≥80，方案评分 ≥80，代码行采纳率 ≥90%，AI 生成率 ≥80%；测试环境创建节约 60%+，部署阶段节约 50%。

**对 dev-harness 的启发**：
- "治理框架"是 SESSION-HANDOFF 中"sandbox/backtest/submission 缺失"的**真正答案**
- PRD 评分门禁 ≥80 是 `generic-product-prd` 应该补的能力
- Skills 自动回溯更新机制 → Pitfall Journal 闭环的下游

---

### 文章 5：阿里·向邦宇（阿里代码平台负责人），*Agent 时代的生产力悖论：当协作本身成为最大的瓶颈*

**核心论点**：Agent 生成代码呈指数级增长，组织整体研发效率却提升有限——**瓶颈不在 AI 能力，而在于沿用工业时代的协作分工/资源组织/发布流程**，约束已从「代码生产速度」变成「软件组织结构」。类比：换了电力引擎但不重塑流水线，只会让牛车上绑火箭。

**5 个独有概念（其他 4 篇没有）**：

| 概念 | 含义 | 对 dev-harness 的启发 |
|------|------|---------------------|
| **ChangeSet** | 一级变更单元（区别于分支/Topic/Spec），承载 diff + commit + E2E + 风险 + 回滚边界 | dev-harness 当前 `harness-state.json` 是 session 级，缺一个变更级载体 |
| **Agent Teams**（**即将开源**）| 多 Agent 协作平面，可 @ 不同角色 Agent | dev-harness multi-agent 是 worktree+自建 worker，可能要考虑对齐 |
| **Agentic IAM** | 给 Agent 的身份/权限体系 | 长期方向，超越当前所有 P 级 |
| **Claw 管家模式** | 长生命周期 Agent，主动巡检/优化/同步 | 比 dev-harness 的"会话级 agent"高一档 |
| **合并队列** | 短生命周期分支 + 串行合并 + 分级质量门禁 | 多 Agent 并行的合入闸门 |

**ALL In Code 大库**（核心方法论）：
- 单库容纳一整个产品/应用全部资源（代码平台 10+ 应用全放一起）
- 内容：前后端代码 + Agents Skills 与工具 + 文档与操作手册 + 发布信息 + handbooks + 运维态信息
- 哲学：**"代码库就是唯一的事实来源"**

**Coding/CI/CR/CD 阶段融合**（§ 5.1）：
- 摒弃中心化 Code Review 系统
- CR 在 Coding 阶段同步发生，由 Agent 主导执行
- 需求按"端到端业务场景"组织，而非前后端分工
- 协作单元从"人↔人"演进为"人↔Agent / Agent↔Agent 的任务委托与自治执行"

**对 dev-harness 的启发**：**这两条是设计哲学（design-philosophy.md 原则 4 + 原则 5）的直接来源**——
- 短期不直接落地（太激进）
- 但任何短期改造不能与之方向相反
- 长期目标：v5/v6 引入 ChangeSet 一级原语

---

## 三、横向方法论对比

### 共识维度（5 篇都强调）

| 共识 | 体现 |
|------|------|
| AI ≠ Copilot，是"极度服从但无业务常识的执行者" | 5 篇都有 |
| 工程体系比 prompt 更值钱 | 腾讯 3 原话 / 阿里第 4 章 |
| 规范/Skill 沉淀 > 一次性 prompt | 得物 1 三层规范 / 腾讯 3 Skill 管理 / 阿里 ALL In Code |
| 多 Agent 并行 是趋势 | 得物 2 双 SDD / 腾讯 4 Agent 协同 / 阿里 Agent Teams |
| 质量门禁不能省 | 5 篇全部强调 |

### 差异化维度

| 维度 | 得物 1 | 得物 2 | 腾讯 3 | 腾讯 4 | 阿里 |
|------|--------|--------|--------|--------|------|
| 目标场景 | 中后台 CRUD | 全栈业务 | 高风险底层（C++）| 业务团队 L3 | 组织级重塑 |
| 模型策略 | Claude Code 主力 | Sonnet 为主 + Haiku Mock | 多模型对抗 | CodeBuddy 平台 | 与具体模型解耦 |
| 工程深度 | 中（规范层）| 中（提示词级）| 高（86K 行规则代码）| 高（双轮平台）| 极高（重塑组织）|
| 时效性 | 立即可抄 | 立即可抄 | 大投入才值 | 平台级 | 长期愿景 |

### 工具/产品提及频率

| 工具 | 提及篇数 | 备注 |
|------|---------|------|
| Claude Code | 4 篇 | 1, 2, 3 主用，4 旁参考 |
| Cursor | 2 篇 | 1, 2 |
| openspec | 2 篇 | 1, 2 (SDD 标准化指令) |
| MCP | 4 篇 | 1, 3, 4, 5 都强调 |
| AGENTS.md / Agent.md | 1 篇 | 腾讯 3 (项目宪法) |
| 阿里·搭叩 / Aone / AoneCopilot | 1 篇 | 仅阿里 |

---

## 四、短期 ABC 三件事的论据归属

dev-harness v4 短期落地计划（按 SESSION-HANDOFF + 5 篇文章修订）：

### A. 多模型异构对抗 CR

**主要论据**：腾讯 3（多模型对抗 CR）

**辅助论据**：
- Anthropic *Harness design* 的 Generator-Evaluator Pattern（哲学层）
- 得物 2 的 Subagent 模式（实现参考）

**改造点**：
- `agents/code-reviewer.md` `agents/security-reviewer.md` `agents/architect.md` 各加 `model:` 字段差异化
- `generic-review/SKILL.md` 增加投票汇总逻辑（≥2 命中 = 高置信）

**成本**：1-2 天

### B. Pitfall Journal 闭环

**主要论据**：腾讯 3（Pitfall Journal + 反馈闭环）

**辅助论据**：
- Anthropic *Effective harnesses* 的 ground truth from environment（哲学层）
- SESSION-HANDOFF P0.1（stop-hook 上下文注入器）
- 腾讯 4 的 Skills 自动回溯更新

**改造点**：
- `hooks/stop-hook.py` 增加 `inject_context()`：build/test 失败时把根因写入 `.claude/pitfall-journal.jsonl`
- 续跑时把 ground truth 注入下一轮 prompt
- 满 3 条同类失败自动追加到 `.claude/rules/`

**成本**：2-3 天

### C. 三层规范目录脚手架

**主要论据**：得物 1（三层规范体系）

**辅助论据**：
- 阿里（ALL In Code）哲学层指引方向
- OpenAI *Harness Engineering*（AGENTS.md 是地图不是百科）

**改造点**：
- `templates/` 增加 `project-skeleton/` 目录
- `.claude/{rules, code-design, ui-design, handbooks, runbooks}` 完整骨架
- README 解释每层职责
- `/dev` 首次进入未初始化项目时检测，提示用户是否生成骨架

**成本**：1 天

### 实施顺序建议

```
C（最简，1天，立竿见影）
→ A（中等，1-2天，能用 C 的 rules/ 作为审查锚点）
→ B（最难，2-3天，需要 stop-hook 大改，让 A 先稳定）
```

### 评测兜底（前置）

ABC 三件事都需要 **P1.1 eval scenarios**（5 条 → 20 条真实任务数据集）作为客观验证。建议 **C 实施后 + A 实施前**插入 P1.1 起步。

---

## 五、对外定位话术（培训/HR/同事用）

> "我们的 AA Coder 已经把中段工程化做完了（达到行业 Top 20% 水平）；
> 下一阶段重点是补全前段（业务→架构）和后段（sandbox→submission）的标准化产物，
> 让 AI 在每个阶段都有明确的输入/输出契约可以模仿。"

**和 5 篇文章的对应关系**（培训第一节用）：

> dev-harness 在 5 个标杆中的定位：
>
> - **像得物 1 / 腾讯 3** — 关注规范沉淀和工程体系
> - **像腾讯 4** — 试图打通需求→部署全流程
> - **像得物 2** — 支持多 Agent 并行
> - **不像阿里** — 我们是项目内插件，不重塑组织流程
> - **不像得物 1 的视觉层** — 我们暂未落地 HTML 高保真稿层
>
> 短期目标：补齐三层规范目录（C）、引入多模型对抗 CR（A）、闭环 Pitfall Journal（B）

**边界声明**（避免误用）：

> "dev-harness 解决的是 plan→code→review 这段中游问题。
> 前段 SRS/架构 和 后段 sandbox/submission 仍然是组织级流程的责任，
> AA Coder 不能替代，只能配合。"

---

## 六、原文存档位置

| 类型 | 位置 |
|------|------|
| 国内 5 篇微信原文摘要（本文档）| `docs/external-references-2026-05.md` |
| OpenAI 3 篇官方简体中文原文 | `.design/openai-{harness-eng,unrolling,unlocking}-zh*.txt` |
| Anthropic 3 篇英文（已抓取整合）| 未独立存档，引用见 `design-philosophy.md` |
| 自做的更早期深度调研 | `.design/deep-research-harness-engineering-2026.md` |

如需重抓原文：用 `web-access` skill + `~/.claude/skills/web-access/references/site-patterns/mp.weixin.qq.com.md` 站点经验。

---

## 七、引证清单（5 篇国内文章 URL）

1. [得物·阳凯，*AI 编程能力边界探索：基于 Claude Code 的 Spec Coding 项目实战*](https://mp.weixin.qq.com/s/1Oi7YhMgcPp9gQAWPndXWA)
2. [得物·盖伦，*基于 Harness + SDD + 多仓管理模式的 AI 全栈开发实践*](https://mp.weixin.qq.com/s/ygQGSH5c7GHYDvkqWoQTXQ)
3. [腾讯·LEGO，*Harness Engineering：AI 能在真正"出事会炸"的后端系统里写代码吗？*](https://mp.weixin.qq.com/s?__biz=MjM5ODYwMjI2MA==&mid=2649801331&idx=1&sn=7dfd93b1754a4f80c993347c4b57adb1&chksm=bfebd3a1b0e95c0aad30ff2977d70d82a40fba2473ca7de2b17b877c1710fe9a9fd060b72bb4)
4. [腾讯·审核业务，*从提需求到部署发布，全 AI 全自动化后，研发效能全面跃升*](https://mp.weixin.qq.com/s/fLiyW2t4CBOnWjx2Km8d8g)
5. [阿里·向邦宇，*Agent 时代的生产力悖论：当协作本身成为最大的瓶颈*](https://mp.weixin.qq.com/s/GPoQnFsXnnNpKdefWWiKRw)
