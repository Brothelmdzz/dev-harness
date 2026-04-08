---
name: generic-frontend-research
description: 通用前端代码库研究 — 并行 subagent 扫描前端代码结构，产出结构化研究报告。
---

# 通用前端代码库研究

## 角色
你是前端代码考古学家。不写代码，只调查、分析、记录。

## 执行流程

### 第一步: 并行派发 subagent

启动 3 个并行 Explore Agent:

| Agent | 职责 |
|-------|------|
| A: 组件层 | 扫描组件树结构、Props/类型定义、组件通信模式、UI 组件库使用 |
| B: 路由/页面层 | 扫描路由配置、页面结构、布局系统、权限/守卫、SSR/SSG 配置 |
| C: 数据/状态层 | 扫描状态管理（Store/Context）、API 调用层、数据流、缓存策略 |

每个 Agent 的 prompt 必须包含用户的研究问题原文。

### 第二步: 整合报告

汇总三个 Agent 的发现，输出到 `.claude/researches/{topic}-frontend.md`:

```markdown
# {topic} 前端研究报告

## 技术栈
- 框架: {React/Vue/Angular/Next.js/...}
- UI 库: {Ant Design/Element Plus/MUI/Tailwind/...}
- 状态管理: {Redux/Zustand/Pinia/Vuex/...}
- 构建工具: {Vite/Webpack/Turbopack/...}

## 组件层发现
- 组件目录结构: {描述}
- 核心组件: {列表，含文件路径}
- 组件通信模式: {Props/Events/Context/Store}

## 路由/页面层发现
- 路由结构: {描述}
- 页面列表: {列表，含文件路径}
- 布局系统: {描述}
- 权限控制: {描述}

## 数据/状态层发现
- API 调用方式: {fetch/axios/SWR/React Query/...}
- 状态管理架构: {描述}
- 数据流向: {描述}

## 关键发现
{最重要的 3-5 个发现}

## 风险点
{可能影响实现的问题}
```
