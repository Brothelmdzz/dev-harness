# 审查降级策略

## Agent 启动失败时

三路并行 Agent 如果有一个启动失败：
- 其余两路继续，不等失败的那个
- 失败的维度由你自己做单路审查，输出到对应的报告文件
- 汇总时标注"单路降级"

## 全部 Agent 启动失败时

降级为你自己做单路全面审查：
- 输出到 `.claude/reports/review-code.md`（覆盖 code + security + arch 三个维度）
- 汇总报告中标注"降级为单路审查"

## 获取变更范围

```bash
# 对比当前分支和主分支的 diff
git diff $(git rev-parse --abbrev-ref origin/HEAD 2>/dev/null | sed 's|origin/||' || echo master)...HEAD

# 或最近 N 次 commit
git log --oneline -10
git diff HEAD~5...HEAD
```
