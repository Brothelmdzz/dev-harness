---
name: prd
description: Requirement alignment via multi-round dialogue producing a structured what-not-how PRD. Use when the user says PRD, 写需求, 对齐需求. Do not use for technical plan design (plan) or product PRDs with user stories (generic-product-prd).
model: opus
model_context: claude-opus-4.5+
---

# 需求文档 (PRD) 创建

## 核心原则
- PRD 定义"做什么"，不定义"怎么做"
- 通过提问发现用户未想到的边界条件
- 输出结构化文档，下游 plan 阶段可直接使用

## 执行流程

### 第一步: 收集初始信息
用户提供: 功能名称、背景、大致需求。

### 第二步: 多轮对话澄清
针对以下维度提问（按需，不必每个都问）:
- 用户角色和权限
- 核心业务流程（正常路径）
- 异常路径和错误处理
- 数据模型和字段
- 与现有功能的关系
- 非功能需求（性能、安全）

### 第三步: 输出 PRD
保存到 `.claude/project-design/{feature}-prd.md`:

```markdown
# {功能名} 需求文档

## 背景
[为什么要做这个]

## 目标用户
[谁会用]

## 功能需求
### FR-1: [需求点]
[描述]

### FR-2: [需求点]
[描述]

## 非功能需求
[性能、安全等]

## 约束和假设
[已知限制]

## 验收标准
[怎样算做完了]
```
