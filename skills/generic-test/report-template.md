# 测试报告模板

输出到 `.claude/reports/test-{module}-{date}.md`：

```markdown
# 测试报告 - {module} - {date}

## 测试环境
- 技术栈: {stack}
- 测试命令: {command}
- 运行时长: {duration}

## 结果
| 类型 | 通过 | 失败 | 跳过 |
|------|------|------|------|
| 单元测试 | {n} | {n} | {n} |
| 功能验证 | {n} | {n} | {n} |

## P0 问题
| # | 描述 | 文件 | 状态 |
|---|------|------|------|
| 1 | {描述} | {file:line} | FIXED / OPEN |

## 结论
P0: {n} / HIGH: {n} / 通过率: {n}%
```
