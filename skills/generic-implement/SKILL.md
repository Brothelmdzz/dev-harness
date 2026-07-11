---
name: generic-implement
description: Plan-driven implementation executing a plan doc phase by phase with automatic build/test gates. Use when the pipeline enters the implement stage and a plan exists. Do not use without a plan (plan) or for frontend (generic-frontend-implement).
model_context: claude-opus-4.5+
---

# 通用计划执行

## 约束

- 一次只执行一个 Phase，完成后必须上报状态
- 门禁命令必须全部 PASS 才能推进到下一个 Phase
- 不跨 Phase 修改文件（Phase 2 不改 Phase 1 产出的文件）
- 不引入 plan 未声明的新依赖
- 连续失败 3 次必须停下报告用户

## 连续执行（违纪红线）

不在 Phase 之间停下和用户 check-in。按 plan 执行完全部 Phase，唯一可停的三种情形：BLOCKED 且无法自解 / 真正阻断推进的歧义 / 全部 Phase 完成。"要我继续下一个 Phase 吗？"式提问是在浪费用户时间——plan 已经写清了每个 Phase，执行就是了。

| 借口 | 现实 |
|------|------|
| "Phase 间停下汇报更稳妥" | `update --phase` 已是唯一进度源，停下=摆烂 |
| "这个 Phase 有点不确定，先问问" | 不确定≠阻断。记 pitfall、按最简可工作版本推进 |
| "剩下的 Phase 让用户确认下" | plan 已是批准的执行契约；连续失败 3 次才停 |

红旗：写了"已完成 Phase N，是否继续"、用散文复述"接下来我会…"代替真的调用 `harness.py update`——出现即代表在摆烂。

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

## Phase 完成契约（必填，缺一不可）

每个 Phase 完成时逐项确认，缺一不可：

- [ ] 产出文件已按 plan 变更清单落盘
- [ ] 门禁结果：build=`<pass/fail>` test=`<pass/fail>`（全部 PASS 才能推进）
- [ ] 已执行 `harness.py update implement IN_PROGRESS --phase N --gate ...`  ← 未执行本行禁止进入下一 Phase
