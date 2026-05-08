# `.claude/` — Agent 工作空间

> 项目内所有给 Agent 看的内容都放在这里。git-tracked，版本化。

## 子目录索引

| 目录 / 文件 | 用途 | 何时读 |
|------------|------|-------|
| [`rules/`](rules/README.md) | 约束层 — 编码规范、命名、目录结构、安全纪律 | 每次 implement 前 |
| [`code-design/`](code-design/README.md) | 示范层 — 标准产出模板（CRUD / 组件 / Handler） | plan + implement |
| [`ui-design/`](ui-design/README.md) | 视觉层 — HTML 高保真稿、组件草图 | 前端 implement |
| [`handbooks/`](handbooks/README.md) | 操作手册 — 部署、第三方集成、配置说明 | 涉及部署/集成时 |
| [`runbooks/`](runbooks/README.md) | 运维剧本 — 故障响应、恢复流程 | incident / on-call |
| `pitfall-journal.jsonl` | 踩坑日志 — 失败案例自动归档（B 阶段启用） | implement / review |

## 运行时产物（review 阶段会写到这里）

| 路径 | 内容 |
|------|------|
| `reports/review-code.md` | code-reviewer (sonnet) 输出 |
| `reports/review-security.md` | security-reviewer (sonnet) 输出 |
| `reports/review-arch.md` | architect (opus) 输出 |
| `reports/review-cross-vendor.md` | 可选 — 装了 codex cli 时由 codex 跑（GPT/GLM/o3 等） |
| `reports/final-review.md` | 三/四路汇总，含异构视角发现 |

跨厂商对抗审查由 `dev-config.yml` 的 `review.cross_vendor.enabled` 控制（默认 `auto`：检测到 codex 自动启用；没装静默跳过）。

## 设计原则

1. **每个文件 ≤ 200 行** — 渐进披露（设计哲学原则 3）。超长就拆 references/。
2. **每条规则带「补偿什么缺口」** — 不能回答 = 删除候选。
3. **JSON 优于 Markdown 作状态** — 模型不会随便覆写 JSON（Anthropic 经验）。

## 不在这里放的东西

- 运行时产物（state / lock / worktrees） — 已被 `.gitignore` 排除
- 真实业务数据 / 客户信息 → 应进 secrets 系统
- 临时实验代码 → 应进各业务模块

## 链接

- [项目骨架总入口](../README.md)
- [设计哲学](../../../docs/design-philosophy.md)
