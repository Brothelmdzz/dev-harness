"""
Dev Harness 评测框架
用法:
  python eval-runner.py run <scenario>     # 运行单个评测场景
  python eval-runner.py run-all            # 运行全部场景
  python eval-runner.py report             # 生成评测报告
  python eval-runner.py compare <before> <after>  # 对比两次评测
"""
import json, os, sys, time, subprocess, argparse
from pathlib import Path
from datetime import datetime

EVAL_DIR = Path(__file__).parent
SCENARIOS_DIR = EVAL_DIR / "scenarios"
RESULTS_DIR = EVAL_DIR / "results"
HARNESS_SCRIPT = Path(__file__).parent.parent / "scripts" / "harness.py"
RESOLVER_SCRIPT = Path(__file__).parent.parent / "scripts" / "skill-resolver.py"

# ==================== 评测指标定义 ====================

METRICS = {
    "skill_resolution": {
        "description": "Skill 三层解析是否正确命中预期层级",
        "weight": 1.0,
    },
    "state_management": {
        "description": "harness-state.json 读写是否正确",
        "weight": 1.0,
    },
    "auto_continue": {
        "description": "Stop Hook 是否正确判断续跑",
        "weight": 2.0,  # 核心指标，权重加倍
    },
    "gate_detection": {
        "description": "构建系统自动检测是否正确",
        "weight": 0.5,
    },
    "pipeline_routing": {
        "description": "路线判断和阶段跳过是否正确",
        "weight": 1.0,
    },
    "hook_defense": {
        "description": "Stop Hook 六道防线各自能否正确触发",
        "weight": 2.0,  # 核心指标
    },
    "session_isolation": {
        "description": "Session ID 隔离是否正确过滤非本 session 状态",
        "weight": 1.5,
    },
    "skill_override": {
        "description": "三层 Skill 覆盖优先级是否正确 (L1>L2>L3)",
        "weight": 1.0,
    },
    "parallel_group": {
        "description": "并行组阶段推进逻辑是否正确",
        "weight": 1.5,
    },
    "worker_management": {
        "description": "Worker 状态文件创建/汇总/清理",
        "weight": 1.0,
    },
}

HOOK_SCRIPT = Path(__file__).parent.parent / "hooks" / "stop-hook.py"

# ==================== 测试工具 ====================

def run_cmd(cmd, cwd=None):
    """执行命令并返回 stdout"""
    env = {**os.environ, "DH_EVAL": "1"}
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, env=env)
    return result.stdout.strip(), result.returncode

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}: expected={expected}, actual={actual}")

def assert_contains(text, substr, msg=""):
    if substr not in text:
        raise AssertionError(f"{msg}: '{substr}' not found in output")

# ==================== 评测场景 ====================

def test_skill_resolution():
    """测试三层 Skill 解析"""
    results = []

    # 测试 1: 无 L1/L2 覆盖时，audit 应正确降级到 L3 generic-audit
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} audit --verbose",
                       cwd=os.getcwd())
    if rc == 0:
        info = json.loads(out)
        # 当前环境无 L1/L2 audit skill，应降级到 L3
        # L1/L2 覆盖场景已在 skill_override 维度单独测试
        passed = "audit" in info["name"]
        results.append({"test": "project_audit_resolution", "pass": passed, "detail": f"{info['level']}:{info['name']}"})
    else:
        results.append({"test": "project_audit_resolution", "pass": False, "detail": f"Command failed: rc={rc}"})

    # 测试 2: 对未知 stage 应该返回 L3 generic
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} wiki --verbose",
                       cwd=os.getcwd())
    if rc == 0:
        info = json.loads(out)
        results.append({"test": "generic_wiki_fallback", "pass": info["level"] == "L3",
                        "detail": f"{info['level']}:{info['name']}"})
    else:
        results.append({"test": "generic_wiki_fallback", "pass": False, "detail": f"rc={rc}"})

    # 测试 3: --all 应该返回所有 stage 的解析结果
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} --all",
                       cwd=os.getcwd())
    if rc == 0:
        lines = [l for l in out.split("\n") if l.strip()]
        results.append({"test": "resolve_all_stages", "pass": len(lines) >= 8,
                        "detail": f"{len(lines)} stages resolved"})
    else:
        results.append({"test": "resolve_all_stages", "pass": False, "detail": f"rc={rc}"})

    return {"metric": "skill_resolution", "results": results}

