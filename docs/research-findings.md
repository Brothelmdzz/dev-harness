# Dev Harness 竞品研究 & 关键发现

> 研究日期：2026-04-04
> 来源：深度对比 OMC / Superpowers / DeerFlow / Ralph Loop 源码和文档

---

## 一、竞品定位总览

| 框架 | Stars | 定位 | 核心差异 |
|------|-------|------|---------|
| **Superpowers** (obra) | ~93k | 开发方法论框架 | TDD 强制 + Socratic Brainstorm + 跨平台 (Codex/OpenCode) |
| **oh-my-claudecode** (OMC) | 数千+ | 多 Agent 编排平台 | 32 agents + tmux 5-worker 并行 + 5 种执行模式 |
| **DeerFlow 2.0** (字节) | #1 Trending | 长时任务 SuperAgent | Docker 容器隔离 + 模型无关 + LangGraph |
| **Ralph Loop** (官方) | - | 自治循环插件 | 最简单的 stop hook + bash while-true 模式 |
| **Dev Harness** (我们) | 新发布 | Pipeline 编排器 | 三层 Skill 解析 + YAML Pipeline + 评测框架 |

**Dev Harness 的独特优势**: 三层 Skill 解析 (L1>L2>L3) 是所有竞品都没有的。

**Dev Harness 的定位**: 不和 Superpowers/OMC 正面竞争，而是作为「Pipeline 编排层」与它们共存。

---

## 二、Stop Hook 不停止的核心技术

### 所有框架用的是同一套 Claude Code 原语

```
Stop Hook stdin → JSON {session_id, stop_hook_active, cwd, ...}
Stop Hook stdout → {"decision": "block", "reason": "..."} 阻止停止
                 → {"continue": true} 允许停止
                 → 空输出 / exit 0 → 允许停止
```

### OMC persistent-mode.cjs 源码关键发现 (43KB)

**1. 从 hook 输入获取项目目录（不依赖 process.cwd()）**
```js
const directory = data.cwd || data.directory || process.cwd();
```
Claude Code 的 Stop Hook stdin 里**已经有 cwd 字段**，不需要自己扫描文件系统。

**2. Context-limit 停止必须放行（否则死锁）**
```js
// 阻止 context-limit 停止会导致死锁：无法 compact 因为无法停止
if (isContextLimitStop(data)) {
    console.log(JSON.stringify({ continue: true, suppressOutput: true }));
    return;
}
```
学习自 OMC issue #213。我们之前的实现是 block 转 remember，会死锁。

**3. 用户主动中断必须尊重**
```js
if (data.user_requested || data.userRequested) return true;
```

**4. Circuit Breaker 模式（熔断器）**
```js
const TEAM_PIPELINE_STOP_BLOCKER_MAX = 20;        // 最多续跑 20 次
const TEAM_PIPELINE_STOP_BLOCKER_TTL_MS = 5 * 60 * 1000; // 5 分钟窗口
const RALPLAN_STOP_BLOCKER_MAX = 30;
const RALPLAN_STOP_BLOCKER_TTL_MS = 45 * 60 * 1000;      // 45 分钟窗口
```

**5. Session ID 隔离**
```js
const sessionId = data.session_id || data.sessionId || "";
if (isSessionMatch(ralph.state, sessionId)) { ... }
```
按 session 隔离状态，防止 session A 的 Hook 影响 session B。

**6. OMC 注册了 11 个生命周期事件 × 20 个 hook 脚本**
```
SessionStart     → session-start.mjs, project-memory-session.mjs
UserPromptSubmit → keyword-detector.mjs, skill-injector.mjs
PreToolUse       → pre-tool-enforcer.mjs
PostToolUse      → post-tool-verifier.mjs, project-memory-posttool.mjs
Stop             → context-guard-stop.mjs, persistent-mode.cjs, code-simplifier.mjs
```

### Ralph Loop 的实现

- Stop Hook 检查 `ralph-state.json` 中的 `active` 和 `iteration`
- 每次续跑 iteration++，达到 max_iterations 时**自动延长 +10**
- 完成信号：Claude 输出 `<promise>` 标签
- **已知 bug**：exit code 2 在 plugin 安装时不生效（#10412），JSON block 可靠

