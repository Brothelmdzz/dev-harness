---
name: generic-tdd
description: TDD 模式实现 — RED-GREEN-REFACTOR 循环，先写测试再写代码。与 implement 阶段集成，强制测试优先。
---

# TDD 模式实现

## 角色
你是 TDD 教练。确保每个功能变更都遵循测试先行的纪律。

## 核心循环

```
RED    → 写一个会失败的测试（描述期望行为）
GREEN  → 写最小代码让测试通过（不多不少）
REFACTOR → 优化代码（测试保持绿色）
COMMIT → 提交这个最小可工作单元
```

## 执行流程

### 第一步: 读取 plan 并定位 Phase
完整阅读 `.claude/plans/` 下的计划文档，定位到当前 Phase。

### 第二步: 为当前 Phase 设计测试

针对 Phase 中的每个变更点:
1. 确定输入/输出预期
2. 写测试用例（正向 + 边界 + 异常）
3. 运行测试，确认**全部失败**（RED）

```bash
# 根据技术栈运行测试
# Java/Gradle: ./gradlew test --tests "XxxTest"
# Python:      pytest tests/test_xxx.py -v
# Node:        npm test -- --testPathPattern=xxx
# Go:          go test ./... -run TestXxx
```

如果测试不失败 → 测试写得有问题，或功能已存在。分析后调整。

### 第三步: 写最小实现

只写让测试通过的最小代码:
- 不添加"顺手"的功能
- 不提前优化
- 不处理测试未覆盖的场景

运行测试，确认**全部通过**（GREEN）。

### 第四步: 重构 (可选)

测试全绿后，审视代码:
- 消除重复
- 改善命名
- 简化逻辑

每次重构后运行测试，确保不破坏。

### 第五步: 运行门禁并更新状态

```bash
# 全量构建 + 测试
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"

# 更新 harness 状态
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass
```

## 反模式（禁止）

| 反模式 | 为什么不行 |
|--------|-----------|
| 先写代码再补测试 | 测试变成橡皮图章，不验证行为 |
| 一次写太多测试 | 失去 RED-GREEN 的快速反馈 |
| 测试依赖实现细节 | Mock 过度，重构即破坏 |
| 跳过 RED 确认 | 可能测试本身就有 bug |
| 重构时加新功能 | 混淆改动意图 |

## 与普通 implement 的区别

| 维度 | 普通 implement | TDD implement |
|------|---------------|---------------|
| 顺序 | 代码 → 测试（可选） | 测试 → 代码 → 重构 |
| 门禁 | build + test | RED确认 + GREEN确认 + build + test |
| 提交粒度 | 按 Phase | 按 RED-GREEN-REFACTOR 循环 |

## 启用方式

在 `.claude/dev-config.yml` 中:
```yaml
tdd: true  # 启用后 implement 阶段使用本 Skill 替代 generic-implement
```
