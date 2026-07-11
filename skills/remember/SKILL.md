---
name: remember
description: Memory capture distilling a session's key work, decisions, and lessons into searchable notes. Use when the user says remember, 收工, 保存进度, or a major task finishes. Do not use for project docs/README (generic-docs).
model: sonnet
model_context: claude-opus-4.5+
---

# 记忆保存

## 核心原则
- 提炼精华，不复制粘贴对话
- 每条记忆 1-3 句话，面向「未来的自己」写
- 敏感信息（密码/API key）禁止写入

## 提取维度

| 类型 | 什么值得记 |
|------|-----------|
| work-log | 完成了什么功能、改了哪些文件 |
| decision | 重要技术决策及理由 |
| lesson | 踩坑经验（触发→错误→正确→检查清单） |
| context | 项目当前状态、未完成工作 |

## 执行流程

1. 回顾当前对话，提取记忆条目
2. 质量自检（搜索命中率、信息密度、独立性）
3. 保存（如果有 Mem0: `python ~/.claude/memory/mem0_client.py add`）
4. 如果没有 Mem0，保存到 `.claude/memory/` 目录下的 Markdown 文件
5. 告诉用户保存了什么，建议下次新会话的开场白
