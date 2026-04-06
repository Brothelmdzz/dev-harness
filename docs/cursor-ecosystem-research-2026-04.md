# Cursor IDE 2026 生态体系深度调研报告

> 调研日期：2026-04-04
> 范围：Cursor 插件体系、Rules/Skills/Hooks/Subagents、MCP、AGENTS.md、各家 Harness 框架 Cursor 集成

---

## 1. Cursor 2026 完整插件体系

### 1.1 版本演进时间线

| 版本 | 日期 | 关键能力 |
|------|------|----------|
| Cursor 2.4 | 2026-01-22 | Subagents + Skills + Image Generation |
| Cursor 2.5 | 2026-02-17 | Plugin Marketplace + Async Subagents + Sandbox Access Controls |
| Cloud Agents | 2026-02-24 | 隔离 VM 中运行自主 Agent，可自测、录屏、产出 PR |
| Self-Hosted Cloud Agents | 2026-03 | 企业级：在自有基础设施中运行 Cloud Agent |

### 1.2 插件系统架构

Cursor 2.5 引入了完整的 **Plugin Marketplace**，插件是一个打包单元，包含五大组件：

```
.cursor-plugin/
├── plugin.json          # 插件清单（manifest）
├── marketplace.json     # marketplace 注册信息
├── skills/              # Agent Skills（SKILL.md + frontmatter）
├── rules/               # Cursor Rules（.mdc 文件）
├── mcp.json             # MCP Server 定义
├── hooks/               # Hooks 配置（hooks.json + 脚本）
└── agents/              # Subagent 定义（markdown + frontmatter）
```

**五大组件**：
1. **Skills** — 领域特定 prompt + 代码，Agent 可自动发现并运行
2. **Subagents** — 专用 Agent，可并行/异步执行，可嵌套 spawn
3. **MCP Servers** — 连接外部工具/API/数据源
4. **Hooks** — 生命周期钩子，观察和控制 Agent 行为
5. **Rules** — 系统级指令，维护编码标准和偏好

### 1.3 安装方式

- **Marketplace UI**：`cursor.com/marketplace` 浏览
- **编辑器内**：`/add-plugin <name>` 一键安装
- **团队市场**：Teams/Enterprise 计划支持私有插件分发

### 1.4 首批生态伙伴

首发合作伙伴：Amplitude、AWS、Figma、Linear、Stripe、Cloudflare、Vercel、Databricks、Snowflake、Hex。截至 2026-03，已扩展至 30+ 插件，包括 Atlassian、Datadog、GitLab、Glean、Hugging Face、monday.com、PlanetScale。

---

## 2. Cursor Rules 最新格式和能力

### 2.1 MDC 格式规范

`.cursor/rules/*.mdc` — Markdown Configuration 格式，每个文件由 YAML frontmatter + Markdown body 组成。

**Frontmatter 验证正则**：
```
^---\ndescription: .+\nglobs: .+\nalwaysApply: (true|false)\n---$
```

**三个核心字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `description` | string | 规则用途的简短描述；Agent 据此决定是否自动加载（"Apply Intelligently"模式） |
| `globs` | string/array | 文件模式匹配，当引用文件匹配时自动附加（"Auto-attach"模式） |
| `alwaysApply` | boolean | `true` = 始终注入上下文（忽略 globs）；`false` = 按条件触发 |

### 2.2 四种规则类型

| 类型 | alwaysApply | globs | description | 触发条件 |
|------|-------------|-------|-------------|----------|
| Always | `true` | 忽略 | 可选 | 每次请求都注入 |
| Auto-attached | `false` | 必填 | 可选 | 当前文件匹配 glob 时自动附加 |
| Agent-requested | `false` | 空 | 必填 | Agent 根据 description 判断是否需要 |
| Manual | `false` | 空 | 空 | 用户手动 @mention |

### 2.3 能力边界

**能做到的**：
- 注入持久上下文到所有 AI 请求（conversation、autocomplete、code generation）
- 按文件类型/路径精确控制规则作用域
- 让 Agent 按需智能加载（基于 description 语义匹配）
- 支持层级：项目级 `.cursor/rules/` + 用户级 `~/.cursor/rules/`

**做不到的**：
- 无法执行代码或触发副作用（纯 prompt 注入，不像 Hooks）
- 无 AST 级别的代码分析能力（是文本匹配，不是结构化分析）
- 无法控制 Agent 行为流程（不像 Hooks 可以拦截/修改）

### 2.4 演进历史

2024: `.cursorrules`（单文件） → 2025-01: `.cursor/rules/*.mdc`（多文件 MDC） → 2026: 集成进 Plugin 体系

---

## 3. Cursor Skills 规范（SKILL.md）

### 3.1 格式

SKILL.md 是开放标准（Agent Skills Specification），跨 Cursor/Claude Code/Codex/Gemini CLI 通用。

