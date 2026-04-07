# Multi-Agent 并行架构 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 Dev Harness 引入两层并行能力：Layer 1 阶段级并行（audit+docs+test 同时跑）、Layer 2 任务级并行（Orchestrator 拆 Phase 给多个 Worker 在独立 worktree 并行执行）

**Architecture:** 用 `parallel_group` 命名分组替代 `parallel_with` 两两绑定。状态文件用 `filelock` 保护并发写入。Worker 通过独立状态文件 `.claude/workers/worker-*.json` 汇报，Orchestrator 轮询合并。review 三路并行在 skill 内部完成，不改 pipeline 层。

**Tech Stack:** Python 3.8+, filelock, Claude Code Agent tool (run_in_background, isolation: worktree)

---

## Task 1: filelock 依赖 + 原子状态读写

**Files:**
- Modify: `scripts/harness.py:96-107` (load_state/save_state)
- Modify: `hooks/stop-hook.py:414-416` (save_state)
- Modify: `scripts/setup.sh` (安装提示)

**Step 1: 安装 filelock**

Run: `pip install filelock`

**Step 2: 改造 harness.py 的 save_state 为原子操作**

```python
# scripts/harness.py — 替换 load_state / save_state

from filelock import FileLock

def load_state():
    lock = FileLock(str(STATE_FILE) + ".lock", timeout=5)
    try:
        with lock:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    lock = FileLock(str(STATE_FILE) + ".lock", timeout=5)
    with lock:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
```

**Step 3: 同步改造 stop-hook.py 的 save_state**

```python
# hooks/stop-hook.py — 替换 save_state 函数

from filelock import FileLock

def save_state(state, path):
    state["updated_at"] = now_iso()
    lock = FileLock(str(path) + ".lock", timeout=5)
    with lock:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
```

**Step 4: setup.sh 添加 filelock 安装**

在 Rich 库检测之后添加：

```bash
# 3. filelock（并行 Agent 状态保护）
if python -c "import filelock" 2>/dev/null; then
    echo "[OK] filelock 已安装"
else
    pip install filelock -q 2>/dev/null && echo "[OK] filelock 安装成功" || echo "[ERROR] filelock 安装失败，多 Agent 并行将无法工作"
fi
```

**Step 5: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 32/32 通过（纯内部重构，不影响行为）

---

## Task 2: parallel_group 分组模型

**Files:**
- Modify: `defaults/pipeline.yml` (parallel_with → parallel_group)
- Modify: `scripts/harness.py:114-124` (DEFAULT_PIPELINE)
- Modify: `scripts/harness.py:242-260` (find_next_runnable)
- Modify: `hooks/stop-hook.py:391-407` (find_next)

**Step 1: 更新 pipeline.yml**

```yaml
# defaults/pipeline.yml — 替换 audit/docs/test 的并行声明

stages:
  - name: research
    when: "route in [B]"
    human: false

  - name: prd
    when: "route in [A, B]"
    human: true

  - name: plan
    when: "route in [A, B, C]"
    human: true

  - name: implement
    when: "route in [A, B, C, C-lite, D]"
    loop: true
    gate:
      - build
      - test
    max_retries: 3
    worktree: true

  - name: audit
    when: "route in [A, B, C]"
    parallel_group: post-implement
    auto_fix: true

  - name: docs
    when: "changed_api"
    parallel_group: post-implement

  - name: test
    when: "route in [A, B, C]"
    parallel_group: post-implement
    auto_fix: true
    max_retries: 3

  - name: review
    when: "route in [A, B, C]"

  - name: remember
    when: "always"
```

**Step 2: 更新 DEFAULT_PIPELINE 常量**

```python
# scripts/harness.py — 替换 DEFAULT_PIPELINE

DEFAULT_PIPELINE = [
    {"name": "research",  "status": "SKIP"},
    {"name": "prd",       "status": "SKIP"},
    {"name": "plan",      "status": "PENDING"},
    {"name": "implement", "status": "PENDING", "phases": []},
    {"name": "audit",     "status": "PENDING", "parallel_group": "post-implement"},
    {"name": "docs",      "status": "PENDING", "parallel_group": "post-implement"},
    {"name": "test",      "status": "PENDING", "parallel_group": "post-implement"},
    {"name": "review",    "status": "PENDING"},
    {"name": "remember",  "status": "PENDING"},
]
```

