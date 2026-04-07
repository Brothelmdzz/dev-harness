---
name: generic-review
description: 通用代码审查 — 三路并行审查（code-reviewer + security-reviewer + architect），Opus 汇总对比。
---

# 通用代码审查（三路并行）

## 角色
你是质量守门人。在代码提交前做最终审查。

## 审查范围

```bash
git diff master...HEAD
```

## 执行方式

同时启动三路审查 Agent（用 `run_in_background=true` 并行）：

```
1. Agent(name="review-code", run_in_background=true):
   prompt: "审查以下 git diff，侧重: 代码质量、bug、边界条件、可维护性。
            输出结构化报告到 .claude/reports/review-code.md
            格式: 每个问题标注 CRITICAL / WARN / INFO 级别"

2. Agent(name="review-security", run_in_background=true):
   prompt: "审查以下 git diff，侧重: SQL 注入、XSS、敏感信息泄露、权限缺失、OWASP Top 10。
            输出结构化报告到 .claude/reports/review-security.md
            格式: 每个问题标注 CRITICAL / WARN / INFO 级别"

3. Agent(name="review-arch", run_in_background=true):
   prompt: "审查以下 git diff，侧重: 架构合理性、模块边界、接口设计、设计模式。
            输出结构化报告到 .claude/reports/review-arch.md
            格式: 每个问题标注 CRITICAL / WARN / INFO 级别"
```

等待三路全部完成后，汇总三份报告。

**降级**: 如果 Agent 启动失败或超时，降级为单路 code-reviewer 审查。

## 汇总规则

| 情况 | 处理 |
|------|------|
| 任一方发现 CRITICAL | 自动修复 → 重编译确认 |
| 多方发现同一问题 | 高置信度，优先修复 |
| 仅一方发现且非 CRITICAL | 留档标注"单方发现" |
| 三方无 CRITICAL | 通过 |

## 产出

`.claude/reports/final-review.md` — 三方对比表和汇总结论。
