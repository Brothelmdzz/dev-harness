# `code-design/` — 示范层

> 告诉 AI **标准产出长什么样**。这一层不写"禁止什么"（→ `rules/`），只写"我们的标准模板"。

## 为什么需要这一层

仅靠约束层（rules/）会得到「合法但不地道」的代码（得物 *Spec Coding* 实战实测）。
- ❌ 只给约束：AI 知道不能写 SQL 注入，但不知道公司的 Service 分层是怎样的
- ✅ 给完整模板：AI 照着 `crud-page.md` 复刻一份，包含 Service / Repo / DTO 分层

## Harness 思维四原则（得物 *Harness + SDD + 多仓全栈*）

| 原则 | 在示范层的体现 |
|------|---------------|
| 找相似实现 | 让 AI 在 code-design/ 找最近的模板 |
| 复用优先 | 模板里指向已有的 Hook / Service / 类型 |
| 模仿着复制 | "抄一份改一改"优于从零写 |
| 约束生成范围 | prompt 中明确指 `@code-design/api-handler.md` |

## 写法：每个模板的标准结构

```markdown
# [模板名] 示范

## 用途
什么时候用这个模板。

## 完整代码示例
\`\`\`[language]
[完整可运行的代码]
\`\`\`

## 关键决策点
- 为什么这样分层
- 为什么用这个库 / 模式
- 哪些部分是可变的，哪些必须照抄

## 反模式
❌ 这种写法看起来像但其实是错的。

## 衍生场景
- 如果需要 [X]，参考 [模板 Y]
- 如果是 [Z] 场景，整套不适用，参考 [模板 W]
```

## 现有模板

| 文件 | 适用场景 |
|------|---------|
| [`api-handler.md`](api-handler.md) | 后端单接口 Handler / Controller 标准模板 |
| [`react-component.md`](react-component.md) | 前端通用组件标准模板 |
| [`crud-page.md`](crud-page.md) | 完整的 CRUD 页面（前端 + 后端整套） |

## 维护原则

1. **来自真实代码，不预设** — 模板从已经生产稳定运行的代码提炼
2. **保持运行性** — 模板代码必须能直接 copy 出去能跑（占位变量除外）
3. **指明可变 vs 必抄** — 用注释标注 `// 可变：业务逻辑` / `// 必抄：分层结构`

## 不在这里放的东西

- 命名/风格规则 → `rules/`
- 视觉稿 → `ui-design/`
- 运维步骤 → `handbooks/`
- 历史决策记录 → `docs/decisions/`（ADR）

## 链接

- [`.claude/` 总索引](../README.md)
- [得物 *Harness + SDD + 多仓全栈* 案例](../../../docs/external-references-2026-05.md#文章-2得物盖伦基于-harness--sdd--多仓管理模式的-ai-全栈开发实践)
