# `handbooks/` — 操作手册

> 长生命周期的「How-to」文档。部署、第三方集成、配置说明、调试技巧。

## 为什么需要这一层

阿里 *Agent 时代生产力悖论* 的核心论点之一：「ALL In Code」——所有 Agent 需要的信息必须在仓库里、版本化。

部署文档放 wiki / 钉钉文档 = 模型看不到 = **不存在**（OpenAI: "Anything an agent cannot access in context at runtime simply does not exist."）。

## 与 `rules/` / `code-design/` 的差异

| 类型 | 时态 | 频率 |
|------|------|------|
| `rules/` | 编写代码时遵守 | 每次 implement |
| `code-design/` | 写代码时模仿 | 每次 implement |
| `handbooks/` | **特定操作时查阅** | 偶尔（部署 / 接入） |
| `runbooks/` | **故障时跟随** | 故障时（罕见但严重） |

## 现有文件

| 文件 | 范围 |
|------|------|
| [`deployment.md`](deployment.md) | 部署流程示例 |

按需扩展：
- `third-party-integration.md` — 接入新第三方时
- `local-dev-setup.md` — 新人本地开发环境
- `db-migration.md` — 数据库迁移流程
- `feature-flag.md` — 功能开关使用规范

## 写法原则

1. **每条步骤可机械执行** — 不要写"配置好 XXX"这种含糊话，写具体的命令/路径/截图
2. **包含失败处理** — 步骤失败时怎么办、怎么排查、找谁
3. **标注最后验证日期** — `Last verified: 2026-05-08`，超过半年没验证 = 标记 STALE

## 链接

- [`.claude/` 总索引](../README.md)
