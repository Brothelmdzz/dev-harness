# Known Issues (MEDIUM 级，待后续版本修复)

> 来源: 2026-04-08 三路代码审查
> 版本: v3.2.x (feat/cursor-compat 分支)

| # | 问题 | 文件 | 影响 | 建议 |
|---|------|------|------|------|
| M1 | WAITING 状态从未被设置但代码多处引用 | harness.py | 低 | 统一清理或定义 WAITING 语义 |
| M3 | gate 参数 split("=") 已修复为 split("=", 1) | harness.py | 已修 | — |
| M4 | 全局变量 PROJECT_ROOT 在 hud/web-hud 中被修改 | harness.py | 多项目并发时理论上有问题 | 改用参数传递 |
| M5 | generic-implement vs implement 重复 80%+ | skills/ | 维护困难 | 合并或明确分工 |
| M6 | CLAUDE.md 未说明 .claude/ 子目录结构 | CLAUDE.md | 新用户困惑 | 补充表格 |
| M7 | phases 正则不覆盖 Phase01（无空格）等格式 | plan-watcher.py + stop-hook.py | 罕见 | 扩展正则 |
| M8 | stop-hook.py implement 逻辑 stop_hook_active vs 首次触发重复 40 行 | stop-hook.py | 可维护性 | 提取公共函数 |
