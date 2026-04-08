# Phases 自动注册 + Stop Hook Fallback + Web HUD 多项目 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 解决 phases 注册从"概率性"变为"确定性"，并升级 Web HUD 为多项目实时面板

**Architecture:** PostToolUse hook 监听 plan 文件写入自动注册 phases；Stop hook 增加 fallback 解析 plan 文件；Web HUD 从 session 索引加载多项目数据，前端 tab 切换

**Tech Stack:** Python 3.8+, filelock, HTML/JS (内嵌), Claude Code hooks

---

## Task 1: plan-watcher.py — PostToolUse 自动注册 phases

**Files:**
- Create: `hooks/plan-watcher.py`
- Modify: `hooks/hooks.json`

**Step 1: 创建 plan-watcher.py**

```python
#!/usr/bin/env python
"""PostToolUse Hook: 监听 plan 文件写入，自动解析 Phase 列表并注册到 harness-state.json"""
import json, sys, os, re
from pathlib import Path
from filelock import FileLock

def parse_phases_from_plan(plan_path):
    """从 plan 文件解析 Phase 列表"""
    text = Path(plan_path).read_text(encoding="utf-8")
    phases = []
    # 匹配: ## Phase N / ### Task N / ## 阶段 N（支持中英文冒号和各种分隔符）
    pattern = r'^#{2,3}\s+(?:Phase|Task|阶段)\s*(\d+)\s*[：:.\-—]?\s*(.*?)$'
    for m in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
        num = int(m.group(1))
        name = m.group(2).strip() or f"Phase {num}"
        phases.append({
            "name": f"Phase {num}: {name}" if name != f"Phase {num}" else name,
            "status": "PENDING",
            "error_count": 0,
        })
    return phases

def main():
    # 读取 hook 输入
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # 只处理 Write 和 Edit 工具
    tool = hook_input.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        sys.exit(0)

    # 获取写入的文件路径
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # 只匹配 .claude/plans/*.md
    fp = Path(file_path)
    if not (fp.suffix == ".md" and ".claude" in fp.parts and "plans" in fp.parts):
        sys.exit(0)

    if not fp.exists():
        sys.exit(0)

    # 解析 phases
    phases = parse_phases_from_plan(fp)
    if not phases:
        sys.exit(0)

    # 查找 harness-state.json
    # 从文件路径向上找项目根
    project_root = fp.parent
    while project_root != project_root.parent:
        state_file = project_root / ".claude" / "harness-state.json"
        if state_file.exists():
            break
        if (project_root / ".git").exists():
            break
        project_root = project_root.parent

    state_file = project_root / ".claude" / "harness-state.json"
    if not state_file.exists():
        sys.exit(0)

    # 更新 state 中的 implement phases
    lock = FileLock(str(state_file) + ".lock", timeout=5)
    with lock:
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            sys.exit(0)

        for s in state.get("pipeline", []):
            if s["name"] == "implement":
                existing = s.get("phases", [])
                # 只在 phases 为空或数量不匹配时更新（避免覆盖已有进度）
                if not existing or len(existing) != len(phases):
                    # 保留已有 phase 的状态
                    for i, new_p in enumerate(phases):
                        if i < len(existing):
                            new_p["status"] = existing[i].get("status", "PENDING")
                            new_p["error_count"] = existing[i].get("error_count", 0)
                    s["phases"] = phases
                break

        from datetime import datetime, timezone
        state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 输出通知（不阻塞）
    print(json.dumps({
        "phases_registered": len(phases),
        "names": [p["name"] for p in phases],
    }, ensure_ascii=False), file=sys.stderr)

if __name__ == "__main__":
    main()
```

**Step 2: 更新 hooks.json 注册 PostToolUse**

在现有 hooks.json 的 Stop 之后添加 PostToolUse：

```json
{
  "hooks": {
    "Stop": [...],
    "PostToolUse": [
      {
        "matcher": "Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "python \"${CLAUDE_PLUGIN_ROOT}/hooks/plan-watcher.py\"",
            "timeout": 3000
          }
        ]
      }
    ]
  }
}
```

**Step 3: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 38/38 通过（新 hook 不影响现有逻辑）

---

## Task 2: plan-watcher 评测用例

**Files:**
- Modify: `eval/eval-runner.py`

**Step 1: 新增 plan_watcher 评测函数**