def test_state_management():
    """测试状态文件读写"""
    import tempfile
    results = []
    tmpdir = tempfile.mkdtemp()

    # 创建一个假的 .git 目录让 harness 能找到项目根
    os.makedirs(os.path.join(tmpdir, ".git"))
    os.makedirs(os.path.join(tmpdir, ".claude"))

    # 测试 init
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} init test-task --route B --module test",
                       cwd=tmpdir)
    state_file = os.path.join(tmpdir, ".claude", "harness-state.json")

    if os.path.exists(state_file):
        state = json.loads(open(state_file).read())
        results.append({"test": "init_creates_state", "pass": True, "detail": f"route={state['task']['route']}"})

        # 验证路线 B 应该包含 research
        research = next((s for s in state["pipeline"] if s["name"] == "research"), None)
        results.append({"test": "route_b_has_research", "pass": research and research["status"] == "PENDING",
                        "detail": str(research)})
    else:
        results.append({"test": "init_creates_state", "pass": False, "detail": "State file not created"})

    # 测试 update
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} update research DONE", cwd=tmpdir)
    if os.path.exists(state_file):
        state = json.loads(open(state_file).read())
        research = next((s for s in state["pipeline"] if s["name"] == "research"), None)
        results.append({"test": "update_stage_status", "pass": research and research["status"] == "DONE",
                        "detail": str(research.get("status"))})
    else:
        results.append({"test": "update_stage_status", "pass": False, "detail": "State file missing"})

    # 测试 C-lite 路线应跳过 research/prd/audit/docs/review
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} init clite-task --route C-lite", cwd=tmpdir)
    if os.path.exists(state_file):
        state = json.loads(open(state_file).read())
        skipped = [s["name"] for s in state["pipeline"] if s["status"] == "SKIP"]
        results.append({"test": "clite_skips_stages", "pass": "research" in skipped and "audit" in skipped,
                        "detail": f"Skipped: {skipped}"})
    else:
        results.append({"test": "clite_skips_stages", "pass": False, "detail": "State file missing"})

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "state_management", "results": results}

