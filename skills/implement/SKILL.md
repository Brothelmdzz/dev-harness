---
name: implement
description: 按 plan 逐 Phase 实现代码变更 — 委托给 generic-implement。
model: opus
---

# 代码实现

本 Skill 与 `generic-implement` 功能完全一致。
直接按 `generic-implement` 的执行流程操作：读取 plan → 逐 Phase 执行 → 门禁验证 → 更新状态。

调用方式：使用 `dev-harness:generic-implement` Skill 执行。
