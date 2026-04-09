---
name: test-skill
description: 单独执行测试 — 自动检测测试框架并运行。Use when: 用户说"跑测试/test/run tests"。
model: opus
---

# /test — 执行测试

单 Skill 模式：只运�� test 阶段。

## 执行流程

1. 检测技术栈：`bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"`
2. 初始化状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" \
     init "run-tests" --route C-lite --mode single --skills test
   ```
3. 解析 test Skill：`python "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" test`
4. 按解析到的 Skill 执行测试
5. 更新状态：
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update test DONE
   ```
