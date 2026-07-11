---
name: generic-audit
description: Spec-conformance audit comparing plan/PRD against the implementation for quality, security, consistency. Use when the pipeline enters the audit stage. Do not use for line-level code review (generic-review).
model_context: claude-opus-4.5+
---

# 通用代码审计

## 约束

- 必须对比 plan/PRD 与实际代码，不凭印象审计
- HIGH 问题必须自动修复后重编译验证
- 报告必须非空（>500 字节 + 至少 2 个 ## 标题），否则 stop-hook 打回

## 审计维度

| 维度 | 检查内容 | 严重级别 |
|------|---------|---------|
| 需求覆盖 | plan 中每个变更点是否都已实现 | HIGH |
| 代码质量 | 空指针、资源泄露、异常处理、边界条件 | MEDIUM-HIGH |
| 安全性 | SQL 注入、XSS、敏感信息泄露、权限校验 | HIGH |
| 错误处理 | 异常是否正确捕获和上报 | MEDIUM |
| 一致性 | 命名规范、代码风格、项目约定 | LOW |

## 参考

- 报告格式 → 读取 report-template.md

## 产出

`.claude/reports/audit-{module}-{date}.md`（格式见 report-template.md）。
