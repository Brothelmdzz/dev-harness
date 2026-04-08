---
name: generic-implement
description: 通用计划执行 — 按 plan 文档逐 Phase 实现代码变更，自动门禁验证。
---

# 通用计划执行

## 核心原则
- 一次只实现一个 Phase
- 每个 Phase 完成后运行门禁
- 发现计划有误时暂停讨论

## 执行流程

### 第一步: 读取 plan
完整阅读 `.claude/plans/` 下的计划文档，定位到当前 Phase。

### 第二步: 执行变更
按计划中的变更清单顺序修改文件。

### 第三步: 运行门禁

自动检测构建命令并执行（`${CLAUDE_PLUGIN_ROOT}` 在 `/dev` 启动时已设置）：

```bash
# 检测技术栈
STACK=$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh" | bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" -c "import sys,json;print(json.load(sys.stdin)['build'])")
eval "$STACK"
```

门禁检查项:
1. 构建通过（build 命令）
2. 测试通过（test 命令）
3. 计划符合度（如有 validate 命令）

### 第四步: 更新状态

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass
```

### 第五步: 继续下一个 Phase
门禁全过 → 直接开始下一个 Phase，不等用户。

## 异常处理

| 场景 | 处理 |
|------|------|
| 构建失败 | 分析错误 → 自动修复 → 重跑 → error_count++ |
| 测试失败 | 分析失败测试 → 修复 → 重跑 |
| 3 次失败 | 停下来报告用户 |
