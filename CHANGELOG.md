# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.4.3] — 2026-05-11

### Added — v4.0 Gate Feedback Loop（Phase 1 第一刀）

- **`harness.py update --gate xx=fail` 自动入 pitfall journal**（`scripts/harness.py` cmd_update）：失败的 `build` / `test` / `lint` / `runtime` / `deploy` 类 gate 会调 `lib.pitfall.capture_failure()` 写入 `.claude/pitfall-journal.jsonl`，下次 stop-hook 续跑时 `build_pitfall_context()` 自动把它当 ground truth 注入到 block reason 末尾。
- **新增 `--gate-detail` CLI 参数**（`scripts/harness.py`）：格式 `--gate-detail name=具体错误信息`，可重复，跟 `--gate` 对应。失败时写入 pitfall 的 `summary` + `root_cause`，让 agent 续跑时直接看到"test failed at auth.test.ts:42 expected 200 got 401"而不是空洞的"test failed"。
- **stop-hook `_build_context_summary` 显示 IN_PROGRESS phase 的失败 gate**（`hooks/stop-hook.py`）：原先只在 phase `DONE` 时显示 gates；现在 `IN_PROGRESS` 时也强调失败的 gate（`(FAIL: test, lint)`），失败的 gate 是 agent 当前最需要的 ground truth。

### Changed

- **`build_pitfall_context()` 去重 + 截断**（`scripts/lib/pitfall.py`）：原先无脑拼接"summary（根因: root_cause）"，导致 `--gate-detail` 写入时 summary 经常是 root_cause 的截断前缀，输出重复占 prompt 空间。现在 summary 跟 root_cause 完全相同或互为前缀时省略根因，root_cause 超过 200 字符自动截断+省略号。
- **`docs/roadmap-v4.md` 1.2 标 `[DONE in v3.4.3]`**：补充落地说明，记录实际实现路径跟原方案的差异（没新增 PostToolUse hook，而是 hook 进 cmd_update + 复用已有 pitfall 闭环），防止未来 Claude 读 roadmap 重复造轮子。

### Design Reference

这是 `docs/roadmap-v4.md` Phase 1 (Agent Eyes) 1.2 Gate Result Feedback Loop 的最小落地。关键洞察：闭环已经存在（v3.4.1 Pitfall + v3.4.2 nudge），缺的只是接通 build/test → pitfall journal 这条线。三处改动 < 40 行代码，但闭合了"失败信号 → 自动记录 → 续跑前注入"完整链路。

跳过 1.1 Pipeline Context Injection 的原因：PostToolUse 每次工具调用都触发频率过高，需要先有 eval 数据再判断 ROI。

---

## [3.4.2] — 2026-05-11

### Added — 防摆烂三件套

- **`/dev` 启动声明强制**（`skills/dev/SKILL.md`）：顶部新增"启动声明（必读 · 不可跳过）"段，第一条回复必须以 `Using dev-harness:dev skill — running Step 0 now.` 开头并同一回复内立即并行执行 Step 0 三条 Bash。明令禁止"按 X 流程启动"的抽象总结代替执行。同源 superpowers `executing-plans` skill 的 "Announce at start" 模式。
- **Plan 阶段 fallback 二态**（`defaults/pipeline.yml` + `templates/dev-config-minimal.yml`）：plan 阶段新增 `fallback: wait | auto-approve | skip`（默认 `wait`）。用户可在 `.claude/dev-config.yml` 通过 `plan.fallback` 覆盖，解决"严肃任务要审批 vs 微小变更想直推"的产品决策歧义。设计参考 mbruhler `.flow` DSL 的 `@review + fallback` 二态思路。
- **Stop-Hook 软提醒分级层**（`hooks/stop-hook.py`）：防线 3/4/5 首次触发 → advisory + 续跑（让 Claude 自纠偏）；同 stage 内再次触发 → 原硬停逻辑。stage 切换时计数器自动重置。设计精神同源 barkain/claude-code-workflow-orchestration 的 adaptive nudge，但保留 dev-harness 独有的"硬续跑"差异化（不引入 PreToolUse hook，沿用现有 6 道防线架构）。

### Changed

- `defaults/skill-spec.md`：SKILL.md 行数硬上限 50 → **200 行**，与 `docs/design-philosophy.md` 红线 4 对齐；推荐 < 80 行，超出拆 `resources/`。
- `AGENTS.md`：v3.4.1 模型异构表（code-reviewer / security-reviewer 改 sonnet，architect 留 opus）+ ABC 配套段落补齐。

### Design Reference

三件套取舍基于 2026-05-11 完成的《Coding Agent Harness 框架：纵向五幕剧 × 横向六层江湖》横纵分析报告（私有 `.design/coding-agent-harness_横纵分析报告.md`），覆盖 19 个同类项目对比。结论：抄 Superpowers Announce / mbruhler fallback / barkain nudge 精神；明确不抄 catlog22 multi-CLI / mbruhler DSL / Aider git-as-state（详见报告第 4.4 节三剧本推演）。

---

## [3.4.1] — 2026-05-08

### Added — v4 ABC three-pillar foundation

