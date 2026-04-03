# Dev Harness Agents

12 个专用 Agent，按 Pipeline 阶段分组。

## 模型路由

| 模型 | 用途 | Agent |
|------|------|-------|
| **haiku** | 快速搜索、门禁检查、路由 | explore, gate-checker, skill-router |
| **sonnet** | 标准实现、调试、测试、安全 | executor, debugger, qa-tester, security-reviewer, wiki-syncer, auto-loop |
| **opus** | 深度推理、架构、审查、规划 | architect, code-reviewer, planner |

## Pipeline 阶段 → Agent 映射

| 阶段 | 主 Agent | 辅助 Agent |
|------|---------|-----------|
| research | explore ×3（并行） | — |
| plan | planner | architect（方案审核） |
| implement | executor / Opus 主进程 | gate-checker（门禁）, debugger（失败时） |
| audit | 由 Skill 驱动 | — |
| test | qa-tester | — |
| review | code-reviewer | security-reviewer（可选第四路） |
| wiki | wiki-syncer | — |
| 全流程 | auto-loop（AutoLoop 模式） | skill-router（启动时） |
