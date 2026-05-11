# Dev Harness Agents

12 个专用 Agent，**模型异构**（v3.4.1 起，详见 `docs/design-philosophy.md` 原则 7）。

| Agent | 角色 | 模型 | Tools |
|-------|------|------|-------|
| architect | 系统架构评审 | **opus** | Read, Grep, Glob, WebFetch, WebSearch |
| planner | 任务规划分解 | opus | Read, Grep, Glob, WebFetch |
| **code-reviewer** | 代码逻辑审查 | **sonnet** (v3.4.1) | Read, Grep, Glob |
| **security-reviewer** | 安全漏洞检测 | **sonnet** (v3.4.1) | Read, Grep, Glob |
| executor | 代码实现执行 | opus | Read, Write, Edit, Bash, Glob, Grep |
| debugger | Bug 诊断分析 | opus | Read, Bash, Grep, Glob |
| qa-tester | 测试策略设计 | opus | Read, Bash, Grep, Glob |
| auto-loop | 自循环迭代 | opus | Read, Write, Edit, Bash, Glob, Grep |
| wiki-syncer | Wiki 同步 | opus | Read, Bash, Glob, Grep, WebFetch |
| explore | 快速代码搜索 | opus | Read, Grep, Glob |
| gate-checker | 构建门禁验证 | opus | Read, Bash, Glob |
| skill-router | Skill 路由 | opus | Read, Bash, Glob |

模型策略：review 阶段三路使用 sonnet ×2 + opus ×1 形成 Claude 内部异构（消除单模型偏见，成本反而降低）；其他 agent 暂时统一 opus 直到验证可降级。

## Pipeline 分工

```
research  → explore (并行扫描)
plan      → planner (Phase 分解)
implement → executor (代码) + gate-checker (门禁) + auto-loop (循环)
audit     → code-reviewer + security-reviewer
review    → code-reviewer (sonnet) + security-reviewer (sonnet) + architect (opus)
            └─ 三路并行 + 可选第四路 codex 跨厂商对抗 (v3.4.1 A 阶段)
```

## v3.4.1 ABC 配套

- **A** review 双层架构 → 见 `skills/generic-review/SKILL.md` + `scripts/detect-codex.sh`
- **B** Pitfall Journal → `scripts/lib/pitfall.py` + `scripts/pitfall-analyze.py` + `hooks/stop-hook.py` (3 处接入)
- **C** 项目骨架 → `templates/project-skeleton/` (三层规范 + 操作手册 + 运维剧本)

详见 `CHANGELOG.md` 及 `docs/design-philosophy.md`。