```python
def test_plan_watcher():
    """测试 PostToolUse plan-watcher 自动注册 phases"""
    import shutil
    results = []
    watcher_script = str(Path(__file__).parent.parent / "hooks" / "plan-watcher.py")

    # 测试 1: 写入 plan 文件后 phases 自动注册
    tmpdir = _make_test_env()
    # 先初始化 state
    run_cmd(f"python {HARNESS_SCRIPT} init watcher-test --route C", cwd=tmpdir)
    # 创建 plan 文件
    plan_dir = os.path.join(tmpdir, ".claude", "plans")
    os.makedirs(plan_dir, exist_ok=True)
    plan_content = """# Test Plan
## Phase 1：脚手架搭建
### 目标
搭建项目骨架
## Phase 2：核心逻辑
实现业务逻辑
## Phase 3：测试补全
补充测试用例
"""
    plan_file = os.path.join(plan_dir, "test-plan.md")
    with open(plan_file, "w", encoding="utf-8") as f:
        f.write(plan_content)
    # 模拟 PostToolUse hook 输入
    hook_input = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": plan_file},
    })
    out, rc = run_cmd(f'echo {json.dumps(hook_input)} | python {watcher_script}', cwd=tmpdir)
    state = _read_state(tmpdir)
    impl = next(s for s in state["pipeline"] if s["name"] == "implement")
    results.append({
        "test": "plan_watcher_registers_phases",
        "pass": len(impl.get("phases", [])) == 3,
        "detail": f"phases={len(impl.get('phases', []))}"
    })

    # 测试 2: 非 plan 文件不触发
    hook_input2 = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": os.path.join(tmpdir, "README.md")},
    })
    # 重置 phases 为空
    impl["phases"] = []
    _write_state(tmpdir, state)
    run_cmd(f'echo {json.dumps(hook_input2)} | python {watcher_script}', cwd=tmpdir)
    state2 = _read_state(tmpdir)
    impl2 = next(s for s in state2["pipeline"] if s["name"] == "implement")
    results.append({
        "test": "plan_watcher_ignores_non_plan",
        "pass": len(impl2.get("phases", [])) == 0,
        "detail": f"phases={len(impl2.get('phases', []))}"
    })

    # 测试 3: 不覆盖已有进度（Phase 1 已 DONE）
    impl2["phases"] = [
        {"name": "Phase 1: 脚手架搭建", "status": "DONE", "error_count": 0},
    ]
    _write_state(tmpdir, state2)
    hook_input3 = json.dumps({
        "tool_name": "Write",
        "tool_input": {"file_path": plan_file},
    })
    run_cmd(f'echo {json.dumps(hook_input3)} | python {watcher_script}', cwd=tmpdir)
    state3 = _read_state(tmpdir)
    impl3 = next(s for s in state3["pipeline"] if s["name"] == "implement")
    phase1 = impl3["phases"][0] if impl3.get("phases") else {}
    results.append({
        "test": "plan_watcher_preserves_progress",
        "pass": len(impl3.get("phases", [])) == 3 and phase1.get("status") == "DONE",
        "detail": f"phases={len(impl3.get('phases', []))}, phase1.status={phase1.get('status')}"
    })

    shutil.rmtree(tmpdir, ignore_errors=True)
    return {"metric": "plan_watcher", "results": results}
```

**Step 2: 注册到 ALL_TESTS 和 METRICS**

METRICS 新增:
```python
"plan_watcher": {
    "description": "PostToolUse plan 文件写入时自动注册 phases",
    "weight": 1.5,
},
```

ALL_TESTS 新增:
```python
"plan_watcher": test_plan_watcher,
```

**Step 3: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 41/41 通过

---

## Task 3: Stop Hook fallback — phases 为空时解析 plan 文件

**Files:**
- Modify: `hooks/stop-hook.py`

**Step 1: 添加 parse_phases_from_plan 函数**

在 stop-hook.py 的工具函数区域添加（复用 plan-watcher 的解析逻辑）：

```python
def parse_phases_from_plan(project_root):
    """从最新 plan 文件解析 Phase 列表（fallback 用）"""
    import re
    plans_dir = project_root / ".claude" / "plans"
    if not plans_dir.exists():
        return []
    plan_files = sorted(plans_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not plan_files:
        return []
    text = plan_files[0].read_text(encoding="utf-8")
    phases = []
    pattern = r'^#{2,3}\s+(?:Phase|Task|阶段)\s*(\d+)\s*[：:.\-—]?\s*(.*?)$'
    for m in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
        num = int(m.group(1))
        name = m.group(2).strip() or f"Phase {num}"
        phases.append({
            "name": f"Phase {num}: {name}" if name != f"Phase {num}" else name,
            "status": "PENDING",
            "error_count": 0,
        })
    return phases
```

