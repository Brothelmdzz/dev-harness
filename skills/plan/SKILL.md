---
name: plan
description: Interactive phased implementation-plan design producing a plan doc with per-phase verification commands. Use when the user says plan, 创建计划, 设计方案, or research is done and a plan is needed. Do not use for requirement definition (prd) or execution (generic-implement).
model: opus
model_context: claude-opus-4.5+
---

# 实现计划创建

## 核心原则
- 计划必须基于代码研究的发现
- 每个 Phase 小到可在一次上下文内完成
- 必须定义验证标准（含可运行的命令）

## 执行流程

### 第一步: 理解上下文
读取 `.claude/researches/` 下的研究文档（如有），理解当前代码结构。

### 第二步: 交互式迭代
用 2-4 轮对话与用户确认:
- 第 1 轮: 功能边界、技术偏好
- 第 2 轮: 细化 Phase 任务、依赖关系
- 第 3 轮: 错误处理、测试策略
- 第 4 轮: 确认完整性

### 第三步: 输出计划
保存到 `.claude/plans/{date}-{feature}.md`，格式:

```markdown
# {功能名} 实现计划

## 概述
[一段话描述目标]

## Phase 列表

### Phase 1: {名称}
- Status: PENDING
- 目标: [一句话]
- 改动文件: [列表]
- 验证命令: [具体命令]
- 依赖: 无

### Phase 2: {名称}
- Status: PENDING
- ...

## 风险点
[已识别的风险]
```

### 第四步: 告知下一步
计划保存后告诉用户可以用 `/dev` 开始执行。
