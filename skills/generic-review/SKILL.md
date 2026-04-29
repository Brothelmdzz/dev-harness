---
name: generic-review
description: 通用代码审查 — 三路并行审查（code-reviewer + security-reviewer + architect），汇总对比。
---

# 通用代码审查

## 约束

- 必须三路并行（code + security + arch），不得串行
- 每路独立输出报告，汇总时保留三方对比
- CRITICAL 问题必须自动修复后重编译验证
- 报告文件必须非空（>500 字节 + 至少 2 个 ## 标题），否则 stop-hook 会打回

## 三路并行

用 `Agent(run_in_background=true)` 同时启动：

| Agent | 侧重 | 产出 |
|-------|------|------|
| review-code | 代码质量、bug、边界条件、可维护性 | `.claude/reports/review-code.md` |
| review-security | SQL 注入、XSS、敏感信息泄露、权限缺失 | `.claude/reports/review-security.md` |
| review-arch | 架构合理性、模块边界、接口设计 | `.claude/reports/review-arch.md` |

每个问题标注 CRITICAL / WARN / INFO 级别。

## 汇总规则

- 任一方 CRITICAL → 自动修复 → 重编译确认
- 多方发现同一问题 → 高置信度，优先修复
- 三方无 CRITICAL → 通过

## 参考

- 报告格式 → 读取 report-template.md
- Agent 启动失败 / 降级 → 读取 playbook-fallback.md

## 产出

汇总到 `.claude/reports/final-review.md`（格式见 report-template.md）。