**Step 3: 重写 find_next_runnable 支持 parallel_group**

```python
# scripts/harness.py — 替换 find_next_runnable

def find_next_runnable(pipeline, current_name):
    """找到下一个可执行的阶段组（同 parallel_group 的阶段一起返回）"""
    found_current = False
    for s in pipeline:
        if s["name"] == current_name:
            found_current = True
            continue
        if not found_current:
            continue
        if s["status"] not in ("PENDING", "WAITING"):
            continue

        group = s.get("parallel_group")
        if group:
            # 返回同组所有 PENDING/WAITING 的阶段
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps["status"] in ("PENDING", "WAITING")]
        else:
            return [s["name"]]
    return []
```

**Step 4: 同步更新 stop-hook.py 的 find_next**

```python
# hooks/stop-hook.py — 替换 find_next 函数（逻辑与 harness.py 一致）

def find_next(pipeline, current_name):
    """找到下一组可执行阶段"""
    found = False
    for s in pipeline:
        if s["name"] == current_name:
            found = True
            continue
        if not found:
            continue
        if s.get("status") not in ("PENDING", "WAITING"):
            continue

        group = s.get("parallel_group")
        if group:
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps.get("status") in ("PENDING", "WAITING")]
        else:
            return [s["name"]]
    return []
```

**Step 5: 更新 cmd_update 处理并行组完成**

在 `cmd_update` 的 `if new_status == "DONE"` 分支中，需要检查并行组是否全部完成：

```python
# scripts/harness.py cmd_update 末尾 — 替换 current_stage 更新逻辑

    if new_status == "DONE":
        # 检查并行组：如果当前阶段属于某个组，只有组内全部 DONE 才推进
        group = None
        for s in state["pipeline"]:
            if s["name"] == stage_name:
                group = s.get("parallel_group")
                break
        if group:
            group_stages = [s for s in state["pipeline"] if s.get("parallel_group") == group]
            all_done = all(s["status"] == "DONE" for s in group_stages)
            if all_done:
                # 组内全完成，找下一个非本组的阶段
                last_in_group = group_stages[-1]["name"]
                next_stages = find_next_runnable(state["pipeline"], last_in_group)
                if next_stages:
                    state["current_stage"] = next_stages[0]
            # 组内未全完成，不推进 current_stage
        else:
            next_stages = find_next_runnable(state["pipeline"], stage_name)
            if next_stages:
                state["current_stage"] = next_stages[0]
```

**Step 6: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 需要更新 eval 中依赖 `parallel_with` 的测试用例。

**Step 7: 更新 eval 用例**

检查 eval-runner.py 中是否有测试直接引用 `parallel_with`，替换为 `parallel_group`。

---

## Task 3: SKILL.md 并行编排逻辑

**Files:**
- Modify: `skills/dev/SKILL.md:160-164` (audit+docs 并行段落)

**Step 1: 重写并行阶段编排指引**

替换 SKILL.md 中 "audit + docs 阶段（并行）" 段落：

```markdown
### post-implement 并行组（audit + docs + test）

implement 完成后，以下三个阶段**同时启动**：

```
1. 更新全部为 IN_PROGRESS:
   python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update audit IN_PROGRESS
   python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update docs IN_PROGRESS
   python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update test IN_PROGRESS

2. 用 background Agent 并行执行三路:
   - Agent(name="audit-worker", run_in_background=true):
     解析 audit Skill → 执行 → harness.py update audit DONE
   - Agent(name="docs-worker", run_in_background=true):
     解析 docs Skill → 执行 → harness.py update docs DONE
   - Agent(name="test-worker", run_in_background=true):
     解析 test Skill → 执行 → harness.py update test DONE

