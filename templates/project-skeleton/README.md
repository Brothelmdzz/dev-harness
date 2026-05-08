# 项目骨架（Project Skeleton）

> dev-harness 推荐的项目级目录结构。把这套骨架复制到新项目根，让 Agent 在每个阶段都能找到它需要的上下文。

## 这是什么

「ALL In Code」哲学的具体落地（详见 [`docs/design-philosophy.md`](../../docs/design-philosophy.md) 原则 4）。

**目标**：让 Agent 工作所需的全部信息都在仓库内、版本化、可被 grep 到。

不在仓库内的就等于不存在 —— OpenAI *Harness Engineering*：「Anything an agent cannot access in context at runtime simply does not exist.」

## 三层规范体系

参考得物 *Spec Coding 实战*（见 `docs/external-references-2026-05.md` 文章 1）的三层划分：

| 层 | 目录 | 解决的问题 |
|---|------|-----------|
| **约束层** | `.claude/rules/` | "AI 写出来的代码合法但不地道" → 告诉它禁止什么 |
| **示范层** | `.claude/code-design/` | "AI 不知道我们的标准产出长什么样" → 给它看模板 |
| **视觉层** | `.claude/ui-design/` | "AI 不知道页面应该长什么样" → 给它 HTML 高保真稿 |

外加两类「ALL In Code」资产（参考阿里 *Agent 时代生产力悖论*）：

| 类型 | 目录 | 用途 |
|------|------|------|
| 操作手册 | `.claude/handbooks/` | 部署、配置、第三方接入等长生命周期文档 |
| 运维剧本 | `.claude/runbooks/` | 故障响应、恢复流程 |
| 发布信息 | `docs/release-notes/` | 版本变更说明 |
| 踩坑日志 | `.claude/pitfall-journal.jsonl` | （B 阶段引入）失败案例自动归档 |

## 用法

### 初次使用

```bash
# 在新项目根下
cp -r ${CLAUDE_PLUGIN_ROOT}/templates/project-skeleton/.claude .
cp -r ${CLAUDE_PLUGIN_ROOT}/templates/project-skeleton/docs/release-notes docs/
```

或者运行（计划中的脚手架命令）：

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.sh --skeleton
```

### 持续维护

按照各 README 指引，**逐步**填充各层。**不要一次性写完所有规则** —— 规则应该从踩坑中提炼，否则会变成"看上去工程化"的死文档。

## 设计原则

每个文件、每个目录、每条规则必须能回答：**"它补偿了模型当前的什么缺口？"**

无法回答 = 删除候选。模型升级后定期回审。

## 与 dev-harness pipeline 的关系

| Pipeline 阶段 | 主要消费 |
|--------------|---------|
| `research` | 整个 `.claude/` 用于了解项目约束 |
| `plan` | `code-design/` 提供模板、`rules/` 提供约束 |
| `implement` | 全部三层 + handbooks/runbooks |
| `audit` / `review` | `rules/` + 历史 `pitfall-journal.jsonl` |
| `test` | `runbooks/` |
| `remember` | 写入 `pitfall-journal.jsonl` 与 `release-notes/` |

## 链接

- [设计哲学](../../docs/design-philosophy.md)
- [外部参考文献](../../docs/external-references-2026-05.md)
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [OpenAI: Harness Engineering](https://openai.com/index/harness-engineering/)
