# Dev Harness 竞品全景对比分析

> 研究日期：2026-04-04
> 方法：WebSearch 逐一调研 11 个竞品的最新公开信息
> 标注规则：数据均标明来源；无法确认的标注「未确认」

---

## 一、竞品总览表

| # | 框架 | Stars | 最新版本/更新 | 定位 | 开源 |
|---|------|-------|-------------|------|------|
| 1 | **oh-my-claudecode (OMC)** | ~1.2k (858/24h 爆发) | v4.9.2 (2026-04) | Claude Code 多 Agent 团队编排 | Yes |
| 2 | **Karpathy autoresearch** | ~53.5k | 2026-03-07 发布 | ML 实验自动循环 | Yes |
| 3 | **Superpowers** | ~107k | 2026-01 官方市场上架 | Claude Code 开发方法论框架 | Yes |
| 4 | **DeerFlow 2.0** | ~45k+ | 2026-02-27 (ByteDance) | 长时任务 SuperAgent | Yes |
| 5 | **Cursor Rules** | N/A (IDE 内置) | .cursor/rules/ (.mdc 格式) | IDE 规则系统 | 部分 |
| 6 | **Aider** | ~42.7k | 2026-03-17 活跃 | 终端 AI 配对编程 | Yes |
| 7 | **Cline** | ~59.8k | v3.70.0 (2026-03) | VS Code 自治 Agent | Yes |
| 8 | **Continue.dev** | ~30.6k | 2026 活跃 | IDE AI 助手 + CI 检查 | Yes |
| 9 | **OpenHands** | ~70k+ | v1.6.0 (2026-03-30) | AI 软件工程师平台 | Yes |
| 10 | **SWE-agent** | ~18.8k | v1.0 (2026-02-13) | GitHub Issue 自动修复 | Yes |
| 11 | **Devin** | N/A (闭源) | v2.2 (2026) | 商业 AI 开发者 | No |
| - | **Dev Harness (我们)** | 新发布 | v3.0 (2026-04-04) | Pipeline 编排 + 三层 Skill | Yes |

---

## 二、逐一深度分析

### 1. oh-my-claudecode (OMC)