### Superpowers 的做法

- **不用 Stop Hook 自动续跑** — 更保守
- 让用户显式 `/execute-plan` 触发
- 用 `subagent-driven-development` 派 subagent 干活，主进程控制节奏
- 从一开始就在 git worktree 隔离分支上工作

---

## 三、已知 Claude Code Bug

### Plugin Stop Hook exit code 2 不生效 (#10412)

- `.claude/hooks/` 下的 exit code 2 → 正常续跑 ✓
- plugin 安装的 exit code 2 → 显示 "Stop hook prevented continuation" 然后停止 ✗
- **workaround**: 不用 exit code 2，用 `{"decision": "block"}` JSON 输出
- 我们已经用 JSON 输出，不受影响

### Plugin prompt-type hooks 静默忽略 (#13155)

- `type: "prompt"` 的 hooks 在 plugin 安装时不执行
- 只有 `type: "command"` 可靠

### Stop Hook 在 home 目录不触发 (#15629)

- user-level stop hook 在 home 目录下运行时可能不触发

---

## 四、Dev Harness 已完成的修复

### v3.0 (2026-04-04)

1. **Stop Hook 六道防线**: rate limit / context / 阶段超时 / 总时长 / 滑动窗口 / 死循环
2. **从 hook_input.cwd 获取项目目录**: 不再依赖 process.cwd()
3. **Context-limit 放行不 block**: 防死锁
4. **用户中断尊重**: 检查 user_requested
5. **旧格式 State 自动迁移**: `{"stages": {...}}` → `{"pipeline": [...]}`
6. **跨目录项目发现**: 扫描 C:/work/* 找最近活跃的 state
7. **多角色 Profile 路由**: --profile frontend/product/qa
8. **4 个新 Skill**: frontend-implement / frontend-research / product-prd / tdd
9. **脚手架 + 模板 + 文档**: scaffold.sh / 5 个模板 / quickstart / contributing

### 待做 (v3.1)

- [ ] Session ID 隔离（防多 session 干扰）
- [ ] 通知系统（桌面/飞书/Slack webhook）
- [ ] CI/CD 集成（GitHub Actions hook）
- [ ] 更精细的 circuit breaker（每种模式独立次数+TTL）
- [ ] Skill 市场（团队内部共享 + 评分）

---

## 五、SWOT 分析

### Strengths
1. **三层 Skill 解析** — 独创，竞品都没有
2. **YAML Pipeline 可配置** + 路线分级 (B/A/C/C-lite/D)
3. **内置评测框架** — 21 测试 + 加权评分
4. **Rich HUD + Statusline** — CLI 可观测性最佳
5. **三路代码审查** — Codex×2 + Claude 交叉验证

### Weaknesses
1. **零社区** — 没有 stars、没有外部用户
2. **缺 TDD 强制** — 测试是事后环节（已新增 generic-tdd skill 缓解）
3. **文档不足** — 只有 README（已补 quickstart + contributing）

### Opportunities
1. 三层解析是杀手级特性 — 做好了是核心壁垒
2. 企业内部推广不需要 stars — 需要可观测/可配置/可评测
3. 前端/产品 Skill 扩展空间大 — 架构已支持

### Threats
1. Superpowers 93k stars + 官方认可 — 已成事实标准
2. OMC 团队模式 + tmux 并行 — 多人协作更成熟
3. Claude Code 平台 API 变更 — Hook 机制可能改

---

## 六、关键数字

- Claude Code 生态: 2787+ skills, 416+ plugins (claudecodeplugins.io)
- 开发者 AI 工具使用率: 84% 日常使用 (2026)
- Claude 企业市占率: 29%
- Claude Code 预估营收: $2.5B run-rate (2026 Q1)
- Superpowers: ~93k stars, ~2000 stars/day 增长
- OMC: 858 stars/24h 爆发增长
- Agent Skills 开放标准: 8+ 工具支持 SKILL.md 格式