**Step 2: 在 implement 检查中添加 fallback**

在 stop-hook.py 的 implement 阶段检查逻辑中，phases 为空时自动解析：

```python
    # ==================== 首次触发 ====================
    if current == "implement" and stage.get("status") == "IN_PROGRESS":
        phases = stage.get("phases", [])

        # fallback: phases 为空时从 plan 文件解析
        if not phases:
            phases = parse_phases_from_plan(project_root)
            if phases:
                stage["phases"] = phases
                save_state(state, state_file)
                log_eval(project_root, state, "phases_fallback",
                         f"从 plan 文件解析到 {len(phases)} 个 Phase")

        # ... 后续逻辑不变
```

同样在 `stop_hook_active` 分支中也添加相同的 fallback。

**Step 3: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 41/41 通过

---

## Task 4: Stop Hook fallback 评测用例

**Files:**
- Modify: `eval/eval-runner.py`

**Step 1: 新增 phases_fallback 评测**

```python
def test_phases_fallback():
    """测试 stop-hook phases 为空时的 plan 文件 fallback"""
    import shutil
    results = []

    # 测试 1: implement IN_PROGRESS + phases=[] + 有 plan 文件 → 自动解析
    tmpdir = _make_test_env()
    state = {
        "version": "1.1", "session_id": "fb-test",
        "project": "test", "task": {"name": "test", "route": "C", "started_at": "2026-04-07T00:00:00Z"},
        "pipeline": [
            {"name": "plan", "status": "DONE"},
            {"name": "implement", "status": "IN_PROGRESS", "phases": [],
             "parallel_group": None, "started_at": "2026-04-07T00:00:00Z"},
            {"name": "audit", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "docs", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "test", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "review", "status": "PENDING"},
            {"name": "remember", "status": "PENDING"},
        ],
        "current_stage": "implement",
        "paused": False,
        "metrics": {"max_retries": 3, "auto_continues": 0, "stages_completed": 0},
    }
    _write_state(tmpdir, state)
    # 创建 plan 文件
    plan_dir = os.path.join(tmpdir, ".claude", "plans")
    os.makedirs(plan_dir, exist_ok=True)
    with open(os.path.join(plan_dir, "test.md"), "w", encoding="utf-8") as f:
        f.write("# Plan\n## Phase 1：搭建\nxxx\n## Phase 2：核心\nyyy\n")
    # 运行 stop-hook
    out, rc = _run_hook(tmpdir, {"session_id": "fb-test"})
    new_state = _read_state(tmpdir)
    impl = next(s for s in new_state["pipeline"] if s["name"] == "implement")
    results.append({
        "test": "fallback_parses_plan",
        "pass": len(impl.get("phases", [])) == 2 and rc == 0 and "block" in out,
        "detail": f"phases={len(impl.get('phases', []))}, rc={rc}"
    })

    # 测试 2: implement IN_PROGRESS + phases=[] + 无 plan 文件 → 不 block
    tmpdir2 = _make_test_env()
    state["pipeline"][1]["phases"] = []
    _write_state(tmpdir2, state)
    out2, rc2 = _run_hook(tmpdir2, {"session_id": "fb-test"})
    results.append({
        "test": "no_plan_no_block",
        "pass": rc2 == 0 and "block" not in out2,
        "detail": f"rc={rc2}, output='{out2[:60]}'"
    })

    shutil.rmtree(tmpdir, ignore_errors=True)
    shutil.rmtree(tmpdir2, ignore_errors=True)
    return {"metric": "phases_fallback", "results": results}
```

**Step 2: 注册**

```python
"phases_fallback": {"description": "Stop hook phases 为空时的 plan 文件 fallback 解析", "weight": 2.0},
```

```python
"phases_fallback": test_phases_fallback,
```

**Step 3: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 43/43 通过

---

## Task 5: Web HUD 多项目支持

**Files:**
- Modify: `scripts/harness.py` (cmd_web_hud + WEB_HUD_HTML)

**Step 1: 重写 cmd_web_hud 支持多项目**

