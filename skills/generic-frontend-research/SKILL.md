---
name: generic-frontend-research
description: 通用前端代码库研究 — 并行 subagent 扫描前端代码结构，产出结构化研究报告。
model_context: claude-opus-4.5+
---

# 通用前端代码库研究

## 约束

- 不写代码，只调查、分析、记录
- 必须并行派发 3 个 Explore Agent（组件层 / 路由页面层 / 数据状态层）
- 每个 Agent 的 prompt 必须包含用户的研究问题原文
- 产出必须包含文件路径引用（不是凭记忆描述）

## 三路并行

| Agent | 扫描范围 |
|-------|---------|
| 组件层 | 组件树结构、Props/类型、组件通信、UI 组件库 |
| 路由/页面层 | 路由配置、页面结构、布局、权限守卫、SSR/SSG |
| 数据/状态层 | Store/Context、API 调用层、数据流、缓存策略 |

## 产出

报告输出到 `.claude/researches/{topic}-frontend.md`，包含：技术栈摘要、各层发现（含文件路径）、关键发现（3-5 条）、风险点。
