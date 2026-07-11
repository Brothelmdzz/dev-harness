---
name: fix
description: "Fast single-pass bug fix: implement plus test only, no research or plan. Use when the user says fix, 修一下, 快速修复, or wants one small defect fixed and verified. Do not use for multi-phase features (dev-pipeline)."
model: opus
model_context: claude-opus-4.5+
---

# /fix — 快速修复

单 Skill 模式：implement + test，不走完整流程。

## 执行流程

1. 检测技术栈：`bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"`
2. 初始化状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" \
     init "{用户描述的问题}" --route C-lite --mode single --skills implement,test
   ```
3. 分析问题，定位代码，实施修复
4. 运行门禁（build + test）
5. 更新状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement DONE
   ```
6. 如果测试通过，更新 test 状态并完成
