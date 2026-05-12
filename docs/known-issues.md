# Known Issues

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