```yaml
---
name: my-skill           # 标识符，也是 /slash-command（小写 kebab-case，最长 64 字符）
description: |           # 最关键字段，Agent 据此判断是否自动触发（最长 1024 字符）
  Use when user asks to review code or mentions PR review.
context: fork            # fork = 作为 subagent 运行（隔离上下文）；省略 = inline 运行
allowed-tools:           # 可选：限制 skill 可用的工具
  - Read
  - Edit
metadata:                # 可选元数据
  author: foo
---

# Skill Instructions (Markdown body)

这里是 Agent 触发 skill 后读取的指令...
```

### 3.2 关键设计

- `description` 决定触发，Markdown body 在触发后才加载
- 支持 `disable-model-invocation: true` 仅允许手动调用
- Frontmatter 验证：只允许白名单 key，禁止 `<>` 等注入字符

---

## 4. Cursor Subagents

### 4.1 定义格式

Subagent 是 Markdown 文件 + frontmatter：

| 属性 | 说明 |
|------|------|
| `name` | 标识符 |
| `description` | Agent 发现用途 |
| `model` | `fast` / `inherit` / 指定模型 |
| `readonly` | 是否只读（不修改文件） |
| `is_background` | 是否异步后台运行 |

### 4.2 Async Subagents（2.5 新增）

- 父 Agent 可继续工作，不阻塞
- Subagent 可 spawn 子 Subagent → 形成协调并行工作树
- 适合大规模自主编码场景

---

## 5. Cursor Hooks

### 5.1 生命周期事件

| Hook 事件 | 触发时机 | 用途 |
|-----------|----------|------|
| `beforeSubmitPrompt` | 用户提交 prompt 后、发送给模型前 | 修改/增强 prompt |
| `beforeShellExecution` | 执行 shell 命令前 | 安全检查、命令过滤 |
| `beforeMCPExecution` | 调用 MCP 工具前 | 权限控制 |
| `beforeReadFile` | 读文件前 | 访问控制 |
| `afterFileEdit` | 文件编辑后 | 格式化、lint、验证 |
| `stop` | 任务完成时 | 自动提交、通知 |

### 5.2 与 Claude Code Hooks 对比

| 维度 | Cursor Hooks | Claude Code Hooks |
|------|-------------|-------------------|
| 事件数 | 6 个 | 12 个 |
| Handler 类型 | command only | command + prompt + agent |
| Prompt Hook | 无 | 有（LLM 语义评估） |
| Agent Hook | 无 | 有（深度代码分析） |
| SubagentStop | 无 | 有 |
| PreToolUse/PostToolUse | beforeMCPExecution | PreToolUse + PostToolUse（更细粒度） |
| 跨平台字段 | `additional_context`（顶层） | `hookSpecificOutput.additionalContext` |

**关键差异**：Claude Code 的 prompt/agent 类型 handler 让 hook 可以进行 LLM 语义判断，Cursor 只能执行外部命令。

---

## 6. MCP 支持

### 6.1 配置方式

**项目级**：`.cursor/mcp.json`
**全局级**：`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@some/mcp-server"],
      "env": {
        "API_KEY": "xxx"
      }
    }
  }
}
```

### 6.2 三种传输协议

| 协议 | 适用场景 |
|------|----------|
| stdio | 本地开发、单机实验 |
| SSE (Server-Sent Events) | 分布式团队、远程服务 |
| Streamable HTTP | 推荐用于生产环境（除本地实验外的所有场景） |

### 6.3 生态规模

截至 2026-03，MCP 生态已有 **5000+ 社区构建的 server**。主流服务（GitHub、Postgres、Figma、Slack、Supabase 等）均有官方 MCP server。

### 6.4 工具审批

- 默认：每次 MCP 工具调用需用户审批
- 可开启 auto-run 自动执行（类似终端命令）
- **硬限制**：Cursor 单会话 MCP 工具上限 **40 个**（Claude Code 无此限制）

### 6.5 与 Claude Code MCP 对比

| 维度 | Cursor | Claude Code |
|------|--------|-------------|
| 配置文件 | `.cursor/mcp.json` | `.claude/settings.json` 中 `mcpServers` |
| 工具上限 | 40 个 | 无硬限制 |
| Per-subagent 配置 | 不支持 | 支持 |
| Tool Search | 不支持 | 支持（延迟加载工具 schema） |
| Plugin 内置 MCP | 支持（plugin.json 中 mcp.json） | 支持（.claude-plugin/ 中） |

---

## 7. AGENTS.md 支持

### 7.1 Cursor 原生支持

Cursor **原生读取** AGENTS.md，行为如下：
- 项目根目录 `AGENTS.md` → 作为 rule 应用于整个项目
- 子目录 `AGENTS.md` → 自动应用于该目录及其子目录的文件
- Cursor CLI 同时读取 `AGENTS.md` 和 `CLAUDE.md`，与 `.cursor/rules/` 并列生效

