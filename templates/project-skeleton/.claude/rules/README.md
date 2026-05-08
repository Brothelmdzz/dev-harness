# `rules/` — 约束层

> 告诉 AI **禁止什么、必须怎样**。这一层不解决"标准产出长什么样"（→ `code-design/`），只解决"什么写法是错的"。

## 为什么需要这一层

仅靠 prompt 让 AI"写出高质量代码"无效（腾讯 LEGO 实测）。
**结构化约束 vs 模糊期望**：
- ❌ 「写高质量代码」 — AI 自由发挥
- ✅ 「热路径禁止全局 mutex，必须用 per-thread 或分片锁」 — AI 100% 遵循

## 写法：反例免疫格式（必须）

每条规则的标准结构（参考腾讯 *Harness Engineering*）：

```markdown
## 规则 X：[一句话标题]

**补偿的缺口**：模型 [当前的什么倾向 / 默认行为] 会导致 [什么问题]。

**❌ 反例**：
\`\`\`
[具体的错误代码 / 错误命名 / 错误结构]
\`\`\`

**✅ 正例**：
\`\`\`
[正确写法]
\`\`\`

**边界 / 例外**：
- [什么情况下这条规则不适用]
```

仅给规则文字、不给反例和正例 = 模型仍会犯。

## 现有文件

| 文件 | 范围 |
|------|------|
| [`code-naming.md`](code-naming.md) | 文件名 / 函数名 / 变量名 / 接口名 |
| [`code-style.md`](code-style.md) | 缩进 / 引号 / 错误处理 / 空白 |
| [`comments.md`](comments.md) | 何时写注释 / 何时不写 |
| [`structure.md`](structure.md) | 目录分层 / 模块边界 |
| [`safety.md`](safety.md) | 安全纪律（SQL / XSS / 权限 / 密钥） |

## 维护原则

1. **从踩坑中提炼，不预设** — 没踩过的坑不写进来。否则变成死文档。
2. **每条规则可机械验证** — 能写成 lint / grep / AST 检查的，必须配套（不只是文字描述）。
3. **定期回审** — 模型升级后某些规则可能不再需要（设计哲学原则 8）。

## 自动提炼的候选规则（B 阶段引入）

`pitfall-analyze.py` 扫描 `.claude/pitfall-journal.jsonl`，发现 ≥ 3 条同类失败时会生成候选规则：

```
.claude/rules/auto-{category}-{date}.md.candidate
```

候选文件**不会自动生效**，需要人工 review：

| 决策 | 操作 |
|------|------|
| 有价值 | 编辑补全反例/正例 → 改名为 `auto-*.md`（去掉 `.candidate` 后缀） |
| 无价值 | 直接 `rm` 删除 |
| 暂缓决定 | 保留 `.candidate`，下次 analyze 不会重复生成同 category |

手动触发：

```bash
python ${CLAUDE_PLUGIN_ROOT}/scripts/pitfall-analyze.py --project .
# 或调阈值 / dry-run 看看会生成什么
python ${CLAUDE_PLUGIN_ROOT}/scripts/pitfall-analyze.py --threshold 5 --dry-run
```

## 不在这里放的东西

- "标准产出模板" → 去 `code-design/`
- "操作步骤" → 去 `handbooks/` 或 `runbooks/`
- 业务领域知识 → 各业务模块自己的 README

## 链接

- [`.claude/` 总索引](../README.md)
- [腾讯 *Harness Engineering* 安全纪律详细](../../../docs/external-references-2026-05.md#文章-3腾讯lego-团队harness-engineeringai-能在真正出事会炸的后端系统里写代码吗)
