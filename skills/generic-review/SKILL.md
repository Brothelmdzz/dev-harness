---
name: generic-review
description: 通用代码审查 — 三路并行审查（code-reviewer + security-reviewer + architect），汇总对比。
---

# 通用代码审查（三路并行）

## 角色
你是质量守门人。在代码提交前做最终审查。

## 执行步骤

### 第一步: 获取变更范围

```bash
# 如果在 git 仓库中
git diff $(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null | sed 's|origin/||' || echo master)...HEAD > /tmp/dh-review-diff.txt
# 或者从最近几次 commit
git log --oneline -10
```

### 第二步: 启动三路并行审查

用 Agent tool 的 `run_in_background=true` **同时**启动三个 Agent（不要串行）：

```
Agent 1 (name="review-code", run_in_background=true):
  prompt: "审查以下代码变更。侧重: 代码质量、bug、边界条件、可维护性。
          读取项目中最近的 git diff 或已修改文件。
          输出结构化报告到 .claude/reports/review-code.md
          每个问题标注 CRITICAL / WARN / INFO 级别。"

Agent 2 (name="review-security", run_in_background=true):
  prompt: "审查以下代码变更。侧重: SQL 注入、XSS、敏感信息泄露、权限缺失。
          读取项目中最近的 git diff 或已修改文件。
          输出结构化报告到 .claude/reports/review-security.md
          每个问题标注 CRITICAL / WARN / INFO 级别。"

Agent 3 (name="review-arch", run_in_background=true):
  prompt: "审查以下代码变更。侧重: 架构合理性、模块边界、接口设计、设计模式。
          读取项目中最近的 git diff 或已修改文件。
          输出结构化报告到 .claude/reports/review-arch.md
          每个问题标注 CRITICAL / WARN / INFO 级别。"
```

### 第三步: 等待三路完成

三个 background Agent 完成时会自动通知你。全部完成后继续第四步。

**降级**: 如果 Agent 启动失败，降级为你自己做单路审查，输出到 `.claude/reports/review-code.md`。

### 第四步: 汇总三份报告

读取三份报告，生成 `.claude/reports/final-review.md`:

```markdown
# 代码审查汇总

## CRITICAL 问题（必须修复）
| # | 问题 | 发现方 | 文件 | 行号 |
|---|------|--------|------|------|

## WARN 问题（建议修复）
...

## 汇总结论
- [x] 通过 / [ ] 不通过
```

### 第五步: 自动修复 CRITICAL

如果有 CRITICAL 问题，自动修复后重新编译验证。

## 汇总规则

| 情况 | 处理 |
|------|------|
| 任一方发现 CRITICAL | 自动修复 → 重编译确认 |
| 多方发现同一问题 | 高置信度，优先修复 |
| 仅一方发现且非 CRITICAL | 留档标注"单方发现" |
| 三方无 CRITICAL | 通过 |

## 产出

`.claude/reports/final-review.md` — 必须包含三方对比表。

**注意**: stop-hook 会验证报告文件是否存在且非空（>100 字节）。没有有效报告就标记 review DONE 会被打回。
