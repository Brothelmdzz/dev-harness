# Skill 编写规范

## 结构（必须）

```
skills/{name}/
  SKILL.md              # 入口：frontmatter + 约束 + 引用
  lang-{language}.md    # 语言特化（如适用）
  framework-{name}.md   # 框架特化（如适用）
  tool-{name}.md        # 工具特化（如适用）
```

## SKILL.md 模板

```markdown
---
name: {name}
description: {一句话描述，<100 字符}
---

# {标题}

## 约束
- {不可违反的规则，用"必须""不得"表达}

## 语言特化（如适用）
检测技术栈后，读取本目录下对应文件：
- Java/Gradle → 读取 lang-java.md
- Python → 读取 lang-python.md

## 状态上报（如适用）
{harness.py 命令}

## 产出
{输出文件路径和格式要求}
```

## 原则

- 约束声明优于步骤指令 — "不跨 Phase 改文件"比"Step 1: 打开文件, Step 2: 修改"更有效
- SKILL.md 不超过 50 行 — 超出部分拆到引用文件
- 语言/框架特化必须拆到独立文件 — Claude 只加载项目对应的那份
- 引用文件用自然语言指引 — "读取 lang-python.md"，不需要特殊语法
- 脚本路径统一用 `${CLAUDE_PLUGIN_ROOT}/scripts/xxx`