### 7.2 跨工具兼容性

AGENTS.md 已被以下工具支持（截至 2026-03）：
- Claude Code、Cursor、GitHub Copilot、Gemini CLI、Windsurf、Aider、Zed、Warp、RooCode

### 7.3 与其他规则文件的关系

| 文件 | 工具 | 格式 |
|------|------|------|
| `AGENTS.md` | 跨工具通用 | 纯 Markdown |
| `CLAUDE.md` | Claude Code（Cursor CLI 也读取） | 纯 Markdown |
| `.cursor/rules/*.mdc` | Cursor 专用 | YAML frontmatter + Markdown |
| `.cursorrules` | Cursor（已废弃） | 纯文本 |

**推荐策略**：用 `AGENTS.md` 做跨工具通用指令，用 `.cursor/rules/*.mdc` 做 Cursor 特有的精细控制。

---

## 8. Superpowers 在 Cursor 中的使用

### 8.1 安装方式

```
# 在 Cursor Agent Chat 中
/add-plugin superpowers
```

也可在 `cursor.com/marketplace` 搜索 "superpowers" 安装。

### 8.2 集成机制

1. 安装后注册 **SessionStart Hook**（`hooks/hooks.json`）
2. 新会话创建时执行 `hooks/session-start.sh`
3. 注入 `using-superpowers` skill 内容
4. Skills 通过 Cursor 原生 Skill 工具可发现和调用

### 8.3 跨平台兼容

Superpowers 是多平台框架，支持：Claude Code、Codex、OpenCode、Cursor、Gemini CLI、Kiro。

**Hook 兼容层**：
```javascript
// Cursor hooks 期望 additional_context（顶层）
// Claude Code hooks 期望 hookSpecificOutput.additionalContext
// Superpowers 同时输出两者，避免重复注入
```

### 8.4 限制

- 部分用户报告 `/add-plugin superpowers` 找不到引用（marketplace 索引延迟）
- Cursor 的 hook 只支持 command 类型，无法使用 Superpowers 在 Claude Code 中的 prompt/agent hook 能力

---

## 9. OMC (oh-my-claudecode) 在 Cursor 中的使用

### 9.1 OMC 本身

OMC 是 Claude Code 专用的多 Agent 编排框架，**没有直接的 Cursor 支持**。

### 9.2 oh-my-cursor：OMC 的 Cursor 移植版

社区创建了 **oh-my-cursor**（by dasomel），将 OMC 的多 Agent 编排模式移植到 Cursor：

**核心内容**：
- 42 条 Cursor Rules（.mdc 文件）
  - 22 个 Agent 角色
  - 11 个 Workflow 模式
  - 8 个 Practice 标准
  - 1 个 Orchestrator 规则

**安装**：
```bash
npx oh-my-cursor install        # 安装所有规则
npx oh-my-cursor add executor   # 添加单条规则
npx oh-my-cursor list           # 查看安装状态
npx oh-my-cursor doctor         # 诊断安装问题
```

**工作原理**：
- 纯 Cursor Rules 驱动，无外部运行时
- Orchestrator rule 协调一切
- 利用 Cursor 内置 Task subagents 实现多 Agent 模式
- `.omc-cursor/` 目录管理状态

**首次使用注意**：需要手动批准 `~/.cursor/rules/orchestrator.mdc`（Cursor 对文件级 user rules 默认不信任）。

---

## 10. Cursor Cloud Agents 与 Automations

### 10.1 Cloud Agents

在隔离 VM 中运行的全自主 Agent：
- 克隆 repo → 搭建环境 → 写代码测试 → 推送 PR
- 可录制工作过程的视频 demo
- 离线运行，无需用户在线

### 10.2 Automations

事件驱动的自动化系统：
- **触发源**：定时器、代码提交、Slack 消息、外部事件
- **执行方式**：自动 spin up cloud sandbox，执行指令
- **MCP 集成**：可使用已配置的 MCP servers
- **记忆**：可选择记住前次运行结果，持续改进

### 10.3 规模化自主编码

Cursor 内部数据：**30%+ 的合并 PR** 由自主 Cloud Agent 创建。架构上将 Agent 分为 Planner（持续探索代码库、创建任务）和 Worker（专注执行任务），数百个 Agent 可在单一代码库上协作数周。

---

## 11. 各家 Harness 框架 Cursor 集成总览

### 11.1 对比矩阵

