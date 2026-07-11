---
name: ask
description: Read-only Q&A that creates no harness state and arms no stop-hook. Use when the user says ask, 问一下, 聊聊, or wants an answer without starting a pipeline. Do not use when a file will change (fix, dev-pipeline).
model_context: claude-opus-4.5+
---

# /ask — 对话模式

conversation 模式：纯问答，不走 pipeline。

## 行为

- **不创建** harness-state.json
- **不触发** stop-hook 自动续跑
- 直接回答用户问题
- 如果涉及代码，可以读取和搜索，但不修改
- 用户想切到开发模式时，引导使用 `/dev` 或 `/fix`
