---
name: dev
description: 开发流水线编排器 — 自动检测状态、三层 Skill 解析、Hook 驱动续跑。通用于任何项目。Use when: 用户说"dev/开发/继续开发/下一步"，或新会话需要续接上次进度。
---

# /dev — 开发流水线编排器

## 约束

- 每完成一个阶段/Phase，必须 `harness.py update` — 续跑的唯一依据
- 不在阶段间停下等用户 — 更新状态后直接继续
- Skill 解析走三层（L1 项目 > L2 用户 > L3 内置）
- 同一 Phase/阶段失败 3 次必须停下报告用户

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

每个阶段：

```bash
# 开始
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update <stage> IN_PROGRESS

# 执行 Skill（根据解析结果）

# 完成
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update <stage> DONE

# 直接继续下一个阶段，不停下
```

---

## 各阶段

### research（路线 B）
产出: `.claude/researches/*.md`

### prd（路线 A/B）
需要多轮对话。产出: `.claude/project-design/*-prd.md`

### plan（路线 A/B/C）
需要用户审批。产出: `.claude/plans/*.md`。用户说"通过"后立即进入 implement。

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
