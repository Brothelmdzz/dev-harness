# Session 交接文档

> 上一次会话: 2026-04-07
> 目录: dev-harness

## 当前状态

**版本**: v3.2-dev (master, 未提交)
**Eval**: 38/38 通过, 10 维度, 加权 100%

## 本次完成的工作

### v3.1 收尾
- 修复 `project_audit_resolution` 测试（测试假设有误，实现正确）
- Hook wrapper 方案：`~/.claude/hooks/dev-harness-stop.py` 通过 `installed_plugins.json` 动态查找路径
- Session 索引：`~/.claude/dev-harness-sessions.json` 自动发现活跃项目
- Web HUD 支持 `--project` 参数和 fallback 扫描
- setup.sh Windows 兼容修复（`$OSTYPE` 检测）
- detect-stack.sh JSON 安全输出

### v3.2 多 Agent 并行架构
- **Layer 1 — 阶段级并行**:
  - `parallel_group` 命名分组替代 `parallel_with` 两两绑定
  - audit + docs + test 三路 background Agent 并行
  - stop-hook 支持并行组：组内部分完成不推进，全完成才推进
- **Layer 2 — 任务级并行 (Orchestrator)**:
  - Phase > 3 时自动触发 Orchestrator 模式
  - Worker 通过 `.claude/workers/worker-*.json` 独立汇报
  - `harness.py worker-report/worker-status/worker-cleanup` 命令
  - 每个 Worker 在独立 worktree 中执行
- **并发安全**: `filelock` 保护 harness-state.json 读写
- **review 三路并行**: skill 内部 3 个 background Agent
- **评测**: 32 → 38 用例, 8 → 10 维度 (新增 parallel_group + worker_management)

## 待做优先级

### 高优先级
1. **提交并发版 v3.2** — 所有改动已完成，评测 100%
2. **实战验证** — 在 ai-capability-hub 项目运行 /dev，验证多 Agent 并行效果
3. **Layer 3 画饼文档** — 跨项目 Agent 编排的设计文档（不实现）

### 中优先级
4. v3.3 多模式架构（pipeline/single/conversation）— evolution-strategy-v4.md Phase 1
5. 通知系统 — pipeline 完成/失败时发桌面/飞书通知
6. README.md 更新 — 反映 v3.2 并行架构

### 低优先级
7. 跨平台 SKILL.md 兼容 (Codex/Gemini CLI)
8. Skill 自进化 (基于 eval 数据自动优化)