3. 等待三路全部完成（background Agent 完成时会通知）

4. 三路都 DONE → 进入 review 阶段
```

**注意**: 每个 background Agent 内部独立更新自己负责的阶段状态。
filelock 保证并发写入安全。如果任一阶段失败超过 max_retries，
该阶段标记 FAILED，其他阶段继续。全部完成后汇总失败信息。
```

**Step 2: 删除旧的 test 阶段独立段落**

把原来的 "### test 阶段" 段落合并到并行组说明中，因为 test 现在是并行组的一部分。

---

## Task 4: stop-hook.py 并行组续跑逻辑

**Files:**
- Modify: `hooks/stop-hook.py:374-387` (并行组续跑指令)

**Step 1: 更新 stop-hook 的阶段完成处理**

当 stop-hook 检测到当前阶段 DONE 且下一组是并行组时，需要生成并行启动指令：

```python
# hooks/stop-hook.py — 替换 stage DONE 后的处理逻辑

    if stage.get("status") == "DONE":
        next_names = find_next(pipeline, current)
        if not next_names:
            sys.exit(0)
        state["current_stage"] = next_names[0]
        state["metrics"]["auto_continues"] = state["metrics"].get("auto_continues", 0) + 1
        save_state(state, state_file)
        if len(next_names) == 1:
            reason = f"上一阶段 {current} 已完成。继续执行 {next_names[0]} 阶段。先运行 skill-resolver 确认用哪个 Skill，然后执行。完成后更新 harness-state.json。"
        else:
            names = "、".join(next_names)
            reason = (
                f"上一阶段 {current} 已完成。并行启动 {names} 阶段。\n"
                f"用 Agent tool 的 run_in_background=true 同时启动 {len(next_names)} 个 background Agent，"
                f"每个 Agent 负责一个阶段：解析 Skill → 执行 → harness.py update <stage> DONE。\n"
                f"等待所有 background Agent 完成后，再推进到下一阶段。"
            )
        output_block(reason, state, project_root)
        return
```

**Step 2: 处理并行组内某阶段 DONE 但组未全完成**

```python
# hooks/stop-hook.py — 在 stage DONE 处理之前，添加并行组检查

    # 检查当前阶段的并行组状态
    current_group = stage.get("parallel_group")
    if current_group and stage.get("status") == "IN_PROGRESS":
        # 当前是并行组内的阶段，正在执行中，不干预
        # （其他组员可能也在并行跑）
        pass

    if current_group and stage.get("status") == "DONE":
        # 并行组内的一个阶段完成了，检查组内其他成员
        group_stages = [s for s in pipeline if s.get("parallel_group") == current_group]
        pending = [s for s in group_stages if s["status"] in ("PENDING", "IN_PROGRESS")]
        if pending:
            # 组内还有未完成的，不推进
            sys.exit(0)
        # 组内全部完成，推进到下一阶段
        next_names = find_next(pipeline, group_stages[-1]["name"])
        if not next_names:
            sys.exit(0)
        state["current_stage"] = next_names[0]
        state["metrics"]["auto_continues"] = state["metrics"].get("auto_continues", 0) + 1
        save_state(state, state_file)
        reason = f"并行组 {current_group} 全部完成。继续执行 {next_names[0]} 阶段。"
        output_block(reason, state, project_root)
        return
```

---

## Task 5: Layer 2 — Worker 状态文件与 Orchestrator 命令

**Files:**
- Modify: `scripts/harness.py` (新增 worker 子命令)
- Create: `scripts/orchestrator.py` (Orchestrator 逻辑)

**Step 1: harness.py 新增 worker 管理命令**

