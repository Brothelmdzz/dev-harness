---
name: ask
description: 纯对话问答模式 — 不创建 harness 状态，不触发 stop-hook。Use when: 用户说"问一下/ask/聊聊"。
---

# /ask — 对话模式

conversation 模式：纯问答，不走 pipeline。

## 行为

- **不创建** harness-state.json
- **不触发** stop-hook 自动续跑
- 直接回答用户问题
- 如果涉及代码，可以读取和搜索，但不修改
- 用户想切到开发模式时，引导使用 `/dev` 或 `/fix`
