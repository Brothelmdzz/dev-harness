# Known Issues

## v4.5 遗留问题（2026-07-11）

### Codex goal 桥接（app-server JSON-RPC）：明确 NO-GO

**判定：现在不做。** Codex app-server 暴露了 `thread/goal/set` 等 JSON-RPC 方法，
理论上可以从外部（非模型）直接设置/订阅 goal，但：

| 维度 | 现状 | 结论 |
|---|---|---|
| app-server 状态 | experimental，goal 方法未标 stable | 接口还在动 |
| 接口 churn 风险 | `expected_goal_id` 陈旧保护、`GoalRuntimeEvent` 10+ 枚举都是内部实现细节，随版本变 | 维护税高 |
| 外部可控性 | 模型工具只暴露 `create_goal`/`update_goal(complete)`，pause/resume/budget 是系统控、模型和外部都碰不到 | 桥接只能 set + 订阅，控制力弱 |
| 现有替代 | Codex Stop hook 已与 Claude Code 1:1 兼容且已随 `hooks.json` ship | 续跑防线走 Stop 层已经够用，没有桥接的必要收益 |

**GO 的触发条件**（满足以下两者才重启评估）：
1. `codex features list` 里 `goals` 特性方法脱离 experimental；**且**
2. 出现 Stop-hook 层给不了的真实需求——例如需要 `token_budget` 硬上限，
   或跨重启持久化的 goal 状态机（这两点正是 Stop hook 做不到、goal 的
   sqlite 存储能做到的）。

若真要做，最小 spike 形态是一个可选桥接脚本（约 150 行）：起 `codex app-server`
子进程、`thread/goal/set` 一次、订阅 `thread/goal/updated`/`thread/goal/cleared`
通知判断完成——默认不启用，只在 `detect-codex.sh` 探测到 app-server 可用时才暴露。

### 5 项待实测 Spike（穿插在各批次前，各 ≤ 半小时）

以下机制目前都是**按官方文档推断实现，尚未在真机验证过**，标注为待办：

1. **Cursor 事件名大小写金丝雀**（风险最高——Cursor 官方要求 camelCase 如
   `sessionStart`，现有 `.cursor-plugin/hooks.json` 是 PascalCase，意味着
   Cursor 上所有 hook 可能从未真正触发过）。验证法：加一条独特标记的
   camelCase hook，真机对照是否触发。
2. **Codex PostToolUse 工具名**：现有 `hooks.json` 的 PostToolUse matcher
   （`Write|Edit|Bash|Task`）是 Claude Code 的工具名，Codex 侧工具名是否
   一致未验证——不一致会导致 `plan-watcher.py`/`activity-watcher.py`/
   `hud-context.py` 在 Codex 上静默休眠。验证法：注册 match-all PostToolUse
   观察 Codex 实际传入的 `tool_name`。
3. **prompt hook 的 `model` 短别名跨平台解析**：v4.5 新增的 Stop 完成裁判
   hook 用 `"model": "haiku"` 短别名，这个字段在 Codex 侧如何解析（是否
   识别同款短别名、是否需要完整模型 ID）未验证。
4. **Codex Stop hook 信任流程真机验证**：需要真机触发一次 `/hooks` 批准，
   确认 `~/.codex/config.toml [hooks.state]` 落 `dev-harness` 条目、Stop
   确实 block 续跑；顺带验证 `python -c "..."` 引号在 Codex Windows 场景
   下的存活性（是否经过 cmd.exe 转义层）。
5. **双 Stop hook 并行行为**：`hooks.json` 现在同时注册了 command
   （`stop-hook.py`）+ prompt（haiku 完成裁判）两个 Stop hook，需要真机
   观察两者是否真的并行 fire、`reason` 如何合并展示、`stop_hook_active`
   计数是否如预期在两个 hook 间共享（避免其中一个 hook 单独触发死循环
   防线失效）。

### `codex_cli` 检测在本机被判"未就绪"——实测结论：不是版本阈值问题

`scripts/setup_report.py` 的 `codex_cli` 检测项（复用 `detect-codex.sh` 的
退出码）在本机（Windows，codex-cli 0.142.4，配置文件完整）返回 `skip`
（判定未就绪），但直接在交互式 Git Bash 里跑
`bash scripts/detect-codex.sh -v` 返回 `exit 0`（就绪）。已实测复现，**根因
不是 detect-codex.sh 对版本判断过严**，而是两处环境差异叠加：

1. `check_codex_cli` 用 `ctx.plugin_root / "scripts" / "detect-codex.sh"`
   构造路径后直接 `str()` 传给 `subprocess.run(["bash", ...])`——`Path.__str__()`
   在 Windows 上产出反斜杠路径，Git Bash 收到反斜杠路径参数会找不到脚本
   （`rc=127`）。改用 `.as_posix()` 后脚本才能被定位到。