```python
# scripts/harness.py — 新增 Worker 状态管理

WORKERS_DIR = PROJECT_ROOT / ".claude" / "workers"

def cmd_worker_report(args):
    """Worker 汇报完成状态"""
    WORKERS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "worker_id": args.worker_id,
        "phase": args.phase,
        "status": args.status.upper(),
        "worktree_branch": args.branch or "",
        "completed_at": now_iso(),
    }
    report_file = WORKERS_DIR / f"worker-{args.worker_id}.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

def cmd_worker_status(args):
    """Orchestrator 查询所有 Worker 状态"""
    if not WORKERS_DIR.exists():
        print(json.dumps({"workers": []}, ensure_ascii=False))
        return
    workers = []
    for f in sorted(WORKERS_DIR.glob("worker-*.json")):
        try:
            workers.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    all_done = all(w["status"] == "DONE" for w in workers) if workers else False
    failed = [w for w in workers if w["status"] == "FAILED"]
    print(json.dumps({
        "workers": workers,
        "total": len(workers),
        "done": sum(1 for w in workers if w["status"] == "DONE"),
        "failed": len(failed),
        "all_done": all_done,
    }, ensure_ascii=False))

def cmd_worker_cleanup(args):
    """清理 Worker 状态文件"""
    if WORKERS_DIR.exists():
        import shutil
        shutil.rmtree(WORKERS_DIR, ignore_errors=True)
    print('{"cleaned": true}')
```

**Step 2: 注册 CLI 子命令**

```python
# scripts/harness.py main() 中添加

    # worker-report
    p_wr = sub.add_parser("worker-report")
    p_wr.add_argument("worker_id")
    p_wr.add_argument("--phase", required=True)
    p_wr.add_argument("--status", required=True)
    p_wr.add_argument("--branch", default="")

    # worker-status
    sub.add_parser("worker-status")

    # worker-cleanup
    sub.add_parser("worker-cleanup")

    # ... 在 dispatch 中添加:
    elif args.cmd == "worker-report":
        cmd_worker_report(args)
    elif args.cmd == "worker-status":
        cmd_worker_status(args)
    elif args.cmd == "worker-cleanup":
        cmd_worker_cleanup(args)
```

---

## Task 6: Layer 2 — SKILL.md Orchestrator 编排逻辑

**Files:**
- Modify: `skills/dev/SKILL.md:124-155` (implement 阶段)

**Step 1: 重写 implement 阶段编排**

```markdown
### implement 阶段（Orchestrator 模式）

读取 plan 文件 → 解析出 Phase 列表 → 写入 harness-state.json

**Phase 数量判断**:
- **≤ 3 个 Phase** → 串行执行（现有逻辑不变）
- **> 3 个 Phase** → Orchestrator 模式：分析依赖关系，将 Phase 分为可并行组

**Orchestrator 模式执行流程**:

```
1. 分析 Plan 中所有 Phase 的依赖关系
   （哪些 Phase 修改同一文件/模块 → 不可并行）
   （哪些 Phase 完全独立 → 可并行）

2. 将 Phase 分组:
   - 并行批次 1: [Phase 1, Phase 2]  ← 互相独立
   - 串行: Phase 3                    ← 依赖 Phase 1
   - 并行批次 2: [Phase 4, Phase 5]  ← 互相独立

3. 对每个并行批次:
   a. 为每个 Phase 启动一个 Agent:
      Agent(
        name="worker-{phase_name}",
        isolation="worktree",        ← 独立 worktree
        run_in_background=true,
        model="opus",
        prompt="实现 Phase N: {具体内容}。
               完成后运行门禁:
                 {build_cmd}
                 {test_cmd}
               门禁通过后汇报:
                 python harness.py worker-report {worker_id} --phase {N} --status DONE --branch {branch}
               门禁失败且重试 3 次仍失败:
                 python harness.py worker-report {worker_id} --phase {N} --status FAILED"
      )

   b. 等待当前批次所有 Worker 完成:
      python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" worker-status
      → 检查 all_done == true

   c. 检查失败:
      - 有 FAILED Worker → 停下报告用户
      - 全部 DONE → 合并 worktree 分支，清理 Worker 文件

4. 所有批次完成:
   python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" worker-cleanup
   python "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement DONE