def test_auto_continue():
    """测试 Stop Hook 的自动续跑判断"""
    import tempfile
    results = []
    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, ".git"))
    os.makedirs(os.path.join(tmpdir, ".claude"))

    hook_script = Path(__file__).parent.parent / "hooks" / "stop-hook.py"

    # 场景 1: implement IN_PROGRESS + 有 PENDING Phase → 应续跑
    state = {
        "version": "1.0", "project": "test",
        "task": {"name": "test", "route": "C", "branch": "", "module": "", "started_at": ""},
        "pipeline": [
            {"name": "plan", "status": "DONE"},
            {"name": "implement", "status": "IN_PROGRESS", "phases": [
                {"name": "Phase 1", "status": "DONE"},
                {"name": "Phase 2", "status": "PENDING"},
            ]},
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
    state_file = os.path.join(tmpdir, ".claude", "harness-state.json")
    with open(state_file, "w") as f:
        json.dump(state, f)

    out, rc = run_cmd(f"python {hook_script}", cwd=tmpdir)
    results.append({
        "test": "continue_next_phase",
        "pass": "Phase 2" in out and "继续" in out,
        "detail": f"output='{out[:80]}'"
    })

    # 场景 2: implement DONE → 应推进到 audit+docs 并行
    state["pipeline"][1]["status"] = "DONE"
    state["pipeline"][1]["phases"][1]["status"] = "DONE"
    state["current_stage"] = "implement"
    with open(state_file, "w") as f:
        json.dump(state, f)

    out, rc = run_cmd(f"python {hook_script}", cwd=tmpdir)
    results.append({
        "test": "continue_to_audit_docs_parallel",
        "pass": "audit" in out and "docs" in out,
        "detail": f"output='{out[:80]}'"
    })

    # 场景 3: paused=True → 不应续跑
    state["paused"] = True
    with open(state_file, "w") as f:
        json.dump(state, f)

    out, rc = run_cmd(f"python {hook_script}", cwd=tmpdir)
    results.append({
        "test": "paused_no_continue",
        "pass": out == "",
        "detail": f"output='{out}'"
    })

    # 场景 4: Phase error_count >= 3 → 死循环，不应续跑
    state["paused"] = False
    state["pipeline"][1]["status"] = "IN_PROGRESS"
    state["pipeline"][1]["phases"][1]["status"] = "PENDING"
    state["pipeline"][1]["phases"][1]["error_count"] = 3
    state["current_stage"] = "implement"
    with open(state_file, "w") as f:
        json.dump(state, f)

    out, rc = run_cmd(f"python {hook_script}", cwd=tmpdir)
    results.append({
        "test": "deadloop_no_continue",
        "pass": out == "",
        "detail": f"output='{out}'"
    })

    # 场景 5: 全部 DONE → 不应续跑
    for s in state["pipeline"]:
        s["status"] = "DONE"
    state["current_stage"] = "remember"
    with open(state_file, "w") as f:
        json.dump(state, f)

    out, rc = run_cmd(f"python {hook_script}", cwd=tmpdir)
    results.append({
        "test": "all_done_no_continue",
        "pass": out == "",
        "detail": f"output='{out}'"
    })

    # 清理
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "auto_continue", "results": results}

def test_gate_detection():
    """测试构建系统自动检测"""
    import tempfile
    results = []
    detect_script = Path(__file__).parent.parent / "scripts" / "detect-stack.sh"

    # 测试 gradle 检测
    tmpdir = tempfile.mkdtemp()
    open(os.path.join(tmpdir, "build.gradle"), "w").close()
    out, rc = run_cmd(f"bash {detect_script}", cwd=tmpdir)
    if rc == 0:
        info = json.loads(out)
        results.append({"test": "detect_gradle", "pass": info["stack"] == "gradle",
                        "detail": str(info)})
    else:
        results.append({"test": "detect_gradle", "pass": False, "detail": f"rc={rc}"})
    import shutil; shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 python 检测
    tmpdir = tempfile.mkdtemp()
    open(os.path.join(tmpdir, "pyproject.toml"), "w").close()
    out, rc = run_cmd(f"bash {detect_script}", cwd=tmpdir)
    if rc == 0:
        info = json.loads(out)
        results.append({"test": "detect_python", "pass": info["stack"] == "python",
                        "detail": str(info)})
    else:
        results.append({"test": "detect_python", "pass": False, "detail": f"rc={rc}"})
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 node 检测
    tmpdir = tempfile.mkdtemp()
    open(os.path.join(tmpdir, "package.json"), "w").close()
    out, rc = run_cmd(f"bash {detect_script}", cwd=tmpdir)
    if rc == 0:
        info = json.loads(out)
        results.append({"test": "detect_node", "pass": info["stack"] == "node",
                        "detail": str(info)})
    else:
        results.append({"test": "detect_node", "pass": False, "detail": f"rc={rc}"})
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 unknown 检测
    tmpdir = tempfile.mkdtemp()
    out, rc = run_cmd(f"bash {detect_script}", cwd=tmpdir)
    if rc == 0:
        info = json.loads(out)
        results.append({"test": "detect_unknown", "pass": info["stack"] == "unknown",
                        "detail": str(info)})
    else:
        results.append({"test": "detect_unknown", "pass": False, "detail": f"rc={rc}"})
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "gate_detection", "results": results}

def test_pipeline_routing():
    """测试路线判断和 Pipeline 生成"""
    import tempfile
    results = []

    for route, expected_active in [
        ("B", ["research", "prd", "plan", "implement", "audit", "docs", "test", "review", "remember"]),
        ("A", ["prd", "plan", "implement", "audit", "docs", "test", "review", "remember"]),
        ("C", ["plan", "implement", "audit", "docs", "test", "review", "remember"]),
        ("C-lite", ["implement", "test", "remember"]),
        ("D", ["implement", "test", "remember"]),
    ]:
        tmpdir = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmpdir, ".git"))
        os.makedirs(os.path.join(tmpdir, ".claude"))

        out, rc = run_cmd(f"python {HARNESS_SCRIPT} init test --route {route}", cwd=tmpdir)
        state_file = os.path.join(tmpdir, ".claude", "harness-state.json")

        if os.path.exists(state_file):
            state = json.loads(open(state_file).read())
            active = [s["name"] for s in state["pipeline"] if s["status"] != "SKIP"]
            match = set(active) == set(expected_active)
            results.append({
                "test": f"route_{route}_stages",
                "pass": match,
                "detail": f"expected={expected_active}, actual={active}"
            })
        else:
            results.append({"test": f"route_{route}_stages", "pass": False, "detail": "No state file"})

        import shutil; shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "pipeline_routing", "results": results}

