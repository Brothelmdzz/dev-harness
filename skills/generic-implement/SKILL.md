---
name: generic-implement
description: 通用计划执行 — 按 plan 文档逐 Phase 实现代码变更，自动门禁验证。
model_context: claude-opus-4.5+
---

# 通用计划执行

## 约束

- 一次只执行一个 Phase，完成后必须上报状态
- 门禁命令必须全部 PASS 才能推进到下一个 Phase
- 不跨 Phase 修改文件（Phase 2 不改 Phase 1 产出的文件）
- 不引入 plan 未声明的新依赖
- 连续失败 3 次必须停下报告用户

## 门禁

门禁命令来源（优先级）:
1. `.claude/dev-config.yml` 的 `gates` 段 → 项目指定
2. `detect-stack.sh` 自动检测 → 通用默认

```bash
STACK_INFO=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh")
```

## 参考

- 门禁失败（build/test 不过）→ 读取 playbook-gate-fail.md

## 状态上报

```bash
# Phase 门禁通过
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS --phase N --gate build=pass --gate test=pass

# 全部 Phase 完成
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement DONE

# 记录错误
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS --phase N --error
```
