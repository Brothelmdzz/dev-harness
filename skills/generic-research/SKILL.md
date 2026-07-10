---
name: generic-research
description: 通用代码库研究 — 并行 subagent 扫描代码库，产出结构化研究报告。适用于任何项目。
model_context: claude-opus-4.5+
---

# 通用代码库研究

## 约束

- 不写代码，只调查、分析、记录
- 必须并行派发 3 个 Explore Agent（数据层 / 业务层 / 接口层）
- 每个 Agent 的 prompt 必须包含用户的研究问题原文
- 产出必须包含文件路径引用

## 三路并行

| Agent | 扫描范围 |
|-------|---------|
| 数据层 | 数据模型（ORM/Schema/类型定义）、数据库交互 |
| 业务层 | 业务逻辑（Service/Handler/UseCase）、状态机、工作流 |
| 接口层 | API 端点（Controller/路由/GraphQL）、DTO/VO、中间件 |

## 产出

报告输出到 `.claude/researches/{topic}.md`，包含：各层发现（含文件路径）、关键发现（3-5 条）、风险点。
