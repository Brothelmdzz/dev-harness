# Dev Harness 贡献指南

## Skill 编写规范

### 文件结构

```
skills/{skill-name}/SKILL.md    # 一个 Skill 一个文件
```

### SKILL.md 模板

```markdown
---
name: 唯一名称（用 scaffold.sh 生成）
description: 一句话描述。Use when: 触发条件。
---

# {Skill 名称}

## 角色
你是 [角色名]。你的职责是 [做什么]，不做 [不做什么]。

## 执行流程

### 第一步: [动作]
[具体步骤]

### 第二步: [动作]
[具体步骤]

## 产出
保存到 `.claude/reports/{skill-name}-{date}.md`

## 约束
- [约束 1]
- [约束 2]
```

### 质量要求

| 要求 | 说明 |
|------|------|
| 长度 | 不超过 200 行（太长浪费上下文） |
| 角色 | 必须有明确的角色定义和边界 |
| 流程 | 3-5 步，每步有具体可执行的内容 |
| 产出 | 必须定义输出文件路径和格式 |
| 约束 | 必须有"不做什么"和"什么时候停" |
| 脚本 | 引用用 `$DH_HOME/scripts/xxx` |

### 不应该包含

- Python/JS 代码（Skill 是指令，不是程序）
- 超过 200 行
- 外部工具依赖安装命令（应在约束中声明，降级处理）
- 硬编码路径（用变量）

## Agent 编写规范

Agent 定义在 `agents/*.md`。

### Model 选择

| 模型 | 用途 | 示例 |
|------|------|------|
| haiku | 快速搜索、简单判断 | explore, gate-checker, skill-router |
| sonnet | 标准实现、调试 | executor, debugger, qa-tester |
| opus | 深度推理、架构 | architect, code-reviewer, planner |

### 约束

- tools 最小化: 只声明需要的工具
- 必须有"不做什么"的约束
- 不直接改代码的 Agent 不应有 Write/Edit 工具

## Pipeline 扩展

### 新增阶段

1. 在 `defaults/pipeline.yml` 加 stage 条目
2. 在 `defaults/skill-map.yml` 加别名映射
3. 在 `scripts/harness.py` 的 `DEFAULT_PIPELINE` 加条目
4. 在 `scripts/harness.py` 的 `ROUTE_STAGES` 加到对应路线

### 新增路线

在 `scripts/harness.py` 的 `ROUTE_STAGES` 添加新路线定义。

## 提交流程

1. Fork 仓库
2. 创建分支: `feature/add-xxx-skill`
3. 编写 Skill/Agent
4. 运行 eval: `python eval/eval-runner.py run-all`
5. 确保通过率 >= 90%
6. 提交 PR