```

**Worktree 合并策略**:
每个批次完成后，按顺序合并各 Worker 的 worktree 分支:
```bash
git merge worker-phase-1 --no-ff -m "merge: Phase 1 via worker"
git merge worker-phase-2 --no-ff -m "merge: Phase 2 via worker"
```
如果合并冲突 → 停下来找用户。

**降级**: Orchestrator 模式中任何 Worker 启动失败 → 自动降级为串行模式。
```

---

## Task 7: review skill 内部三路并行

**Files:**
- Modify: `skills/generic-review/SKILL.md` (三路并行改为显式 Agent 调用)

**Step 1: 重写 review skill 为显式并行**

```markdown
---
name: generic-review
description: 通用代码审查 — 三路并行审查（code-reviewer + security-reviewer + architect），Opus 汇总对比。
---

# 通用代码审查（三路并行）

## 角色
你是质量守门人。在代码提交前做最终审查。

## 审查范围

```bash
git diff master...HEAD
```

## 执行方式

同时启动三路审查 Agent:

```
1. Agent(name="review-code", subagent_type="code-review-ai:architect-review", run_in_background=true):
   "审查以下 diff，侧重: 代码质量、bug、边界条件、可维护性。
    输出结构化报告到 .claude/reports/review-code-{date}.md
    格式: CRITICAL/WARN/INFO 分级"

2. Agent(name="review-security", run_in_background=true):
   "审查以下 diff，侧重: SQL 注入、XSS、敏感信息泄露、权限缺失。
    输出结构化报告到 .claude/reports/review-security-{date}.md
    格式: CRITICAL/WARN/INFO 分级"

3. Agent(name="review-arch", run_in_background=true):
   "审查以下 diff，侧重: 架构合理性、模块边界、设计模式。
    输出结构化报告到 .claude/reports/review-arch-{date}.md
    格式: CRITICAL/WARN/INFO 分级"
```

等待三路全部完成后，汇总:

## 汇总规则

| 情况 | 处理 |
|------|------|
| 任一方发现 CRITICAL | 自动修复 → 重编译确认 |
| 多方发现同一问题 | 高置信度，优先修复 |
| 仅一方发现且非 CRITICAL | 留档标注"单方发现" |
| 三方无 CRITICAL | 通过 |

## 产出

`.claude/reports/final-review-{date}.md` — 三方对比表和汇总结论。
```

---

## Task 8: 评测用例更新

**Files:**
- Modify: `eval/eval-runner.py` (更新 parallel_with → parallel_group 测试)

**Step 1: 更新 DEFAULT_PIPELINE 引用**

eval-runner.py 中如果直接引用 `parallel_with` 字段需改为 `parallel_group`。

**Step 2: 新增并行组评测用例**

```python
def test_parallel_group():
    """测试 parallel_group 分组逻辑"""
    results = []

    # 测试 1: find_next_runnable 返回同组所有阶段
    tmpdir = create_temp_project()
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} init parallel-test --route C", cwd=tmpdir)
    assert rc == 0

    # 手动设 implement=DONE，检查下一组
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} update implement DONE", cwd=tmpdir)
    state = json.loads((Path(tmpdir) / ".claude" / "harness-state.json").read_text(encoding="utf-8"))
    # 应该推进到并行组的第一个阶段
    results.append({
        "test": "parallel_group_advance",
        "pass": state["current_stage"] in ("audit", "docs", "test"),
        "detail": f"current_stage={state['current_stage']}"
    })

    # 测试 2: 并行组内一个 DONE，组未全完成时不推进
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} update audit DONE", cwd=tmpdir)
    state = json.loads((Path(tmpdir) / ".claude" / "harness-state.json").read_text(encoding="utf-8"))
    # review 不应该被激活
    review = next(s for s in state["pipeline"] if s["name"] == "review")
    results.append({
        "test": "parallel_group_partial",
        "pass": review["status"] == "PENDING" and state["current_stage"] != "review",
        "detail": f"review.status={review['status']}, current={state['current_stage']}"
    })

    # 测试 3: 并行组全部 DONE，推进到 review
    run_cmd(f"python {HARNESS_SCRIPT} update docs DONE", cwd=tmpdir)
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} update test DONE", cwd=tmpdir)
    state = json.loads((Path(tmpdir) / ".claude" / "harness-state.json").read_text(encoding="utf-8"))
    results.append({
        "test": "parallel_group_all_done",
        "pass": state["current_stage"] == "review",
        "detail": f"current_stage={state['current_stage']}"
    })

    cleanup_temp(tmpdir)
    return "parallel_group", results
```