2. 脚本定位到之后，**在 Python subprocess 派生的 bash 子进程里，`codex`
   解析到的是一个 WSL 风格路径**（`/mnt/c/Users/.../codex`），**而不是**
   交互式终端里解析到的 Windows npm 全局安装路径（`/c/Users/.../codex`）；
   前者执行 `codex --version` 会失败，`detect-codex.sh` 因此（正确地）判定
   "codex cli 损坏"并返回未就绪。

即同一台机器、同一个 codex 安装，在两种调用路径下给出不同判定——这是环境
相关的 flakiness，不是"版本判断偏严待放宽"。修复不在本次 Wave 3 范围内
（`scripts/setup_report.py` 不在本次改动的文件所有权内），留给下一次改动
`setup_report.py` 时处理，方向：(a) `check_codex_cli` 改用 `script.as_posix()`；
(b) 排查 Python subprocess 起的 bash 子进程 PATH 顺序为何优先命中 WSL 路径，
必要时显式清理传给子进程的 `PATH`，或改用 `shutil.which("codex")` 在
Python 层直接探测，不依赖子 shell 的 PATH 解析。

---

## v3.4.4 跳过的 LOW 级问题（2026-05-12 全量审查跟进）

> 来源：v3.4.x 全量 0-context code review（commit `60d7db8`）
> 版本归属：v3.4.4 已主动跳过，留下次顺手清理。不阻塞当前功能。

| # | 问题 | 文件 | 影响 | 建议 |
|---|------|------|------|------|
| L1 | `build_pitfall_context` 空 summary 边界（半截 `- [test] `） | `scripts/lib/pitfall.py` | 极低 | 写入路径已保证非空，遗留兼容旧 pitfall 数据 |
| L2 | gate category 白名单（build/test/lint/runtime/deploy）vs `pitfall.py` docstring 列表（含 review，缺 lint）不一致 | `scripts/harness.py` + `scripts/lib/pitfall.py` | 极低 | 二选一统一 |
| L3 | `gates` 字段类型容错——旧 state 可能是字符串 `"pass"`/`"fail"` 而非 bool | `hooks/stop-hook.py` `_build_context_summary` | 低 | 显式比较替代 `if not v` |
| L4 | `web_hud._handle_sse` 在 SSE 顶层用 `sf.stat()` 探测 mtime，没走 `_load_project_state` 白名单 | `scripts/web_hud.py` | 低（只能探测 `.claude/harness-state.json` 是否存在） | 移入白名单检查后 |
| L5 | `web_hud.start_web_hud(bind=...)` 接受 `0.0.0.0` 无警告 | `scripts/web_hud.py` | 低 | 加 LAN 暴露 stderr 提示 |
| L6 | `parse_simple_yaml` 不支持 list/bool/null（所有值都是 string） | `scripts/lib/config.py` | 中（业务代码用 truthy 判断仍 OK，严格比较失败） | 引入真实 YAML 解析或 schema 校验 |
| L7 | `stop-hook.is_context_limit_stop` 关键字 `"context"` 子串匹配过宽 | `hooks/stop-hook.py` | 低 | 收紧 regex |
| L8 | `plan-watcher._update` 重新覆盖 phases 时 gates 字段丢失 | `hooks/plan-watcher.py` | 低 | 保留 gates / completed_at 等附加字段 |

详见 commit `60d7db8` 的 CHANGELOG.md v3.4.4 段 Notes 部分。

---

## v3.2.x 历史已知问题（archive）

> 来源: 2026-04-08 三路代码审查
> 版本: v3.2.x (feat/cursor-compat 分支)
> 注：M3/M8 已在后续 release 修复；M1/M4/M5/M6/M7 部分仍有效，待重新评估。

| # | 问题 | 文件 | 影响 | 建议 |
|---|------|------|------|------|
| M1 | WAITING 状态从未被设置但代码多处引用 | harness.py | 低 | 统一清理或定义 WAITING 语义 |
| M3 | gate 参数 split("=") 已修复为 split("=", 1) | harness.py | 已修 | — |
| M4 | 全局变量 PROJECT_ROOT 在 hud/web-hud 中被修改 | harness.py | 多项目并发时理论上有问题 | 改用参数传递（INFO-A 同款，v3.4.4 审查重申）|
| M5 | generic-implement vs implement 重复 80%+ | skills/ | 维护困难 | 合并或明确分工 |
| M6 | CLAUDE.md 未说明 .claude/ 子目录结构 | CLAUDE.md | 新用户困惑 | 补充表格 |
| M7 | phases 正则不覆盖 Phase01（无空格）等格式 | plan-watcher.py + stop-hook.py | 罕见 | 扩展正则 |
| M8 | stop-hook.py implement 逻辑 stop_hook_active vs 首次触发重复 40 行 | stop-hook.py | 已修 | v3.4.0 _handle_implement_continue 提取 |