```python
def cmd_web_hud(args):
    """启动多项目 Web HUD 面板"""
    global PROJECT_ROOT, STATE_FILE
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    port = args.port or WEB_HUD_PORT

    class HUDHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == '/api/projects':
                # 返回所有活跃项目列表
                projects = self._find_all_projects()
                self._json_response(projects)

            elif parsed.path == '/api/state':
                # 返回指定项目的 state（?project=路径）
                params = urllib.parse.parse_qs(parsed.query)
                proj_path = params.get("project", [None])[0]
                state = self._load_project_state(proj_path)
                if state:
                    self._json_response(state)
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(WEB_HUD_HTML.encode('utf-8'))

        def _find_all_projects(self):
            projects = []
            # 从 session 索引获取
            index = load_session_index()
            seen = set()
            for sid in sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True):
                proj = index[sid]["project"]
                if proj in seen:
                    continue
                sf = Path(proj) / ".claude" / "harness-state.json"
                if sf.exists():
                    try:
                        state = json.loads(sf.read_text(encoding="utf-8"))
                        projects.append({
                            "path": proj,
                            "name": state.get("project", Path(proj).name),
                            "task": state.get("task", {}).get("name", ""),
                            "current_stage": state.get("current_stage", ""),
                            "session_id": state.get("session_id", ""),
                        })
                        seen.add(proj)
                    except Exception:
                        pass
            # fallback 扫描
            if not projects:
                proj = find_latest_session_project()
                if proj:
                    sf = proj / ".claude" / "harness-state.json"
                    if sf.exists():
                        try:
                            state = json.loads(sf.read_text(encoding="utf-8"))
                            projects.append({
                                "path": str(proj),
                                "name": state.get("project", proj.name),
                                "task": state.get("task", {}).get("name", ""),
                                "current_stage": state.get("current_stage", ""),
                                "session_id": state.get("session_id", ""),
                            })
                        except Exception:
                            pass
            return projects

        def _load_project_state(self, proj_path):
            if proj_path:
                sf = Path(proj_path) / ".claude" / "harness-state.json"
            else:
                sf = STATE_FILE
            try:
                lock = FileLock(str(sf) + ".lock", timeout=2)
                with lock:
                    return json.loads(sf.read_text(encoding="utf-8"))
            except Exception:
                return None

        def _json_response(self, data):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        def log_message(self, format, *a):
            pass

    server = HTTPServer(('0.0.0.0', port), HUDHandler)
    print(f"Dev Harness Web HUD: http://localhost:{port}")
    print("Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nWeb HUD 已停止")
```

**Step 2: 重写 WEB_HUD_HTML 支持多项目 tab + 详细展示**

完整替换 WEB_HUD_HTML 变量，新版包含：
- 顶部项目 tab 栏（自动发现所有活跃项目）
- Pipeline 阶段进度条（带颜色状态）
- Phase 级进度展示（含门禁结果和 error_count）
- Worker 状态展示（如果有）
- 指标面板（auto_continues / errors / stages_completed）
- 2 秒自动刷新

**Step 3: 运行评测**

Run: `python eval/eval-runner.py run-all`
Expected: 43/43 通过（web-hud 改动不影响评测）

---

## Task 6: 文档和版本更新

**Files:**
- Modify: `CLAUDE.md`
- Modify: `hooks/hooks.json` (确认最终格式)

**Step 1: CLAUDE.md 补充 PostToolUse 机制**

在 "Hook 注册机制" 段落后添加:

```markdown
### PostToolUse plan-watcher

`hooks/plan-watcher.py` — plan 文件写入时自动解析 Phase 列表并注册到 harness-state.json。解决 SKILL.md 指引是"概率性"的问题，让 phases 注册变成"确定性"的代码约束。Stop hook 同时有 fallback：phases 为空时主动从 plan 文件解析。
```

**Step 2: 运行完整评测**

Run: `python eval/eval-runner.py run-all`
Expected: 43/43 全通过

---

## 执行顺序

```
Task 1: plan-watcher.py + hooks.json  ← 核心，PostToolUse 自动注册
Task 2: plan-watcher 评测             ← 验证 Task 1
Task 3: stop-hook fallback            ← 兜底，phases 为空时解析 plan
Task 4: fallback 评测                 ← 验证 Task 3
Task 5: Web HUD 多项目               ← UI 升级
Task 6: 文档                          ← 收尾
```
