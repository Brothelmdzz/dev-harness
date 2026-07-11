---
name: run-review
description: Standalone multi-reviewer code review (parallel code, security, architecture). Use when the user says review, 审查, code review outside a pipeline. Do not use for plan-conformance audit (run-audit).
model: opus
model_context: claude-opus-4.5+
---

# /review — 代码审查

单 Skill 模式：只运行 review 阶段（三路并行审查）。

## 执行流程

1. 初始化状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" \
     init "code-review" --route C --mode single --skills review
   ```
2. 解析 review Skill：`python "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" review`
3. 按解析到的 Skill 执行三路并行审查
4. 汇总报告到 `.claude/reports/final-review.md`
5. 更新状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update review DONE
   ```