| 框架 | 原生平台 | Cursor 支持 | 集成方式 | 成熟度 |
|------|----------|------------|----------|--------|
| **Superpowers** (obra) | Claude Code | 有（Marketplace 插件） | SessionStart Hook + Skills | 高 |
| **oh-my-cursor** (dasomel) | Cursor | 原生 | 42 条 .mdc Rules + CLI 安装 | 中 |
| **oh-my-cursor** (tmcfarlane) | Cursor | 原生 | Rules + Config files | 中 |
| **OMC** (oh-my-claudecode) | Claude Code | 无直接支持 | 需社区移植版 oh-my-cursor | N/A |
| **dev-harness** (本项目) | Claude Code | 待评估 | 需要 Cursor Plugin 适配 | 高 |

### 11.2 Cursor 专有框架

除了移植版，还有 Cursor 原生的编排方案：
- **cursor/plugins** — 官方插件规范和示例
- **awesome-cursor-rules-mdc** — 879 条社区 .mdc 规则集合
- **AgentSkills** (blastum) — Cursor agent skills（SKILL.md 集合）
- **sub-agents-skills** (shinpr) — 跨 LLM subagent 编排作为 Agent Skills

---

## 12. 关键发现与对 dev-harness 的启示

### 12.1 Cursor Plugin 是标准分发方式

dev-harness 若要支持 Cursor，应打包为 `.cursor-plugin/` 格式，包含：
- `plugin.json` manifest
- Skills（将现有 skills/ 转换为 SKILL.md 格式）
- Rules（将 AGENTS.md/CLAUDE.md 核心指令转换为 .mdc）
- Hooks（将现有 hooks/ 适配 Cursor hook 事件名和输入格式）
- MCP（如有，配置 mcp.json）

### 12.2 Hook 体系差异是最大障碍

| Claude Code | Cursor 等价 | 差距 |
|-------------|-------------|------|
| PreToolUse | beforeMCPExecution（仅 MCP 工具） | Cursor 不拦截文件读写等内部工具 |
| PostToolUse | afterFileEdit（仅文件编辑） | 粒度更粗 |
| SubagentStop | 无 | Cursor subagent 完成无 hook |
| prompt handler | 无 | 无法做 LLM 语义评估 |
| agent handler | 无 | 无法做深度代码分析 |

**结论**：dev-harness 的六道防线在 Cursor 上只能实现约 60%。Stop Hook、beforeSubmitPrompt 可以移植，但 prompt/agent 类型 handler 和 SubagentStop 需要降级处理。

### 12.3 AGENTS.md 是最低成本跨平台方案

dev-harness 的 `AGENTS.md` 已被 Cursor 原生读取，无需任何适配即可生效。这是零成本的跨平台基线。

### 12.4 SKILL.md 是跨平台 Skills 标准

Cursor 和 Claude Code 都遵循 Agent Skills 规范（SKILL.md frontmatter 格式），dev-harness 的 skills 可以按此标准统一。

---

## Sources

- [Cursor Marketplace Blog](https://cursor.com/blog/marketplace)
- [Cursor Plugins Reference](https://cursor.com/docs/reference/plugins)
- [Cursor 2.5 Changelog](https://cursor.com/changelog/2-5)
- [Cursor 2.4 Changelog](https://cursor.com/changelog/2-4)
- [Cursor Rules Docs](https://cursor.com/docs/rules)
- [Cursor MCP Docs](https://cursor.com/docs/context/mcp)
- [Cursor Hooks Docs](https://cursor.com/docs/hooks)
- [Agent Skills Specification](https://agentskills.io/specification)
- [AGENTS.md](https://agents.md/)
- [obra/superpowers GitHub](https://github.com/obra/superpowers)
- [dasomel/oh-my-cursor GitHub](https://github.com/dasomel/oh-my-cursor)
- [tmcfarlane/oh-my-cursor GitHub](https://github.com/tmcfarlane/oh-my-cursor)
- [Cursor Cloud Agents Blog](https://cursor.com/blog/scaling-agents)
- [Cursor Self-Hosted Cloud Agents](https://cursor.com/blog/self-hosted-cloud-agents)
- [SKILL.md Format Specification (DeepWiki)](https://deepwiki.com/openai/skills/7.1-skill.md-format-specification)
- [Cursor vs Claude Code 2026 (builder.io)](https://www.builder.io/blog/cursor-vs-claude-code)
- [Cursor Agent Computer Use](https://cursor.com/blog/agent-computer-use)
- [New Plugins Join Cursor Marketplace](https://cursor.com/blog/new-plugins)
- [Cursor Forum: AGENTS.md Support](https://forum.cursor.com/t/support-agents-md/133414)
- [AgentMD for Cursor Forum](https://forum.cursor.com/t/agentmd-making-agents-md-executable-for-cursor-users/153089)
- [Superpowers Cursor Marketplace Page](https://cursor.com/en-US/marketplace/superpowers)
- [Superpowers Cursor Forum Guide](https://forum.cursor.com/t/give-cursor-superpowers/144578)
