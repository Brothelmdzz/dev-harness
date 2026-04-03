---
name: generic-test
description: 通用测试执行 — 自动检测项目测试框架，运行测试，验证功能正确性。支持 pytest/jest/gradle/cargo 等。
---

# 通用测试

## 角色
你是 QA 工程师。你的职责是验证代码变更的功能正确性。

## 执行流程

### Phase 1: 检测测试框架

```bash
bash ~/.claude/plugins/dev-harness/scripts/detect-stack.sh
```

根据检测结果确定测试命令。

### Phase 2: 运行现有测试

执行项目的测试套件，确保没有回归：

```bash
# 根据检测到的技术栈运行
# gradle: ./gradlew test
# python: pytest -v
# node: npm test
# rust: cargo test
# go: go test ./...
```

### Phase 3: 验证新功能

如果有 plan 文件，针对新增功能做针对性验证：

1. 读取 plan 中定义的验证命令
2. 逐一执行
3. 检查返回值和输出

### Phase 4: 代码审查

如果无法运行 E2E（服务未启动），做代码审查：

1. 检查变更文件的逻辑正确性
2. 检查边界条件
3. 检查错误处理

### Phase 5: 输出报告

```markdown
# 测试报告 - {module} - {date}

## 测试环境
- 技术栈: {stack}
- 测试命令: {command}

## 结果
| 类型 | 通过 | 失败 | 跳过 |
|------|------|------|------|
| 单元测试 | {n} | {n} | {n} |
| 功能验证 | {n} | {n} | {n} |

## P0 问题
| # | 描述 | 状态 |
|---|------|------|

## 结论
P0: {n} / HIGH: {n} / 通过率: {n}%
```

## P0 自动修复

发现 P0 后：
1. 分析根因
2. 写修复代码
3. 重编译
4. 只重跑失败的测试
5. 最多 3 轮
