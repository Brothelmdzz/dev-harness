---
name: research
description: 通用代码库研究。并行 subagent 扫描代码库，产出结构化研究文档。Use when: 用户说"研究一下/调研/research"。
model: opus
---

# 代码库研究

## 核心原则
- **不写代码**，只调查、分析、记录
- 所有发现必须有具体文件路径和行号
- 主 agent 做派发和整合，重活甩给 subagent

## 执行流程

### 第一步: 并行派发 subagent

根据项目规模和研究问题，启动 2-4 个并行 explore agent:

| Agent | 扫描范围 |
|-------|---------|
| A | 数据层（Model/Schema/ORM/Entity） |
| B | 业务层（Service/Handler/UseCase） |
| C | 接口层（Controller/Route/API/Handler） |
| D | 配置/基础设施（可选） |

每个 subagent 的 prompt 必须包含用户的研究问题原文和项目根目录。

### 第二步: 整合报告

汇总所有 subagent 的发现，保存到 `.claude/research/{topic}.md`:

```markdown
# {topic} 研究报告

## 数据层发现
## 业务层发现
## 接口层发现
## 关键发现（top 3-5）
## 风险点
```