**仓库**: [Yeachan-Heo/oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)
**官网**: [ohmyclaudecode.com](https://ohmyclaudecode.com/)

| 维度 | 详情 |
|------|------|
| Stars | ~1.2k (2026-04 初), 858 stars/24h 爆发增长 |
| 版本 | v4.9.2 (npm: oh-my-claude-sisyphus@4.10.1) |
| 核心特性 | 32 agents + 40+ skills, tmux 5-worker 并行, Ultrapilot 全自主模式 |
| 架构 | 五阶段流水线: planning → PRD → execution → verification → correction |
| Stop Hook | persistent-mode.cjs (43KB), context-limit 放行, session ID 隔离, circuit breaker |
| 自动续跑 | 有 — Autopilot 模式 + persistent-mode stop hook |
| 可扩展 | 11 个生命周期事件 x 20 个 hook 脚本; keyword-detector + skill-injector |
| 评测框架 | 无专门评测; 社区 benchmark 显示 69.2% pass rate (vs 73.1% plain) |
| HUD/Dashboard | 未确认 |
| 模型路由 | Haiku(快)/Sonnet(标准)/Opus(深度), 节省 30-50% token |
| **vs Dev Harness** | OMC 重「团队多 Agent」, DH 重「Pipeline 编排 + 三层 Skill」; OMC 无评测框架; DH 无 tmux 并行 |

---

### 2. Karpathy autoresearch

**仓库**: [karpathy/autoresearch](https://github.com/karpathy/autoresearch)
**公告**: [VentureBeat 报道](https://venturebeat.com/technology/andrej-karpathys-new-open-source-autoresearch-lets-you-run-hundreds-of-ai)

| 维度 | 详情 |
|------|------|
| Stars | ~53.5k (2026-03-24), 21k+ stars 首周 |
| 发布 | 2026-03-07 |
| 核心特性 | AI agent + 单 GPU 训练 = 自动实验循环; ~12 实验/小时, ~100 实验/夜 |
| 架构 | Markdown 描述研究方向 → AI coding agent 自动修改代码 → 训练 5 分钟 → 保留或丢弃 |
| 自动续跑 | 有 — 核心就是 while-loop: 修改→训练→评估→决策 |
| 自修复 | 有 — 训练失败自动回滚 git, 只保留 beat baseline 的改动 |
| 可扩展 | 有限 — program.md 定义研究方向, 但无 Skill 系统 |
| 评测框架 | 内置 — 训练 loss 作为唯一评测指标 |
| HUD/Dashboard | 无 — git log 作为实验记录 |
| **vs Dev Harness** | 完全不同赛道; autoresearch 是 ML 实验循环, DH 是软件开发流水线; 但其「自动循环+评估+保留最优」模式值得借鉴 |

---

### 3. Claude Code Superpowers

**仓库**: [obra/superpowers](https://github.com/obra/superpowers)
**市场**: [Anthropic 官方插件](https://claude.com/plugins/superpowers)

| 维度 | 详情 |
|------|------|
| Stars | ~107k (5 个月增长, 2026-01 发布) |
| 版本 | 2026-01-15 Anthropic 官方市场上架 |
| 核心特性 | 七阶段工作流: Brainstorm → Spec → Plan → TDD → Subagent Dev → Review → Finalize |
| 架构 | Skill 文件 (Markdown) 教会 Claude 结构化开发方法论 |
| Stop Hook | 「Double Shot Latte」hook — agent 自主决策是否继续 |
| 自动续跑 | 保守模式 — 用户显式 `/execute-plan` 触发, 不默认自动循环 |
| 可扩展 | 有 — composable skills, 用户可自定义 skill; superpowers-lab 实验性 skill |
| TDD | 核心特性 — 强制 red/green TDD, YAGNI, DRY |
| 评测框架 | 无内置评测 |
| HUD/Dashboard | 无 |
| Subagent | 有 — subagent-driven-development, 每任务用 fresh subagent 防上下文漂移 |
| **vs Dev Harness** | Superpowers 重「方法论 + TDD 强制」, DH 重「Pipeline 编排 + 状态持久化 + 评测」; Superpowers 无三层 Skill 优先级、无评测框架、无 HUD; DH 无 TDD 强制(已加 generic-tdd 缓解) |

---

### 4. DeerFlow 2.0 (ByteDance)

**仓库**: [bytedance/deer-flow](https://github.com/bytedance/deer-flow)
**官网**: [deerflow.tech](https://deerflow.tech/)

| 维度 | 详情 |
|------|------|
| Stars | ~45k+ (2026-02-28 发布, 24h 内 GitHub Trending #1) |
| 版本 | 2.0 (2026-02-27) |
| 核心特性 | SuperAgent: research + code + reports + slides + images/video |
| 架构 | LangGraph + LangChain; Docker 沙盒; filesystem + bash + memory + skills + subagents |
| 自动续跑 | 有 — 长时任务设计, subagent 自动编排 |
| 可扩展 | 有 — Markdown Skill 文件, 可自定义/替换/组合 |
| 评测框架 | 未确认 |
| HUD/Dashboard | 有 — Web UI (localhost:2026) |
| 沙盒 | Docker 容器完整隔离 (filesystem + bash + 执行) |
| **vs Dev Harness** | DeerFlow 是通用 SuperAgent (不限编码), DH 是专注软件开发 Pipeline; DeerFlow 有 Docker 沙盒/Web UI, DH 有三层 Skill + 评测 + 路线分级; DeerFlow 依赖 LangChain 生态, DH 纯 Claude Code 原生 |

---

### 5. Cursor Rules / .cursorrules

**文档**: [Cursor Rules](https://docs.cursor.com/context/rules)
**社区**: [awesome-cursorrules](https://github.com/PatrickJS/awesome-cursorrules)

| 维度 | 详情 |
|------|------|
| Stars | N/A (IDE 内置功能) |
| 格式 | .cursorrules (旧) → .cursor/rules/*.mdc (新, 推荐) |
| 核心特性 | 持久化 system prompt; 按 glob 匹配文件自动激活规则 |
| 架构 | MDC (Markdown Cursor) 格式 + frontmatter (globs, alwaysApply) |
| 自动续跑 | 无 — 规则系统, 不是执行引擎 |
| 可扩展 | 有 — 按文件/目录拆分规则, 社区共享规则库 |
| 评测框架 | 有 — CursorBench (内部, 基于真实 Cursor session) |
| HUD/Dashboard | Cursor IDE 内置 |
| **vs Dev Harness** | Cursor Rules 是「规则注入」, DH 是「Pipeline 执行」; 不同层面; Cursor Rules 的 glob 匹配思路可借鉴到 Skill 解析 |

---

### 6. Aider

**仓库**: [Aider-AI/aider](https://github.com/Aider-AI/aider)
**官网**: [aider.chat](https://aider.chat/)

| 维度 | 详情 |
|------|------|
| Stars | ~42.7k |
| 更新 | 2026-03-17 活跃 |
| 核心特性 | 终端 AI 配对编程; Git 原生集成; Repo Map; 100+ 语言; 语音支持 |
| 架构 | 单进程 CLI; 多 LLM 后端; tree-sitter 代码分析; edit format (diff/whole/udiff) |
| 自动续跑 | 有限 — lint-and-fix 自动循环 (编辑→lint→修复→重复); 无 Pipeline 编排 |
| 自修复 | 有 — 每次 LLM 编辑后自动 lint, 发现错误自动请求修复 |
| 可扩展 | 有限 — 配置驱动 (linter/tester 可自定义); 无 Skill 系统 |
| 评测框架 | 有 — 内置 benchmark 套件; 持续跟踪各 LLM 在 aider benchmark 上的表现 |
| HUD/Dashboard | 无 — 纯终端 |
| **vs Dev Harness** | Aider 重「交互式配对」, DH 重「自主 Pipeline」; Aider 无状态持久化/续跑/Pipeline 阶段; DH 无语音/Repo Map |

---

### 7. Cline

**仓库**: [cline/cline](https://github.com/cline/cline)
**官网**: [cline.bot](https://cline.bot)

| 维度 | 详情 |
|------|------|
| Stars | ~59.8k, 5M+ VS Code 安装 |
| 版本 | v3.70.0 (2026-03) |
| 核心特性 | VS Code 内自治 Agent; 创建/编辑文件 + 执行命令 + 浏览器操作; MCP 扩展 |
| 架构 | VS Code Extension; 先规划后执行策略; MCP 工具协议; YOLO 自动批准模式 |
| 自动续跑 | 有 — YOLO 模式全自动; Native subagents (v3.58) |
| 可扩展 | 强 — MCP 协议无限扩展; 用户可让 Cline 自建 MCP 工具; 无工具数量上限 |
| 评测框架 | 无内置 |
| HUD/Dashboard | VS Code 侧边栏 UI |
| **vs Dev Harness** | Cline 是 IDE-native, DH 是 CLI-native; Cline 用 MCP 扩展, DH 用三层 Skill; Cline 无 Pipeline 阶段/状态管理/评测 |

---

### 8. Continue.dev

**仓库**: [continuedev/continue](https://github.com/continuedev/continue)
**官网**: [continue.dev](https://www.continue.dev/)

| 维度 | 详情 |
|------|------|
| Stars | ~30.6k |
| 更新 | 2026 活跃 |
| 核心特性 | IDE AI 助手 (VS Code + JetBrains); 自动补全 + Chat + CI 检查; 多模型支持 |
| 架构 | config.json/yaml 配置; context providers; slash commands; CI 集成 (GitHub Actions) |
| 自动续跑 | 无 — 交互式助手, 非自主 Agent |
| 可扩展 | 有 — context providers + slash commands + skills (checks 格式); 团队共享配置 |
| 评测框架 | 有 — AI checks 可在 PR 上运行, 类似 CI lint |
| HUD/Dashboard | IDE 侧边栏 |
| CI 集成 | 强 — 原生 GitHub Actions 支持; Sentry/Snyk 自动修复 |
| **vs Dev Harness** | Continue 重「IDE 内交互 + CI 集成」, DH 重「自主 Pipeline + 状态管理」; Continue 的 CI 集成思路可借鉴 |

---

### 9. OpenHands (formerly OpenDevin)

**仓库**: [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands)
**官网**: [openhands.dev](https://openhands.dev/)

| 维度 | 详情 |
|------|------|
| Stars | ~70k+, 490+ contributors |
| 版本 | v1.6.0 (2026-03-30), Kubernetes 支持 + Planning Mode beta |
| 融资 | $18.8M Series A |
| 核心特性 | AI 软件工程师: 浏览网页 + 写代码 + 执行命令 + 解决 GitHub Issues |
| 架构 | Docker 沙盒; 多模型后端 (Claude/GPT-4o/Gemini/本地); Planning Mode |
| 自动续跑 | 有 — 自主工作模式; Planning Mode 允许先批准计划再自动执行 |
| 可扩展 | 有限 — 模型可切换; 工具集固定 |
| 评测框架 | 强 — SWE-bench Verified 53%+; OpenHands Index (多维评测); SWE-Gym |
| HUD/Dashboard | 有 — sdk-dashboard + openhands-dashboard + community-pr-dashboard |
| **vs Dev Harness** | OpenHands 是独立 AI Engineer 平台, DH 是 Claude Code 增强; OpenHands 评测体系更成熟; DH 三层 Skill + YAML Pipeline 更灵活; OpenHands 需 Docker 环境 |

---

### 10. SWE-agent (Princeton/Stanford)

**仓库**: [SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent)
**文档**: [swe-agent.com](https://swe-agent.com/latest/)

| 维度 | 详情 |
|------|------|
| Stars | ~18.8k |
| 版本 | v1.0 (2026-02-13); mini-swe-agent v2 已发布 |
| 核心特性 | GitHub Issue → 自动修复; Agent-Computer Interface (ACI); 网络安全/竞赛编程 |
| 架构 | 自定义 ACI 增强 LLM 的仓库浏览/编辑/执行能力; NeurIPS 2024 论文 |
| 自动续跑 | 有 — 自主工作直到 Issue 解决 |
| 可扩展 | 有限 — ACI 可配置; mini-swe-agent 100 行极简 |
| 评测框架 | 强 — SWE-bench 核心; mini-swe-agent 74%+ on SWE-bench Verified |
| HUD/Dashboard | 无 |
| **vs Dev Harness** | SWE-agent 专注 Issue 修复, DH 是全流程 Pipeline; SWE-agent 的 ACI 设计思路值得学习; DH 更面向「从零到交付」 |

---

### 11. Devin (Cognition AI)

**官网**: [devin.ai](https://devin.ai/)
**博客**: [cognition.ai/blog](https://cognition.ai/blog/devin-2)

| 维度 | 详情 |
|------|------|
| Stars | N/A (闭源商业产品) |
| 版本 | v2.2 (2026), $20/月起 |
| 核心特性 | 全自主 AI 开发者; Cloud IDE; 并行 Devin 实例; Interactive Planning |
| 架构 | Cloud-native; VSCode-like 界面; AWS/Azure/GCP 集成; Docker/CI/CD 自动配置 |
| 自动续跑 | 有 — 核心设计: 分配任务后全自主工作; 启动速度 3x 提升 |
| 可扩展 | 有限 — 商业平台, 不可自定义 Agent/Skill |
| 评测框架 | 有 — 内部 benchmark (83%+ 任务完成率提升); ACU 计量 |
| HUD/Dashboard | 强 — DeepWiki 自动生成架构文档; 完整 IDE + 计划视图 + 代码审查 |
| 定价 | Core: $20/月 + $2.25/ACU; Team: $500/月 (250 ACU); Enterprise: 定制 |
| **vs Dev Harness** | Devin 是商业闭源云平台, DH 是开源本地插件; Devin 的 Interactive Planning + DeepWiki 功能可借鉴; DH 零成本 + 完全可控 |

---

## 三、关键特性矩阵对比

### 3.1 可扩展机制（类似「三层 Skill 解析」）

| 框架 | Skill/插件系统 | 层级优先级 | 类比 DH 三层解析 |
|------|-------------|-----------|-----------------|
| **Dev Harness** | 三层 Skill: L1 项目 > L2 用户 > L3 内置 | **有** | -- (我们的独创) |
| **Superpowers** | Composable Skills (Markdown) | 无层级 | 单层 Skill, 无优先级覆盖 |
| **OMC** | 40+ Skills + keyword-detector + skill-injector | 无层级 | Hook 注入式, 不是层级覆盖 |
| **DeerFlow** | Markdown Skill 文件, 可自定义/替换 | 无层级 | 可替换但无优先级链 |
| **Cursor Rules** | .cursor/rules/*.mdc + glob 匹配 | **近似** | glob 条件激活 ≈ 场景层 Skill |
| **Cline** | MCP 工具协议扩展 | 无层级 | 协议级扩展, 非 Skill 文件 |
| **Continue** | Context providers + slash commands + skills | 无层级 | 配置驱动, 无覆盖链 |
| **Aider** | 配置驱动 (linter/tester) | 无层级 | 极简配置, 非 Skill |
| **OpenHands** | 工具集固定, 模型可切换 | 无层级 | 不可扩展 |
| **SWE-agent** | ACI 配置 | 无层级 | 接口级, 非 Skill |
| **Devin** | 闭源, 不可自定义 | 无层级 | 不适用 |

**结论**: **三层 Skill 优先级覆盖是 Dev Harness 独有特性**。Cursor Rules 的 glob 条件激活最接近, 但它是规则注入而非执行层。

---

### 3.2 Stop Hook / 自动续跑

| 框架 | 机制 | 实现方式 | 成熟度 |
|------|------|---------|--------|
| **Dev Harness** | 六道防线 Stop Hook | Python, JSON 输出, session 隔离 | 高 |
| **OMC** | persistent-mode.cjs | Node.js, circuit breaker, context-limit 放行 | 高 |
| **Superpowers** | Double Shot Latte hook | Agent 自决, 保守策略 | 中 |
| **Karpathy autoresearch** | while-loop + git rollback | Bash, 训练 loss 驱动 | 高 (ML 场景) |
| **Cline** | YOLO 模式 + subagents | VS Code 内置 | 中 |
| **DeerFlow** | 长时任务 subagent 编排 | LangGraph | 中 |
| **OpenHands** | 自主工作 + Planning Mode | Docker 沙盒内 | 中 |
| **Devin** | 全自主 + Interactive Planning | 云端, 闭源 | 高 |
| **Aider** | lint-and-fix 自动循环 | 有限循环, 非全流程 | 低 |
| **SWE-agent** | 自主修复直到完成 | ACI 驱动 | 中 |
| **Continue** | 无 | 交互式助手 | N/A |
| **Cursor Rules** | 无 | 规则系统, 非执行引擎 | N/A |

**结论**: DH 和 OMC 的 Stop Hook 最成熟。DH 的六道防线（rate limit/context/超时/总时长/滑动窗口/死循环）防线最多。

---

### 3.3 可视化 HUD / Dashboard

| 框架 | HUD 类型 | 详情 |
|------|---------|------|
| **Dev Harness** | CLI Rich HUD + Web HUD | `harness.py hud --rich` + `web-hud` (localhost:1603) |
| **Devin** | 云端 IDE + DeepWiki | 最完整: 计划/代码/审查/架构文档 |
| **OpenHands** | Web Dashboard | sdk-dashboard + community-pr-dashboard |
| **DeerFlow** | Web UI | localhost:2026, 任务可视化 |
| **Cline** | VS Code 侧边栏 | IDE 原生 UI |
| **Continue** | VS Code/JetBrains 侧边栏 | IDE 原生 UI |
| **Cursor Rules** | Cursor IDE 内置 | IDE 原生 |
| **OMC** | 未确认 | 可能有 tmux 状态显示 |
| **Superpowers** | 无 | 纯 Markdown 指令 |
| **Aider** | 无 | 纯终端 |
| **SWE-agent** | 无 | 纯终端 |
| **autoresearch** | 无 | git log 即记录 |

**结论**: DH 的 CLI Rich HUD + Web HUD 组合在 Claude Code 插件中独一无二。Devin/OpenHands 的 Web Dashboard 更丰富但面向不同场景。

---

### 3.4 评测框架

| 框架 | 评测能力 | 详情 |
|------|---------|------|
| **Dev Harness** | 内置 eval-runner | 21 测试, 5 维度, 加权评分, before/after 对比 |
| **OpenHands** | SWE-bench + OpenHands Index | 最全面: Issue 修复/新建应用/前端/测试 多维 |
| **SWE-agent** | SWE-bench 核心贡献者 | 74%+ SWE-bench Verified (mini-swe-agent) |
| **Cursor** | CursorBench (内部) | 基于真实 session, 多维评估 |
| **Aider** | aider benchmark | 持续跟踪各 LLM 表现 |
| **autoresearch** | 训练 loss | 简单但有效的单指标评测 |
| **Devin** | 内部 benchmark | 83%+ 任务完成率提升 (vs v1) |
| **Superpowers** | 无 | -- |
| **OMC** | 无 | 社区零散 benchmark |
| **DeerFlow** | 未确认 | -- |
| **Cline** | 无 | -- |
| **Continue** | AI checks (CI) | PR 级检查, 非 Agent 评测 |

**结论**: DH 是 Claude Code 插件中**唯一内置评测框架**的。OpenHands/SWE-agent 在学术评测上更强但面向不同场景。

---

## 四、竞品分层定位图

```
                        自主性 ↑
                        │
              Devin ────┤── OpenHands
                        │
            DeerFlow ───┤── SWE-agent
                        │
        OMC ────────────┤── Dev Harness (我们)
                        │
         Superpowers ───┤── Cline
                        │
              Aider ────┤── Continue
                        │
       Cursor Rules ────┤
                        └──────────────────→ 可定制性
```

- **左上 (高自主 + 低定制)**: Devin — 闭源云平台, 开箱即用但不可改
- **右上 (高自主 + 高定制)**: OpenHands, DeerFlow — 开源全自主 Agent
- **中间 (中自主 + 高定制)**: **Dev Harness**, OMC — Pipeline 编排 + 可扩展
- **中下 (低自主 + 高定制)**: Superpowers, Cline — 方法论/工具增强
- **底部 (交互式)**: Aider, Continue — 人机配对

---

## 五、Dev Harness 差异化优势总结

### 独有特性（竞品均无）

1. **三层 Skill 解析 (L1>L2>L3)** — 项目级覆盖用户级覆盖内置级; 无竞品有此机制
2. **YAML Pipeline 路线分级 (B/A/C/C-lite/D)** — 按任务复杂度选择流程深度
3. **内置评测框架 + 加权评分** — Claude Code 插件中唯一
4. **CLI Rich HUD + Web HUD** — Claude Code 原生可观测性最佳
5. **三路代码审查** — Codex x2 + Claude 交叉验证

### 强于多数竞品

1. **六道防线 Stop Hook** — 比 OMC 多 rate-limit/滑动窗口/死循环检测
2. **多角色 Profile 路由** — backend/frontend/product/qa 专用 Skill
3. **技术栈自动检测** — detect-stack.sh 自动适配

### 需补强的方面

1. **TDD 强制** — Superpowers 核心优势, DH 已加 generic-tdd 但非强制
2. **并行执行** — OMC tmux 5-worker, DH 当前串行
3. **MCP 扩展** — Cline 的 MCP 生态更开放
4. **CI/CD 集成** — Continue 的 GitHub Actions 集成更成熟
5. **Docker 沙盒** — DeerFlow/OpenHands 的隔离更彻底
6. **社区规模** — 所有竞品 stars 均远超 DH

---

## 六、战略建议

### 短期（v3.1）— 巩固独有优势

- Session ID 隔离（对标 OMC）
- 评测框架增加 SWE-bench 子集支持
- 三层 Skill 解析加入 glob 条件匹配（借鉴 Cursor Rules）

### 中期（v4.0）— 补齐短板

- TDD 强制模式（学习 Superpowers 的 red/green 门禁）
- 并行阶段执行（不一定 tmux, 可用 subagent 并发）
- Web HUD 增加 DeepWiki 式架构可视化（借鉴 Devin）

### 长期定位

> **不和 Superpowers/OMC 正面竞争, 而是作为「Pipeline 编排层」与它们共存。**
> 
> DH 的核心价值 = 三层 Skill 解析 + YAML Pipeline + 评测框架 + HUD 可观测
> 这些是「基础设施层」, 而非「方法论层」或「Agent 层」

---

## Sources

- [oh-my-claudecode GitHub](https://github.com/Yeachan-Heo/oh-my-claudecode)
- [oh-my-claudecode 官网](https://ohmyclaudecode.com/)
- [OMC AIToolly 报道](https://aitoolly.com/ai-news/article/2026-04-02-oh-my-claudecode-a-new-multi-agent-orchestration-framework-designed-for-team-based-claude-code-integ)
- [Karpathy autoresearch GitHub](https://github.com/karpathy/autoresearch)
- [autoresearch VentureBeat](https://venturebeat.com/technology/andrej-karpathys-new-open-source-autoresearch-lets-you-run-hundreds-of-ai)
- [autoresearch DataCamp Guide](https://www.datacamp.com/tutorial/guide-to-autoresearch)
- [Superpowers GitHub](https://github.com/obra/superpowers)
- [Superpowers Anthropic Marketplace](https://claude.com/plugins/superpowers)
- [Superpowers Builder.io 深度分析](https://www.builder.io/blog/claude-code-superpowers-plugin)
- [Superpowers DevGenius 解析](https://blog.devgenius.io/superpowers-explained-the-claude-plugin-that-enforces-tdd-subagents-and-planning-c7fe698c3b82)
- [DeerFlow GitHub](https://github.com/bytedance/deer-flow)
- [DeerFlow DEV Community](https://dev.to/arshtechpro/deerflow-20-what-it-is-how-it-works-and-why-developers-should-pay-attention-3ip3)
- [DeerFlow 2.0 #1 Trending](https://www.arturmarkus.com/bytedances-deerflow-2-0-hits-1-on-github-trending-with-35300-stars-in-24-hours-superagent-framework-executes-code-in-docker-sandboxes-not-chat-windows/)
- [Cursor Rules 官方文档](https://docs.cursor.com/context/rules)
- [Cursor Rules 2026 指南](https://dev.to/deadbyapril/the-best-cursor-rules-for-every-framework-in-2026-20-examples-29ag)
- [CursorBench 博客](https://cursor.com/blog/cursorbench)
- [Aider GitHub](https://github.com/Aider-AI/aider)
- [Aider 官网](https://aider.chat/)
- [Aider lint-test 文档](https://aider.chat/docs/usage/lint-test.html)
- [Cline GitHub](https://github.com/cline/cline)
- [Cline 官网](https://cline.bot)
- [Cline Auto-Approve 文档](https://docs.cline.bot/features/auto-approve)
- [Cline 2026 评测](https://vibecoding.app/blog/cline-review-2026)
- [Continue GitHub](https://github.com/continuedev/continue)
- [Continue 官网](https://www.continue.dev/)
- [Continue 文档](https://docs.continue.dev/)
- [OpenHands GitHub](https://github.com/OpenHands/OpenHands)
- [OpenHands 官网](https://openhands.dev/)
- [OpenHands Index 发布](https://openhands.dev/blog/openhands-index)
- [OpenHands 2026 评测](https://vibecoding.app/blog/openhands-review)
- [SWE-agent GitHub](https://github.com/SWE-agent/SWE-agent)
- [SWE-agent 文档](https://swe-agent.com/latest/)
- [mini-swe-agent GitHub](https://github.com/SWE-agent/mini-swe-agent)
- [Devin 2.0 VentureBeat](https://venturebeat.com/programming-development/devin-2-0-is-here-cognition-slashes-price-of-ai-software-engineer-to-20-per-month-from-500/)
- [Devin 2.0 官方博客](https://cognition.ai/blog/devin-2)
- [Devin 2.2 官方博客](https://cognition.ai/blog/introducing-devin-2-2)
- [Devin 定价](https://devin.ai/pricing)