**Step 3: 新增 Worker 管理评测**

```python
def test_worker_management():
    """测试 Worker 状态文件管理"""
    results = []
    tmpdir = create_temp_project()

    # 测试 1: worker-report 创建文件
    out, rc = run_cmd(
        f"python {HARNESS_SCRIPT} worker-report w1 --phase Phase1 --status DONE --branch dh-w1",
        cwd=tmpdir)
    worker_file = Path(tmpdir) / ".claude" / "workers" / "worker-w1.json"
    results.append({
        "test": "worker_report_creates_file",
        "pass": worker_file.exists() and rc == 0,
        "detail": f"exists={worker_file.exists()}"
    })

    # 测试 2: worker-status 汇总
    run_cmd(f"python {HARNESS_SCRIPT} worker-report w2 --phase Phase2 --status DONE", cwd=tmpdir)
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} worker-status", cwd=tmpdir)
    info = json.loads(out)
    results.append({
        "test": "worker_status_aggregation",
        "pass": info["total"] == 2 and info["all_done"] == True,
        "detail": f"total={info['total']}, all_done={info['all_done']}"
    })

    # 测试 3: worker-cleanup 清理
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} worker-cleanup", cwd=tmpdir)
    workers_dir = Path(tmpdir) / ".claude" / "workers"
    results.append({
        "test": "worker_cleanup",
        "pass": not workers_dir.exists(),
        "detail": f"dir_exists={workers_dir.exists()}"
    })

    cleanup_temp(tmpdir)
    return "worker_management", results
```

**Step 4: 注册新测试维度**

在 eval-runner.py 的 `run_all` 中注册:

```python
all_results.append(test_parallel_group())   # weight=1.5
all_results.append(test_worker_management()) # weight=1.0
```

**Step 5: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 全部通过（含新增用例）

---

## Task 9: CLAUDE.md 和文档更新

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/SESSION-HANDOFF.md`

**Step 1: CLAUDE.md 补充多 Agent 架构说明**

在 "### 12 个 Agent" 之后添加:

```markdown
### 多 Agent 并行

**Layer 1 — 阶段级并行**: pipeline.yml 中 `parallel_group` 字段声明可并行的阶段组。implement 完成后，audit + docs + test 三路同时启动（各自一个 background Agent），全部完成后进入 review。

**Layer 2 — 任务级并行 (Orchestrator 模式)**: 当 Plan 中 Phase > 3 个时自动触发。Orchestrator 分析 Phase 依赖关系，将无依赖的 Phase 分为并行批次，每个 Phase 交给一个 Worker Agent 在独立 worktree 中执行。Worker 通过 `.claude/workers/worker-*.json` 汇报状态，Orchestrator 轮询合并。

**并发安全**: harness-state.json 的读写通过 filelock 保护，防止多 Agent 竞态。

**review 三路并行**: 在 generic-review skill 内部完成（code-reviewer + security-reviewer + architect 三个 background Agent），不走 pipeline 层。
```

**Step 2: SESSION-HANDOFF.md 更新**

更新待做列表和已完成工作。

---

## 执行顺序总结

```
Task 1: filelock 原子写入          ← 基础设施，后续都依赖
Task 2: parallel_group 模型        ← Layer 1 核心
Task 3: SKILL.md 并行编排          ← Layer 1 编排
Task 4: stop-hook 并行续跑        ← Layer 1 续跑
Task 5: Worker 命令                ← Layer 2 核心
Task 6: SKILL.md Orchestrator     ← Layer 2 编排
Task 7: review 三路并行            ← Layer 1 补充
Task 8: 评测                       ← 验证
Task 9: 文档                       ← 收尾
```
