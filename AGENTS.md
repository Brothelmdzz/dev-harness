# Dev Harness Agents

12 个专用 Agent，全部使用 **Opus** 模型。

| Agent | 角色 | Tools |
|-------|------|-------|
| architect | 系统架构评审 | Read, Grep, Glob, WebFetch, WebSearch |
| planner | 任务规划分解 | Read, Grep, Glob, WebFetch |
| code-reviewer | 代码逻辑审查 | Read, Grep, Glob |
| security-reviewer | 安全漏洞检测 | Read, Grep, Glob |
| executor | 代码实现执行 | Read, Write, Edit, Bash, Glob, Grep |
| debugger | Bug 诊断分析 | Read, Bash, Grep, Glob |
| qa-tester | 测试策略设计 | Read, Bash, Grep, Glob |
| auto-loop | 自循环迭代 | Read, Write, Edit, Bash, Glob, Grep |
| wiki-syncer | Wiki 同步 | Read, Bash, Glob, Grep, WebFetch |
| explore | 快速代码搜索 | Read, Grep, Glob |
| gate-checker | 构建门禁验证 | Read, Bash, Glob |
| skill-router | Skill 路由 | Read, Bash, Glob |

## Pipeline 分工

```
research  → explore (并行扫描)
plan      → planner (Phase 分解)
implement → executor (代码) + gate-checker (门禁) + auto-loop (循环)
audit     → code-reviewer + security-reviewer
review    → code-reviewer + security-reviewer + architect (三路并行)
```
