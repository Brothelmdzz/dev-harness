---
name: validate
description: Plan-conformance validation comparing each planned change to the code and running the plan verification commands. Use when the user says validate, 验证计划, 检查实现, or phases are done and need regression. Do not use for code review (run-review).
model: sonnet
model_context: claude-opus-4.5+
---

# 计划验证

## 执行流程

1. **读取计划**: 完整阅读 plan 文档
2. **检查代码变更**: 对每个 Phase 的每个变更点，定位文件 → 检查是否实施 → 记录差异
3. **运行验证命令**: 执行 plan 中定义的所有验证命令
4. **生成报告**: 保存到 `.claude/reports/{date}-validation.md`

## 报告格式

```markdown
# 实现验证报告

## 验证范围
Plan: {path}, Phase 1-{N}

## 逐项检查
| Phase | 变更点 | 状态 | 说明 |
|-------|--------|------|------|

## 验证命令结果
| 命令 | 结果 |
|------|------|

## 结论
覆盖率: {n}/{total} 变更点已实现
```
