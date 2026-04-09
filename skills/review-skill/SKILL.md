---
name: review-skill
description: 单独执行代码审查（三路并行）。Use when: 用户说"审查/review/code review"。
model: opus
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