- **C: Project skeleton** — `templates/project-skeleton/` ships a 20-file three-layer regulation directory:
  - `rules/` (constraint layer): naming, style, comments, structure, safety — counter-example immune format
  - `code-design/` (demonstration layer): api-handler, react-component, crud-page templates
  - `ui-design/` (visual layer): HTML high-fidelity mockup
  - `handbooks/` + `runbooks/` + `pitfall-journal.jsonl` for ALL-In-Code persistence
- **A: Multi-model adversarial code review**:
  - Layer 1 (always-on): `code-reviewer` and `security-reviewer` switched from `opus` to `sonnet`; `architect` stays `opus` — heterogeneous Claude trio costs less than the previous all-`opus` setup
  - Layer 2 (optional): `scripts/detect-codex.sh` + `skills/generic-review/SKILL.md` cross-vendor review via `codex exec --skip-git-repo-check --output-last-message`
  - `dev-config.yml` `review.cross_vendor.enabled: auto | true | false`
- **B: Pitfall Journal closed loop**:
  - `scripts/lib/pitfall.py` core library — `capture_failure` / `build_pitfall_context` / `find_promotable`
  - `scripts/pitfall-analyze.py` CLI — `--threshold N` clusters recurring failures into `.claude/rules/auto-*.md.candidate` (not auto-promoted; humans decide)
  - `hooks/stop-hook.py` 3-line addition: ground-truth injection on resume, capture on audit/review report rejection
- `eval/scenarios/` — 5 baseline real-task scenarios as ABC regression tests
- `docs/design-philosophy.md` — eight principles + nine red lines
- `docs/external-references-2026-05.md` — 5 industry case studies (Dewu × 2, Tencent × 2, Alibaba)

### Changed

- `.gitignore` — `docs/` is now file-level (`docs/*` + whitelist) so `design-philosophy.md`, `external-references-2026-05.md`, `quickstart.md`, `contributing.md`, `known-issues.md` are publishable while research drafts stay local.
- `CLAUDE.md` synced with v4 ABC sections (Code Review double-layer, Pitfall Journal closed loop, directory structure additions).

### Fixed

- `pitfall-analyze.py` no longer crashes on Windows `cmd.exe` (GBK default codepage) when emitting Unicode — added `sys.stdout.reconfigure(encoding="utf-8")`.

---

## [3.5.0] — 2026-04 (commit `87e782d`)

> Note: this version was committed but plugin metadata was never bumped past 3.4.0; treat as superseded by 3.4.1.

- 安全加固 + Skill 渐进披露 + 架构精简

## [3.4.0] — 2026-04 (commit `babf54c`)

- 93 项审计修复 + 共享库（`scripts/lib/`）+ 架构清理
- 共享库消除 14 处代码重复，统一 state 读写、项目根发现、DAG 遍历、Phase 解析
- 原子状态写入：所有 `harness-state.json` 写入路径统一使用 `.tmp` + `os.replace()`，防止 hook 超时导致文件损坏
- Pipeline DAG：`depends_on` 字段声明阶段显式依赖，拓扑排序 + 环检测
- 防线参数可配：`dev-config.yml` 的 `limits` 段覆盖六道防线参数，自动 clamp 到合法范围
- `filelock` 安全门：并行模式（Orchestrator）启动前强制检测 `filelock` 依赖，缺失时拒绝进入
- Hook 超时追踪：面包屑机制检测被超时杀掉的 hook，记录到 eval log
- Web HUD 拆分：HTTP 服务器从 `harness.py` 拆到独立的 `web_hud.py`

## [3.3.0] — 2026-04 (commit `2999bd9`)

- 多模式架构：pipeline / single / conversation 三种模式
- Web HUD SSE 实时推送（0.5s 检测，连接失败降级 2s 轮询）
- Cursor 2.5+ 适配（`${CURSOR_PLUGIN_ROOT}` 自动映射）
- 通知系统：`notify.py` 桌面通知 + 飞书 Webhook
- Worker 可视化：Orchestrator 模式下并行批次进度
- 评测趋势图：Canvas 折线图显示 score / pass rate 历史
- 移动端适配：768px 断点
- 完成项目过滤：默认隐藏已结束任务

## [3.2.4] — 2026-03 (commit `e1d43ea`)

- SessionStart 引导 + README 重写 + v3.3 规划

## [3.2.3] — 2026-03 (commit `d600a2f`)

- 全量 venv 隔离，零全局污染

## [3.2.2] — 2026-03 (commit `b6a0852`)

- setup 非侵入式重构 + filelock 可选降级

## [3.2.x] — 2026-03

- v3.2 多 Agent 并行架构
  - Layer 1 阶段级并行：parallel_group 命名分组，audit + docs + test 三路 background Agent 并行
  - Layer 2 任务级并行（Orchestrator）：Phase > 3 自动触发，Worker 通过 `.claude/workers/worker-*.json` 独立汇报
  - 并发安全：`filelock` 保护 `harness-state.json`
  - review 三路并行：skill 内部 3 个 background Agent
  - 评测：32 → 38 用例，8 → 10 维度

---

For commits before 3.2, see `git log`.
