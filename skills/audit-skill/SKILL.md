---
name: audit-skill
description: 单独执行代码审计。Use when: 用户说"审计/audit/检查代码质量"。
model: opus
---

# /audit — 代码审计

单 Skill 模式：只运行 audit 阶段。

## 执行流程

1. 初始化状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" \
     init "code-audit" --route C --mode single --skills audit
   ```
2. 解析 audit Skill：`python "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" audit`
3. 按解析到的 Skill 执行审计，输出报告到 `.claude/reports/audit-*.md`
4. 更新状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update audit DONE
   ```
