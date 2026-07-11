---
name: dev-pipeline
description: Full-auto multi-stage dev pipeline orchestrator with build/test gate enforcement and hook-driven auto-resume. Use when the user says /dev, 开发, 继续开发, 下一步, when a new session must resume an in-progress harness task, or when the user sets a goal that references the dev pipeline / dev-harness. Do not use for one-off fixes (fix), Q&A (ask), or one stage alone (*-skill).
model_context: claude-opus-4.5+
---

# /dev — 开发流水线编排器

## 启动声明（必读 · 不可跳过）

收到 `/dev` 调用后，**第一条回复必须严格按以下格式开头**：

> Using `dev-harness:dev-pipeline` skill — running Step 0 (并行 3 条检测) now.

然后**在同一条回复内立即并行调用**下面"启动"段的 3 条 Bash 命令。

**禁止行为**：

- 只回复"收到，按 dev-harness 流程启动..."然后停下等下一轮
- 用抽象总结（"我会先检测环境"）代替实际 Bash 执行
- 只列出要做什么而不真正调用工具

**Why**：用户输入 `/dev` 是开始动作，不是请求解说。把"意图声明"绑死到"立即执行"，是 harness engineering 的核心防摆烂手段（参考 superpowers `executing-plans` skill 的 "Announce at start" 同源设计）。

## 约束

- Skill 解析走三层（L1 项目 > L2 用户 > L3 内置）
- 同一 Phase/阶段失败 3 次必须停下报告用户

## 连续执行（违纪红线）

不在阶段间停下和用户 check-in。执行完 pipeline 全部阶段，唯一可停的三种情形：BLOCKED 且无法自解 / 真正阻断推进的歧义 / 全部阶段完成。"要我继续吗？"式提问和进度小结是在浪费用户时间——用户输入 `/dev` 就是让你跑完。

| 借口 | 现实 |
|------|------|
| "阶段间同步下进度更稳妥" | update 状态已是唯一进度源，同步=停摆 |
| "让用户确认下再进 implement" | 只有 `plan.fallback=wait` 才停；其余一律续跑 |
| "这一步有点不确定，先问问" | 不确定≠阻断。记 pitfall、按最简可工作版本推进 |

### 红旗（出现即代表你在摆烂）

- 写了"已完成 X 阶段，是否继续" — 删掉，直接进下一阶段
- 用自然语言复述"接下来我会…"代替真的调用 `harness.py update`
- 违背话术字面 = 违背话术精神

## 脚本路径

所有脚本通过 `${CLAUDE_PLUGIN_ROOT}` 定位：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" <cmd>
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" <stage>
```

---

## 启动

并行执行环境检测：

```bash
cat .claude/harness-state.json 2>/dev/null || echo "NO_STATE"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/detect-stack.sh"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" --all
```

- **有 harness-state.json** → 读取 `current_stage`，续接该阶段
- **无状态** → 询问用户任务名称和类型，判断路线，初始化：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" init "任务名" --route C
```

## Skill 解析

对当前阶段运行三层解析：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/skill-resolver.py" <stage_name>
```

- L1/L2 命中 → 调用 `/skill-name`
- L3 命中 → 读取插件内置 SKILL.md 执行

## Pipeline 推进

每个阶段按下面的循环走。`update` 之后**立即**跑一次 `hud`——hud 输出作为工具结果进 transcript，是完成裁判（prompt Stop hook）判定流水线是否真跑完的唯一证据；不跑 hud 裁判看不到任何状态。

```bash
# 开始
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update <stage> IN_PROGRESS

# 执行 Skill（根据解析结果）

# 完成
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update <stage> DONE
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" hud

# 直接继续下一个阶段，不停下
```

### 每 stage 完成契约（必填，缺一不可）

- [ ] 产出文件已落盘：`<path>`
- [ ] 门禁结果：build=`<pass/fail>` test=`<pass/fail>`
- [ ] 已执行 `harness.py update <stage> DONE` + `harness.py hud`  ← 未执行本行禁止进入下一 stage

---

## 各阶段

### research（路线 B）
产出: `.claude/researches/*.md`

### prd（路线 A/B）
需要多轮对话。产出: `.claude/project-design/*-prd.md`

### plan（路线 A/B/C）

产出: `.claude/plans/*.md`。**等待策略读 `pipeline.yml` 或 `dev-config.yml` 的 `plan.fallback`**：

- `fallback: wait`（默认）— plan 写完停下，明确告诉用户"请 review，说'通过'后我会继续"。等审批
- `fallback: auto-approve` — plan 写完立即 `harness.py update plan DONE` 并进入 implement，不等用户。**告诉用户已自动通过**但不要等回复
- `fallback: skip` — 跳过整个 plan 阶段（D 路线/修 typo 类极简任务）

无配置时默认 `wait`。**禁止**在 `wait` 模式下用任何形式自作主张进入 implement。

### implement
读取 `.claude/plans/` 下的计划文档，逐 Phase 执行。

每个 Phase:
1. 按 plan 变更清单修改文件
2. 运行门禁（detect-stack.sh 检测 build/test 命令）
3. 门禁通过 → `harness.py update implement IN_PROGRESS --phase N --gate build=pass`
4. 继续下一个 Phase

Phase > 3 时，可用 background Agent(`isolation: "worktree"`) 并行执行无依赖的 Phase。

门禁命令来源（优先级）:
1. `.claude/dev-config.yml` 的 `gates` 段
2. `detect-stack.sh` 自动检测

### post-implement 并行组（audit + docs + test）

implement 完成后，用 background Agent 同时启动三路：

```
Agent(name="audit-worker", run_in_background=true):  解析 audit Skill → 执行 → harness.py update audit DONE
Agent(name="docs-worker", run_in_background=true):   解析 docs Skill → 执行 → harness.py update docs DONE
Agent(name="test-worker", run_in_background=true):   解析 test Skill → 执行 → harness.py update test DONE
```

等待三路全部完成后进入 review。

### review
三路联合审查（code-reviewer + security-reviewer + architect）。CRITICAL → 自动修复。

### remember
调用 /remember 保存进度。

---

## 自动续跑

Stop Hook 检查六道防线（上下文/超时/频率/rate limit/死循环），通过则注入续跑指令。你应该尽量自己直接推进，Stop Hook 是兜底。

---

## 用户交互模板

### 新任务
```
检测到项目: {project_name}，技术栈: {stack}
未找到进行中的任务。请告诉我：
1. 任务名称  2. 类型（新功能/bugfix/紧急）  3. 涉及模块
```

### 续接
```
续接任务: {task_name}
当前阶段: implement (Phase 3/4)
继续实现 Phase 3...
```

### 完成
```
全流程完成！
Task: {task_name} | Route: {route} | Stages: {completed}/{total}
Reports: .claude/reports/
```