# ==================== 新增: 六道防线测试 ====================

def _make_test_env():
    """创建带 .git + .claude 的临时目录"""
    import tempfile
    tmpdir = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmpdir, ".git"))
    os.makedirs(os.path.join(tmpdir, ".claude"))
    return tmpdir

def _write_state(tmpdir, state):
    state_file = os.path.join(tmpdir, ".claude", "harness-state.json")
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def _read_state(tmpdir):
    state_file = os.path.join(tmpdir, ".claude", "harness-state.json")
    return json.loads(open(state_file, encoding="utf-8").read())

def _run_hook(tmpdir, hook_input=None):
    """运行 stop-hook.py，通过 stdin 传入 hook_input JSON"""
    inp = json.dumps(hook_input or {})
    result = subprocess.run(
        ["python", str(HOOK_SCRIPT)],
        input=inp, capture_output=True, text=True, cwd=tmpdir
    )
    return result.stdout.strip(), result.returncode

def _base_state(session_id="test-sess", current_stage="implement", stage_status="IN_PROGRESS"):
    """构造一个标准的测试 state"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "version": "1.1",
        "session_id": session_id,
        "project": "test",
        "task": {"name": "test", "route": "C", "branch": "", "module": "", "started_at": now},
        "pipeline": [
            {"name": "plan", "status": "DONE"},
            {"name": "implement", "status": stage_status, "phases": [
                {"name": "Phase 1", "status": "DONE"},
                {"name": "Phase 2", "status": "PENDING"},
            ]},
            {"name": "audit", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "docs", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "test", "status": "PENDING", "parallel_group": "post-implement"},
            {"name": "review", "status": "PENDING"},
            {"name": "remember", "status": "PENDING"},
        ],
        "current_stage": current_stage,
        "paused": False,
        "metrics": {"max_retries": 3, "auto_continues": 0, "stages_completed": 1,
                    "total_errors": 0, "auto_fixed": 0, "blocking": 0},
    }

def test_hook_defense():
    """测试 Stop Hook 六道防线"""
    import shutil
    from datetime import datetime, timezone, timedelta
    results = []

    # 防线 1: Rate Limit 检测
    tmpdir = _make_test_env()
    state = _base_state()
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {
        "session_id": "test-sess",
        "last_assistant_message": "I've hit your rate limit. Please wait.",
    })
    reloaded = _read_state(tmpdir)
    results.append({
        "test": "defense_rate_limit",
        "pass": reloaded.get("paused") == True and reloaded.get("pause_reason") == "rate_limit",
        "detail": f"paused={reloaded.get('paused')}, reason={reloaded.get('pause_reason')}"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 防线 2: 上下文溢出放行
    tmpdir = _make_test_env()
    state = _base_state()
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {
        "session_id": "test-sess",
        "context_window": {"used": 850000, "total": 1000000},
    })
    results.append({
        "test": "defense_context_overflow",
        "pass": "continue" in out.lower() or '"continue"' in out,
        "detail": f"output='{out[:80]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 防线 3: 单阶段超时
    tmpdir = _make_test_env()
    state = _base_state()
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=35)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["pipeline"][1]["started_at"] = old_time
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {"session_id": "test-sess"})
    results.append({
        "test": "defense_stage_timeout",
        "pass": rc == 0 and ("block" not in out.lower() if out else True),
        "detail": f"rc={rc}, output='{out[:60]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 防线 4: 总运行时长超时
    tmpdir = _make_test_env()
    state = _base_state()
    old_time = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    state["task"]["started_at"] = old_time
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {"session_id": "test-sess"})
    results.append({
        "test": "defense_total_timeout",
        "pass": rc == 0 and ("block" not in out.lower() if out else True),
        "detail": f"rc={rc}, output='{out[:60]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 防线 5: 滑动窗口死循环
    tmpdir = _make_test_env()
    state = _base_state()
    _write_state(tmpdir, state)
    # 写入 12 条最近 5 分钟内的 auto_continue 事件
    eval_log = os.path.join(tmpdir, ".claude", "harness-eval.jsonl")
    now = datetime.now(timezone.utc)
    with open(eval_log, "w", encoding="utf-8") as f:
        for i in range(12):
            ts = (now - timedelta(seconds=i*20)).strftime("%Y-%m-%dT%H:%M:%SZ")
            f.write(json.dumps({"timestamp": ts, "event": "auto_continue", "stage": "implement"}) + "\n")
    out, rc = _run_hook(tmpdir, {"session_id": "test-sess"})
    results.append({
        "test": "defense_sliding_window",
        "pass": rc == 0 and ("block" not in out.lower() if out else True),
        "detail": f"rc={rc}, output='{out[:60]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 防线 6: error_count >= max_retries
    tmpdir = _make_test_env()
    state = _base_state()
    state["pipeline"][1]["phases"][1]["error_count"] = 3
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {"session_id": "test-sess"})
    results.append({
        "test": "defense_error_max_retries",
        "pass": rc == 0 and out == "",
        "detail": f"rc={rc}, output='{out[:60]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "hook_defense", "results": results}

# ==================== 新增: Session ID 隔离测试 ====================

def test_session_isolation():
    """测试 Session ID 隔离"""
    import shutil
    results = []

    # 测试 1: 匹配的 session_id → 正常续跑
    tmpdir = _make_test_env()
    state = _base_state(session_id="aaa111")
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {"session_id": "aaa111"})
    results.append({
        "test": "session_match_continues",
        "pass": "block" in out.lower() or "Phase 2" in out,
        "detail": f"output='{out[:80]}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 2: 不匹配的 session_id → 跳过不干预
    tmpdir = _make_test_env()
    state = _base_state(session_id="aaa111")
    _write_state(tmpdir, state)
    out, rc = _run_hook(tmpdir, {"session_id": "bbb222"})
    results.append({
        "test": "session_mismatch_skips",
        "pass": rc == 0 and out == "",
        "detail": f"rc={rc}, output='{out}'"
    })
    shutil.rmtree(tmpdir, ignore_errors=True)

    return {"metric": "session_isolation", "results": results}

# ==================== 新增: Skill 覆盖优先级测试 ====================

def test_skill_override():
    """测试 L1 > L2 > L3 覆盖优先级"""
    import tempfile, shutil
    results = []

    # 测试 1: L1 项目层覆盖 — 在项目目录放一个 .claude/skills/audit/SKILL.md
    tmpdir = _make_test_env()
    l1_dir = os.path.join(tmpdir, ".claude", "skills", "audit")
    os.makedirs(l1_dir)
    with open(os.path.join(l1_dir, "SKILL.md"), "w") as f:
        f.write("---\nname: audit\ndescription: project audit\n---\n# L1 Audit")
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} audit --verbose --project-dir {tmpdir}")
    if rc == 0 and out:
        try:
            info = json.loads(out)
            results.append({
                "test": "l1_overrides_l3",
                "pass": info.get("level") == "L1",
                "detail": f"{info.get('level')}:{info.get('name')}"
            })
        except json.JSONDecodeError:
            results.append({"test": "l1_overrides_l3", "pass": False, "detail": f"JSON parse error: {out[:60]}"})
    else:
        results.append({"test": "l1_overrides_l3", "pass": False, "detail": f"rc={rc}, out={out[:60]}"})
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 2: 无 L1 → 应 fallback 到 L2 或 L3
    tmpdir = _make_test_env()
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} audit --verbose --project-dir {tmpdir}")
    if rc == 0 and out:
        try:
            info = json.loads(out)
            results.append({
                "test": "no_l1_fallback",
                "pass": info.get("level") in ("L2", "L3"),
                "detail": f"{info.get('level')}:{info.get('name')}"
            })
        except json.JSONDecodeError:
            results.append({"test": "no_l1_fallback", "pass": False, "detail": f"JSON parse error: {out[:60]}"})
    else:
        results.append({"test": "no_l1_fallback", "pass": False, "detail": f"rc={rc}, out={out[:60]}"})
    shutil.rmtree(tmpdir, ignore_errors=True)

    # 测试 3: L3 内置兜底 — wiki 阶段通常只有 L3
    out, rc = run_cmd(f"python {RESOLVER_SCRIPT} wiki --verbose")
    if rc == 0 and out:
        try:
            info = json.loads(out)
            results.append({
                "test": "l3_builtin_fallback",
                "pass": info.get("level") == "L3",
                "detail": f"{info.get('level')}:{info.get('name')}"
            })
        except json.JSONDecodeError:
            results.append({"test": "l3_builtin_fallback", "pass": False, "detail": f"JSON parse error: {out[:60]}"})
    else:
        results.append({"test": "l3_builtin_fallback", "pass": False, "detail": f"rc={rc}, out={out[:60]}"})

    return {"metric": "skill_override", "results": results}

# ==================== 新增: 并行组测试 ====================

def test_parallel_group():
    """测试 parallel_group 分组逻辑"""
    import shutil
    results = []

    # 测试 1: implement DONE 后推进到并行组第一个阶段
    tmpdir = _make_test_env()
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} init parallel-test --route C", cwd=tmpdir)
    out, rc = run_cmd(f"python {HARNESS_SCRIPT} update implement DONE", cwd=tmpdir)
    state = _read_state(tmpdir)
    results.append({
        "test": "parallel_group_advance",
        "pass": state["current_stage"] in ("audit", "docs", "test"),
        "detail": f"current_stage={state['current_stage']}"
    })

    # 测试 2: 并行组内一个 DONE，组未全完成时不推进到 review
    run_cmd(f"python {HARNESS_SCRIPT} update audit DONE", cwd=tmpdir)
    state = _read_state(tmpdir)
    review = next(s for s in state["pipeline"] if s["name"] == "review")
    results.append({
        "test": "parallel_group_partial",
        "pass": review["status"] == "PENDING" and state["current_stage"] != "review",
        "detail": f"review.status={review['status']}, current={state['current_stage']}"
    })

    # 测试 3: 并行组全部 DONE 后推进到 review
    run_cmd(f"python {HARNESS_SCRIPT} update docs DONE", cwd=tmpdir)
    run_cmd(f"python {HARNESS_SCRIPT} update test DONE", cwd=tmpdir)
    state = _read_state(tmpdir)
    results.append({
        "test": "parallel_group_all_done",
        "pass": state["current_stage"] == "review",
        "detail": f"current_stage={state['current_stage']}"
    })

    shutil.rmtree(tmpdir, ignore_errors=True)
    return {"metric": "parallel_group", "results": results}

# ==================== 新增: Worker 管理测试 ====================

def test_worker_management():
    """测试 Worker 状态文件管理"""
    import shutil
    results = []
    tmpdir = _make_test_env()

    # 测试 1: worker-report 创建文件
    out, rc = run_cmd(
        f"python {HARNESS_SCRIPT} worker-report w1 --phase Phase1 --status DONE --branch dh-w1",
        cwd=tmpdir)
    worker_file = os.path.join(tmpdir, ".claude", "workers", "worker-w1.json")
    results.append({
        "test": "worker_report_creates_file",
        "pass": os.path.exists(worker_file) and rc == 0,
        "detail": f"exists={os.path.exists(worker_file)}"
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
    run_cmd(f"python {HARNESS_SCRIPT} worker-cleanup", cwd=tmpdir)
    workers_dir = os.path.join(tmpdir, ".claude", "workers")
    results.append({
        "test": "worker_cleanup",
        "pass": not os.path.exists(workers_dir),
        "detail": f"dir_exists={os.path.exists(workers_dir)}"
    })

    shutil.rmtree(tmpdir, ignore_errors=True)
    return {"metric": "worker_management", "results": results}

# ==================== 评测执行器 ====================

ALL_TESTS = {
    "skill_resolution": test_skill_resolution,
    "state_management": test_state_management,
    "auto_continue": test_auto_continue,
    "gate_detection": test_gate_detection,
    "pipeline_routing": test_pipeline_routing,
    "hook_defense": test_hook_defense,
    "session_isolation": test_session_isolation,
    "skill_override": test_skill_override,
    "parallel_group": test_parallel_group,
    "worker_management": test_worker_management,
}

def run_scenario(name):
    if name not in ALL_TESTS:
        print(f"未知场景: {name}. 可选: {list(ALL_TESTS.keys())}")
        return None

    print(f"运行评测: {name}")
    start = time.time()
    try:
        result = ALL_TESTS[name]()
        result["duration_sec"] = round(time.time() - start, 2)
        result["timestamp"] = datetime.now().isoformat()

        passed = sum(1 for r in result["results"] if r["pass"])
        total = len(result["results"])
        print(f"  结果: {passed}/{total} 通过 ({result['duration_sec']}s)")
        for r in result["results"]:
            icon = "PASS" if r["pass"] else "FAIL"
            print(f"    [{icon}] {r['test']}: {r['detail'][:60]}")

        return result
    except Exception as e:
        print(f"  错误: {e}")
        return {"metric": name, "results": [], "error": str(e), "duration_sec": round(time.time() - start, 2)}

def run_all():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []

    for name in ALL_TESTS:
        result = run_scenario(name)
        if result:
            all_results.append(result)

    # 汇总
    print("\n" + "=" * 60)
    print("评测汇总")
    print("=" * 60)

    total_pass = 0
    total_tests = 0
    weighted_score = 0
    max_weighted = 0

    for result in all_results:
        metric_name = result["metric"]
        weight = METRICS.get(metric_name, {}).get("weight", 1.0)
        passed = sum(1 for r in result["results"] if r["pass"])
        total = len(result["results"])
        total_pass += passed
        total_tests += total

        rate = passed / total if total > 0 else 0
        weighted_score += rate * weight
        max_weighted += weight

        print(f"  {metric_name:<20} {passed}/{total} ({rate*100:.0f}%)  weight={weight}")

    overall = weighted_score / max_weighted if max_weighted > 0 else 0
    print(f"\n  总计: {total_pass}/{total_tests} 通过")
    print(f"  加权得分: {overall*100:.1f}%")

    # 保存结果
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": all_results,
        "summary": {
            "total_pass": total_pass,
            "total_tests": total_tests,
            "weighted_score": round(overall, 4),
        },
    }
    result_file = RESULTS_DIR / f"eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    result_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n  结果已保存: {result_file}")

    return report

def cmd_report(args):
    """列出历史评测结果"""
    results = sorted(RESULTS_DIR.glob("eval-*.json"))
    if not results:
        print("无评测记录")
        return

    print(f"{'时间':<22} {'通过率':>8} {'加权分':>8}")
    print("-" * 42)
    for r in results[-10:]:  # 最近 10 次
        data = json.loads(r.read_text())
        s = data["summary"]
        ts = data["timestamp"][:19]
        rate = f"{s['total_pass']}/{s['total_tests']}"
        score = f"{s['weighted_score']*100:.1f}%"
        print(f"  {ts}  {rate:>8}  {score:>8}")

def cmd_compare(args):
    """对比两次评测"""
    results = sorted(RESULTS_DIR.glob("eval-*.json"))
    if len(results) < 2:
        print("需要至少 2 次评测结果才能对比")
        return

    before = json.loads(results[-2].read_text())
    after = json.loads(results[-1].read_text())

    print(f"对比: {results[-2].name} vs {results[-1].name}")
    print(f"{'指标':<20} {'之前':>8} {'之后':>8} {'变化':>8}")
    print("-" * 50)

    b_score = before["summary"]["weighted_score"]
    a_score = after["summary"]["weighted_score"]
    delta = a_score - b_score
    sign = "+" if delta >= 0 else ""
    print(f"  {'加权总分':<18} {b_score*100:.1f}%  {a_score*100:.1f}%  {sign}{delta*100:.1f}%")

# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Dev Harness 评测")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run")
    p_run.add_argument("scenario", nargs="?")

    sub.add_parser("run-all")
    sub.add_parser("report")
    sub.add_parser("compare")

    args = parser.parse_args()
    if args.cmd == "run":
        if args.scenario:
            run_scenario(args.scenario)
        else:
            print(f"可用场景: {list(ALL_TESTS.keys())}")
    elif args.cmd == "run-all":
        run_all()
    elif args.cmd == "report":
        cmd_report(args)
    elif args.cmd == "compare":
        cmd_compare(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
