---
name: implement
description: 通用代码实现。按 plan 文档逐 Phase 实现代码变更，自动门禁验证，自动更新 harness 状态。Use when: 用户说"开始实现/implement/做 Phase X"。
model: opus
---

# 代码实现

## 核心原则
- 一次只实现一个 Phase，完成后直接继续下一个
- 每个 Phase 完成后必须跑门禁
- 发现计划有误时停下来讨论

## 执行流程

### 第一步: 读取 plan
完整阅读 `.claude/plans/` 下的计划文档，定位到当前 Phase。

### 第二步: 执行变更
按计划中的变更清单顺序修改文件。

### 第三步: 运行门禁

```bash
# 检测技术栈（${CLAUDE_PLUGIN_ROOT} 在 /dev 启动时已设置）
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"

# 如果项目有 .claude/dev-config.yml，优先用项目定义的门禁命令
# 否则用检测到的默认命令
```

门禁项: build → test → validate（如有）

### 第四步: 更新 harness 状态

```bash
# 门禁通过
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass

# 门禁失败
python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --error --auto-fixed
```

### 第五步: 继续下一个 Phase
门禁全过 → 直接开始下一个 Phase，**不要停下来等用户**。
3 次失败 → 停下来报告。

## 异常处理

| 场景 | 处理 |
|------|------|
| 构建失败 | 分析错误 → 自动修复 → 重跑门禁 |
| 测试失败 | 分析失败测试 → 修复 → 重跑 |
| 3 次失败 | 停下来报告用户 |
| 计划有误 | 暂停，说明问题，等用户决定 |
