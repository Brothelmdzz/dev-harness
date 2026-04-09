"""
Dev Harness — 状态管理 + HUD 面板 + Hook 入口
用法:
  python harness.py init <task_name> [--route B] [--module portal]
  python harness.py check-continue
  python harness.py update <stage> <status> [--phase N] [--gate build=pass]
  python harness.py hud [--watch]
  python harness.py eval [--report]
"""
import json, os, sys, time, glob, argparse, uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from filelock import FileLock
except ImportError:
    # 无 filelock 时降级为无操作锁（单 Agent 场景够用，多 Agent 并行时建议安装）
    class FileLock:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

# ==================== 路径 ====================

def find_project_root(override=None):
    """定位项目根：override 参数 > DH_PROJECT 环境变量 > 向上查找 .git"""
    if override:
        return Path(override).resolve()
    env = os.environ.get("DH_PROJECT")
    if env:
        return Path(env).resolve()
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()

PROJECT_ROOT = find_project_root()
STATE_FILE = PROJECT_ROOT / ".claude" / "harness-state.json"
CONFIG_FILE = PROJECT_ROOT / ".claude" / "dev-config.yml"
PLANS_DIR = PROJECT_ROOT / ".claude" / "plans"
EVAL_LOG = PROJECT_ROOT / ".claude" / "harness-eval.jsonl"

def set_project_root(root):
    """统一切换项目根目录，同步更新所有派生路径"""
    global PROJECT_ROOT, STATE_FILE, CONFIG_FILE, PLANS_DIR, EVAL_LOG, AUTOLOOP_LOG, WORKERS_DIR
    PROJECT_ROOT = Path(root).resolve()
    STATE_FILE = PROJECT_ROOT / ".claude" / "harness-state.json"
    CONFIG_FILE = PROJECT_ROOT / ".claude" / "dev-config.yml"
    PLANS_DIR = PROJECT_ROOT / ".claude" / "plans"
    EVAL_LOG = PROJECT_ROOT / ".claude" / "harness-eval.jsonl"
    AUTOLOOP_LOG = PROJECT_ROOT / ".claude" / "autoloop-results.log"
    WORKERS_DIR = PROJECT_ROOT / ".claude" / "workers"

# 中央 session 索引：session_id → 项目路径
SESSION_INDEX = Path.home() / ".claude" / "dev-harness-sessions.json"

def load_session_index():
    if SESSION_INDEX.exists():
        try:
            return json.loads(SESSION_INDEX.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_session_index(index):
    SESSION_INDEX.parent.mkdir(parents=True, exist_ok=True)
    SESSION_INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

def register_session(session_id, project_path):
    """注册 session → 项目路径映射"""
    index = load_session_index()
    index[session_id] = {
        "project": str(project_path),
        "started_at": now_iso(),
    }
    # 清理超过 50 条的旧记录
    if len(index) > 50:
        sorted_keys = sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True)
        index = {k: index[k] for k in sorted_keys[:50]}
    save_session_index(index)

def find_latest_session_project():
    """从中央索引找到最近活跃 session 的项目路径，索引为空时扫描常见位置"""
    index = load_session_index()
    # 优先从索引查找
    if index:
        for sid in sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True):
            proj = Path(index[sid]["project"])
            state_file = proj / ".claude" / "harness-state.json"
            if state_file.exists():
                return proj
    # fallback: 扫描常见工作目录下的 harness-state.json
    scan_roots = []
    # Windows: C:\work\*  macOS/Linux: ~/work/*, ~/projects/*
    home = Path.home()
    if os.name == "nt":
        scan_roots.append(Path("C:/work"))
    scan_roots.extend([home / "work", home / "projects", home / "dev"])
    candidates = []
    for root in scan_roots:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if not d.is_dir():
                continue
            sf = d / ".claude" / "harness-state.json"
            if sf.exists():
                candidates.append((sf.stat().st_mtime, d))
    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None

# ==================== 状态读写 ====================

def _state_lock():
    return FileLock(str(STATE_FILE) + ".lock", timeout=10)

def load_state():
    try:
        with _state_lock():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    with _state_lock():
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def load_and_update_state(updater_fn):
    """原子化 read-modify-write：在同一把锁内读取、修改、保存状态
    返回更新后的 state dict（文件不存在时返回 None）"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _state_lock():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        updater_fn(state)
        state["updated_at"] = now_iso()
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ==================== 初始化 ====================

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

ROUTE_STAGES = {
    "B":      ["research", "prd", "plan", "implement", "audit", "docs", "test", "review", "remember"],
    "A":      ["prd", "plan", "implement", "audit", "docs", "test", "review", "remember"],
    "C":      ["plan", "implement", "audit", "docs", "test", "review", "remember"],
    "C-lite": ["implement", "test", "remember"],
    "D":      ["implement", "test", "remember"],
}

def cmd_init(args):
    route = args.route or "C"
    mode = getattr(args, 'mode', None) or "pipeline"
    active_stages = ROUTE_STAGES.get(route, ROUTE_STAGES["C"])

    # single 模式: pipeline 只含指定的 skill 阶段
    if mode == "single" and getattr(args, 'skills', None):
        active_stages = args.skills.split(",")

    pipeline = []
    for stage in DEFAULT_PIPELINE:
        s = dict(stage)
        if s["name"] in active_stages:
            s["status"] = "PENDING"
        else:
            s["status"] = "SKIP"
        pipeline.append(s)

    session_id = args.session_id or uuid.uuid4().hex[:12]

    state = {
        "version": "1.1",
        "session_id": session_id,
        "mode": mode,
        "project": PROJECT_ROOT.name,
        "task": {
            "name": args.task_name,
            "route": route,
            "branch": args.branch or "",
            "module": args.module or "",
            "started_at": now_iso(),
        },
        "pipeline": pipeline,
        "current_stage": next((s["name"] for s in pipeline if s["status"] == "PENDING"), None),
        "paused": False,
        "metrics": {
            "total_errors": 0,
            "auto_fixed": 0,
            "blocking": 0,
            "max_retries": 3,
            "stages_completed": 0,
            "auto_continues": 0,
        },
    }
    save_state(state)

    # 预创建标准目录结构（防止 Claude 自行创建不一致的目录名）
    for d in ["researches", "plans", "reports", "project-design"]:
        (PROJECT_ROOT / ".claude" / d).mkdir(parents=True, exist_ok=True)

    # 评测模式下不注册 session（避免临时目录污染索引）
    if not os.environ.get("DH_EVAL"):
        register_session(session_id, PROJECT_ROOT)
    print(json.dumps({"action": "init", "task": args.task_name, "route": route, "session_id": session_id}, ensure_ascii=False))

# ==================== 自动续跑检查（Stop Hook 调用） ====================

def cmd_check_continue(args):
    state = load_state()
    if not state:
        return  # 没有 harness 会话

    if state.get("paused"):
        return

    current = state.get("current_stage")
    if not current:
        return

    pipeline = state["pipeline"]
    stage = next((s for s in pipeline if s["name"] == current), None)
    if not stage:
        return

    # implement 阶段: 检查 Phase 进度
    if current == "implement" and stage["status"] == "IN_PROGRESS":
        phases = stage.get("phases", [])
        blocked = [p for p in phases if p.get("error_count", 0) >= state["metrics"]["max_retries"]]
        if blocked:
            return  # 死循环

        pending = [p for p in phases if p["status"] == "PENDING"]
        if pending:
            print(f"继续实现下一个 Phase: {pending[0].get('name', 'Phase ' + str(phases.index(pending[0])+1))}")
            log_eval_event(state, "auto_continue", f"implement phase -> {pending[0].get('name')}")
            return

        # 所有 Phase 完成
        stage["status"] = "DONE"
        stage["completed_at"] = now_iso()
        state["metrics"]["stages_completed"] += 1

    # 当前阶段已完成，找下一个
    if stage["status"] == "DONE":
        next_stages = find_next_runnable(pipeline, current)
        if not next_stages:
            return  # 全部完成

        # 更新 current_stage（单次 save）
        state["current_stage"] = next_stages[0]
        for ns in next_stages:
            for s in pipeline:
                if s["name"] == ns:
                    s["status"] = "PENDING"
        state["metrics"]["auto_continues"] += 1
        save_state(state)

        if len(next_stages) == 1:
            msg = f"继续执行 {next_stages[0]} 阶段"
        else:
            msg = f"并行启动 {' + '.join(next_stages)} 阶段"
        print(msg)
        log_eval_event(state, "auto_continue", msg)
        return

    # IN_PROGRESS 但不是 implement → 不干预（可能还在跑）

def find_next_runnable(pipeline, current_name):
    """找到下一个可执行的阶段组（同 parallel_group 的阶段一起返回）"""
    found_current = False
    for s in pipeline:
        if s["name"] == current_name:
            found_current = True
            continue
        if not found_current:
            continue
        if s["status"] != "PENDING":
            continue
        group = s.get("parallel_group")
        if group:
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps["status"] == "PENDING"]
        return [s["name"]]
    return []

# ==================== 通知集成 ====================

def _try_notify_pipeline(state, new_status):
    """Pipeline 完成或失败时触发桌面通知（静默失败，不影响主流程）"""
    if new_status not in ("DONE", "FAILED"):
        return
    pipeline = state.get("pipeline", [])
    # DONE: 检查是否全部完成
    if new_status == "DONE":
        if not all(s["status"] in ("DONE", "SKIP") for s in pipeline):
            return
    # FAILED: 立即通知
    try:
        from importlib.util import spec_from_file_location, module_from_spec
        notify_path = Path(__file__).resolve().parent / "notify.py"
        if not notify_path.exists():
            return
        spec = spec_from_file_location("notify", str(notify_path))
        notify = module_from_spec(spec)
        spec.loader.exec_module(notify)
        notify.notify_pipeline_result(state)
    except Exception:
        pass  # 通知失败不应阻塞主流程

# ==================== 状态更新 ====================

def cmd_update(args):
    """原子化状态更新：read-modify-write 在同一把锁内完成（修复 C1+C2）"""
    stage_name = args.stage
    new_status = args.status.upper()

    def updater(state):
        for s in state["pipeline"]:
            if s["name"] == stage_name:
                prev_status = s["status"]
                s["status"] = new_status
                if new_status == "DONE":
                    s["completed_at"] = now_iso()
                    # 幂等保护: 只在首次 DONE 时计数
                    if prev_status != "DONE":
                        state["metrics"]["stages_completed"] += 1
                elif new_status == "IN_PROGRESS":
                    s["started_at"] = now_iso()

                # Phase 级更新
                if args.phase is not None and "phases" in s:
                    idx = args.phase - 1
                    if 0 <= idx < len(s["phases"]):
                        p = s["phases"][idx]
                        if args.gate:
                            for g in args.gate:
                                parts = g.split("=", 1)
                                if len(parts) == 2:
                                    if "gates" not in p:
                                        p["gates"] = {}
                                    p["gates"][parts[0]] = parts[1].lower() == "pass"

                # 错误计数
                if args.error:
                    state["metrics"]["total_errors"] += 1
                    if args.auto_fixed:
                        state["metrics"]["auto_fixed"] += 1
                    else:
                        state["metrics"]["blocking"] += 1
                break

        # C1: FAILED 状态处理 — 标记并行组内其他 PENDING 为 BLOCKED
        if new_status == "FAILED":
            group = next((s.get("parallel_group") for s in state["pipeline"] if s["name"] == stage_name), None)
            if group:
                for s in state["pipeline"]:
                    if s.get("parallel_group") == group and s["status"] == "PENDING":
                        s["status"] = "BLOCKED"

        # C2: 并行组推进逻辑（在锁内原子执行）
        if new_status == "DONE":
            group = next((s.get("parallel_group") for s in state["pipeline"] if s["name"] == stage_name), None)
            if group:
                group_stages = [s for s in state["pipeline"] if s.get("parallel_group") == group]
                if all(s["status"] == "DONE" for s in group_stages):
                    last_in_group = group_stages[-1]["name"]
                    nxt = find_next_runnable(state["pipeline"], last_in_group)
                    if nxt:
                        state["current_stage"] = nxt[0]
            else:
                nxt = find_next_runnable(state["pipeline"], stage_name)
                if nxt:
                    state["current_stage"] = nxt[0]

    result = load_and_update_state(updater)
    if result is None:
        print("ERROR: 无 harness 状态", file=sys.stderr)
        sys.exit(1)
    # log 在锁外执行（不影响原子性）
    state = load_state()
    if state:
        log_eval_event(state, "update", f"{stage_name} -> {new_status}")
        # Pipeline 完成/失败时发送桌面通知
        _try_notify_pipeline(state, new_status)
    print(json.dumps({"stage": stage_name, "status": new_status}, ensure_ascii=False))

# ==================== HUD 面板 ====================

def cmd_hud(args):
    if getattr(args, 'project', None):
        set_project_root(args.project)
    elif not STATE_FILE.exists():
        proj = find_latest_session_project()
        if proj:
            set_project_root(proj)

    while True:
        state = load_state()
        if not state:
            print("等待 harness 会话启动...")
            if not args.watch:
                return
            time.sleep(3)
            continue

        os.system("cls" if os.name == "nt" else "clear")
        render_hud(state)

        if not args.watch:
            return
        time.sleep(5)

def display_width(s):
    """计算字符串的终端显示宽度（中文字符占 2 列）"""
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ('F', 'W'):
            w += 2
        else:
            w += 1
    return w

def pad_to_width(s, width):
    """将字符串填充到指定终端宽度"""
    dw = display_width(s)
    if dw >= width:
        return s
    return s + " " * (width - dw)

def render_hud(state):
    task = state.get("task", {})
    metrics = state.get("metrics", {})
    pipeline = state.get("pipeline", [])
    current = state.get("current_stage", "")

    W = 60
    print("+" + "=" * W + "+")
    print(f"| {'Dev Harness v1.0':^{W}} |")
    updated = state.get("updated_at", "")[:19].replace("T", " ")
    print(f"| {updated:^{W}} |")
    print("+" + "=" * W + "+")
    proj_line = f"Project: {state.get('project', '?')}"
    print(f"| {pad_to_width(proj_line, W)} |")
    task_line = f"Task: {task.get('name', '?')}  Route: {task.get('route', '?')}  Branch: {task.get('branch', '')}"
    print(f"| {pad_to_width(task_line, W)} |")
    print("+" + "-" * W + "+")

    # Pipeline 进度
    for s in pipeline:
        name = s["name"]
        status = s["status"]
        is_current = (name == current)

        # 状态图标
        if status == "DONE":
            icon = "[OK]"
        elif status == "IN_PROGRESS":
            icon = "[>>]"
        elif status == "SKIP":
            icon = "[--]"
        elif status == "BLOCKED":
            icon = "[!!]"
        else:
            icon = "[  ]"

        marker = ">>>" if is_current else "   "
        source = s.get("skill_source", "")

        # 耗时
        duration = ""
        if s.get("completed_at") and s.get("started_at"):
            try:
                t0 = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
                t1 = datetime.fromisoformat(s["completed_at"].replace("Z", "+00:00"))
                dur_sec = int((t1 - t0).total_seconds())
                duration = f"{dur_sec//60}m{dur_sec%60:02d}s"
            except:
                pass

        line = f"{marker} {icon} {name:<12} {status:<14} {duration:<8} {source}"
        print(f"| {pad_to_width(line, W)} |")

        # 如果是 implement 且有 phases，展示 Phase 细节
        if name == "implement" and "phases" in s:
            for i, p in enumerate(s["phases"]):
                p_icon = "[OK]" if p["status"] == "DONE" else "[>>]" if p["status"] == "IN_PROGRESS" else "[  ]"
                p_name = p.get("name", f"Phase {i+1}")
                gates = p.get("gates", {})
                gate_str = " ".join(f"{'v' if v else 'x'}" for v in gates.values()) if gates else ""
                p_line = f"      {p_icon} {pad_to_width(p_name, 20)} {gate_str}"
                print(f"| {pad_to_width(p_line, W)} |")

    print("+" + "-" * W + "+")

    # 指标
    err_line = f"Errors: {metrics.get('total_errors',0)} total, {metrics.get('auto_fixed',0)} fixed, {metrics.get('blocking',0)} blocking"
    cont_line = f"Auto-continues: {metrics.get('auto_continues',0)}  Stages done: {metrics.get('stages_completed',0)}/{len([s for s in pipeline if s['status'] != 'SKIP'])}"
    print(f"| {pad_to_width(err_line, W)} |")
    print(f"| {pad_to_width(cont_line, W)} |")
    print("+" + "=" * W + "+")

# ==================== 评测日志 ====================

def log_eval_event(state, event_type, detail=""):
    """追加评测事件到 JSONL 日志"""
    entry = {
        "timestamp": now_iso(),
        "project": state.get("project", ""),
        "task": state.get("task", {}).get("name", ""),
        "event": event_type,
        "detail": detail,
        "stage": state.get("current_stage", ""),
        "metrics": state.get("metrics", {}),
    }
    EVAL_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVAL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def cmd_eval(args):
    """生成评测报告"""
    if not EVAL_LOG.exists():
        print("无评测数据")
        return

    events = []
    for line in EVAL_LOG.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            events.append(json.loads(line))

    if not events:
        print("无评测数据")
        return

    # 统计
    auto_continues = [e for e in events if e["event"] == "auto_continue"]
    updates = [e for e in events if e["event"] == "update"]
    projects = set(e["project"] for e in events)

    print("=" * 60)
    print("Dev Harness 评测报告")
    print("=" * 60)
    print(f"数据范围: {events[0]['timestamp'][:10]} ~ {events[-1]['timestamp'][:10]}")
    print(f"涉及项目: {', '.join(projects)}")
    print(f"总事件数: {len(events)}")
    print()
    print("核心指标:")
    print(f"  自动续跑次数:     {len(auto_continues)}")
    print(f"  状态更新次数:     {len(updates)}")
    print(f"  平均每任务续跑:   {len(auto_continues)/max(len(set(e['task'] for e in events)),1):.1f} 次")
    print()

    # 按项目分组
    print("按项目统计:")
    for proj in projects:
        proj_events = [e for e in events if e["project"] == proj]
        proj_ac = [e for e in proj_events if e["event"] == "auto_continue"]
        print(f"  {proj}: {len(proj_events)} 事件, {len(proj_ac)} 次自动续跑")

    if args.report:
        report_path = PROJECT_ROOT / ".claude" / "reports" / f"harness-eval-{datetime.now().strftime('%Y%m%d')}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Dev Harness 评测报告\n\n")
            f.write(f"- 日期: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"- 项目: {', '.join(projects)}\n")
            f.write(f"- 自动续跑: {len(auto_continues)} 次\n")
            f.write(f"- 状态更新: {len(updates)} 次\n")
        print(f"\n报告已保存: {report_path}")

# ==================== AutoLoop 引擎 ====================

AUTOLOOP_LOG = PROJECT_ROOT / ".claude" / "autoloop-results.log"
AUTOLOOP_DEFAULT_TIMEOUT = 7200  # 2 小时

def cmd_autoloop_status(args):
    """显示 AutoLoop 运行状态"""
    state = load_state()
    if not state:
        print("无 harness 会话")
        return

    pipeline = state.get("pipeline", [])
    current = state.get("current_stage", "")
    metrics = state.get("metrics", {})

    done = [s for s in pipeline if s["status"] == "DONE"]
    total = [s for s in pipeline if s["status"] != "SKIP"]
    pending = [s for s in pipeline if s["status"] == "PENDING"]

    started = state.get("task", {}).get("started_at", "")
    elapsed = ""
    if started:
        try:
            t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
            t1 = datetime.now(timezone.utc)
            elapsed_sec = int((t1 - t0).total_seconds())
            elapsed = f"{elapsed_sec//3600}h{(elapsed_sec%3600)//60:02d}m"
        except:
            pass

    print(json.dumps({
        "task": state.get("task", {}).get("name", ""),
        "current_stage": current,
        "progress": f"{len(done)}/{len(total)}",
        "pending_stages": [s["name"] for s in pending],
        "errors": metrics.get("total_errors", 0),
        "auto_continues": metrics.get("auto_continues", 0),
        "elapsed": elapsed,
    }, ensure_ascii=False, indent=2))

def autoloop_log(stage, phase, action, result, detail=""):
    """写入 autoloop-results.log"""
    AUTOLOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} | {stage} | {phase or '-'} | {action} | {result} | {detail}\n"
    with open(AUTOLOOP_LOG, "a", encoding="utf-8") as f:
        f.write(line)

def cmd_autoloop_log(args):
    """显示最近的 AutoLoop 日志"""
    if not AUTOLOOP_LOG.exists():
        print("无 AutoLoop 日志")
        return
    lines = AUTOLOOP_LOG.read_text(encoding="utf-8").strip().split("\n")
    n = args.lines if hasattr(args, 'lines') else 20
    for line in lines[-n:]:
        print(line)

# ==================== Rich HUD（增强版） ====================

def cmd_rich_hud(args):
    """Rich 库增强版 HUD — 彩色面板 + 进度条 + 日志流"""
    try:
        from rich.live import Live
        from rich.table import Table
        from rich.panel import Panel
        from rich.layout import Layout
        from rich.text import Text
    except ImportError:
        print("Rich 库未安装。运行: pip install rich")
        print("回退到基础 HUD...")
        cmd_hud(args)
        return

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=5),
    )
    layout["body"].split_row(
        Layout(name="pipeline", ratio=2),
        Layout(name="log", ratio=1),
    )

    with Live(layout, refresh_per_second=1, screen=True) as live:
        while True:
            state = load_state()
            if not state:
                layout["header"].update(Panel("等待 harness 会话...", border_style="dim"))
                time.sleep(2)
                continue

            task = state.get("task", {})
            metrics = state.get("metrics", {})
            pipeline = state.get("pipeline", [])
            current = state.get("current_stage", "")

            # ===== Header =====
            header_text = (
                f"[bold blue]{task.get('name', '?')}[/]  "
                f"Route: {task.get('route', '?')}  "
                f"Branch: {task.get('branch', '')}  "
                f"Stage: [yellow]{current}[/]"
            )
            layout["header"].update(Panel(header_text, title="Dev Harness v2.0", border_style="blue"))

            # ===== Pipeline 表格 =====
            pt = Table(show_header=True, header_style="bold blue", expand=True)
            pt.add_column("Stage", width=14)
            pt.add_column("Status", width=14)
            pt.add_column("Source", width=16)
            pt.add_column("Time", width=8)

            style_map = {
                "DONE": "green", "IN_PROGRESS": "yellow",
                "SKIP": "dim", "PENDING": "white",
                "BLOCKED": "red bold",
            }

            for s in pipeline:
                name = s["name"]
                status = s["status"]
                st = style_map.get(status, "white")
                is_current = (name == current)
                prefix = ">> " if is_current else "   "
                source = s.get("skill_source", "")

                dur = ""
                if s.get("completed_at") and s.get("started_at"):
                    try:
                        t0 = datetime.fromisoformat(s["started_at"].replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(s["completed_at"].replace("Z", "+00:00"))
                        ds = int((t1 - t0).total_seconds())
                        dur = f"{ds//60}m{ds%60:02d}s"
                    except:
                        pass

                pt.add_row(f"{prefix}{name}", f"[{st}]{status}[/]", source, dur)

                if name == "implement" and "phases" in s:
                    for i, p in enumerate(s["phases"]):
                        pst = style_map.get(p["status"], "dim")
                        gates = p.get("gates", {})
                        gs = " ".join(
                            "[green]v[/]" if v else "[red]x[/]" for v in gates.values()
                        ) if gates else ""
                        pname = p.get("name", f"Phase {i+1}")
                        pt.add_row(f"     {pname}", f"[{pst}]{p['status']}[/]", gs, "")

            layout["pipeline"].update(Panel(pt, title="Pipeline", border_style="blue"))

            # ===== Log 面板 =====
            log_text = Text()
            if AUTOLOOP_LOG.exists():
                try:
                    lines = AUTOLOOP_LOG.read_text(encoding="utf-8").strip().split("\n")[-25:]
                    for line in lines:
                        if "PASS" in line:
                            log_text.append(line + "\n", style="green")
                        elif "FAIL" in line:
                            log_text.append(line + "\n", style="red")
                        elif "FIX" in line or "auto-fix" in line:
                            log_text.append(line + "\n", style="yellow")
                        else:
                            log_text.append(line + "\n")
                except:
                    log_text.append("日志读取错误\n", style="red")
            else:
                log_text.append("等待 AutoLoop 日志...\n", style="dim")

            layout["log"].update(Panel(log_text, title="AutoLoop Log", border_style="yellow"))

            # ===== Footer =====
            m = metrics
            footer_text = (
                f"Errors: {m.get('total_errors',0)} total / "
                f"{m.get('auto_fixed',0)} fixed / "
                f"[red]{m.get('blocking',0)} blocking[/]  |  "
                f"Auto-continues: [cyan]{m.get('auto_continues',0)}[/]  |  "
                f"Stages: {m.get('stages_completed',0)} done"
            )
            layout["footer"].update(Panel(footer_text, title="Metrics", border_style="green"))

            time.sleep(1)

# ==================== Web HUD (localhost:1603) ====================

WEB_HUD_PORT = 1603

WEB_HUD_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Dev Harness HUD</title>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>
  :root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9; --dim:#8b949e;
          --green:#3fb950; --yellow:#d29922; --red:#f85149; --blue:#58a6ff; --purple:#bc8cff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'JetBrains Mono',Consolas,monospace; font-size:14px; padding:20px; }
  h1 { color:var(--blue); font-size:18px; margin-bottom:4px; }
  .meta { color:var(--dim); font-size:12px; margin-bottom:16px; display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .conn-status { display:inline-flex; align-items:center; gap:4px; font-size:11px; padding:2px 8px;
                 border-radius:10px; border:1px solid var(--border); }
  .conn-status .indicator { width:6px; height:6px; border-radius:50%; }
  .conn-live .indicator { background:var(--green); } .conn-live { color:var(--green); }
  .conn-poll .indicator { background:var(--yellow); } .conn-poll { color:var(--yellow); }
  .conn-off .indicator { background:var(--red); } .conn-off { color:var(--red); }
  .tabs-bar { display:flex; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
  .tabs { display:flex; gap:4px; flex-wrap:wrap; flex:1; }
  .show-all { color:var(--dim); font-size:11px; cursor:pointer; user-select:none; }
  .show-all input { vertical-align:middle; margin-right:4px; }
  .tab { padding:6px 16px; border-radius:6px 6px 0 0; cursor:pointer; font-size:12px;
         background:var(--card); border:1px solid var(--border); border-bottom:none; color:var(--dim); }
  .tab.active { background:var(--bg); color:var(--blue); border-color:var(--blue); border-bottom:1px solid var(--bg); }
  .tab .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
  .dot.running { background:var(--yellow); } .dot.done { background:var(--green); } .dot.idle { background:var(--dim); }
  .mobile-select { display:none; width:100%; padding:8px 12px; border-radius:6px; background:var(--card);
                   color:var(--text); border:1px solid var(--border); font-family:inherit; font-size:13px; margin-bottom:16px; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; }
  .card h2 { color:var(--blue); font-size:14px; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:8px; }
  .progress-bar { display:flex; height:6px; border-radius:3px; overflow:hidden; margin-bottom:16px; background:var(--border); }
  .progress-bar .seg { height:100%; transition:flex 0.3s; }
  .seg.done { background:var(--green); } .seg.active { background:var(--yellow); }
  .seg.pending { background:var(--border); } .seg.skip { background:transparent; }
  .stage { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--border); }
  .stage:last-child { border-bottom:none; }
  .stage .icon { width:24px; text-align:center; font-weight:bold; }
  .stage .name { width:100px; }
  .stage .status { flex:1; }
  .stage .dur { width:60px; text-align:right; color:var(--dim); }
  .stage .group-tag { font-size:10px; color:var(--purple); margin-left:4px; }
  .stage.current { background:rgba(88,166,255,0.08); border-radius:4px; margin:0 -8px; padding:6px 8px; }
  .DONE { color:var(--green); } .IN_PROGRESS { color:var(--yellow); }
  .SKIP { color:var(--dim); } .PENDING { color:var(--text); }
  .FAILED,.BLOCKED { color:var(--red); }
  .phase { padding:4px 0 4px 32px; font-size:13px; color:var(--dim); display:flex; align-items:center; gap:6px; }
  .phase .gate { display:inline-block; margin-left:8px; font-size:11px; }
  .gate.pass { color:var(--green); } .gate.fail { color:var(--red); }
  .phase .err { color:var(--red); font-size:11px; }
  .workers { margin-top:12px; padding-top:12px; border-top:1px solid var(--border); }
  .workers h3 { font-size:12px; color:var(--purple); margin-bottom:8px; display:flex; align-items:center; gap:6px; }
  .workers .mode-badge { font-size:10px; padding:1px 6px; border-radius:3px; background:var(--purple); color:var(--bg); }
  .worker { display:flex; gap:8px; font-size:12px; padding:4px 0; border-bottom:1px solid var(--border); align-items:center; }
  .worker:last-child { border-bottom:none; }
  .worker .w-id { color:var(--blue); min-width:80px; }
  .worker .w-phase { color:var(--text); flex:1; }
  .worker .w-branch { color:var(--dim); font-size:11px; }
  .worker .w-status { min-width:70px; text-align:right; font-weight:bold; }
  .batch-group { margin:8px 0; padding:8px; border:1px dashed var(--border); border-radius:4px; }
  .batch-group .batch-label { font-size:10px; color:var(--dim); margin-bottom:4px; }
  .metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .metric { text-align:center; }
  .metric .val { font-size:24px; font-weight:bold; }
  .metric .label { font-size:11px; color:var(--dim); margin-top:4px; }
  .extra-metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:16px;
                   padding-top:12px; border-top:1px solid var(--border); font-size:12px; color:var(--dim); text-align:center; }
  .no-data { color:var(--dim); text-align:center; padding:40px; }
  .session-id { color:var(--purple); font-size:12px; }
  .eval-section { margin-top:16px; }
  .eval-chart-wrap { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; }
  .eval-chart-wrap h2 { color:var(--blue); font-size:14px; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:8px; }
  .eval-chart-wrap canvas { width:100%; height:200px; }
  .eval-legend { display:flex; gap:16px; margin-top:8px; font-size:11px; color:var(--dim); justify-content:center; }
  .eval-legend span { display:flex; align-items:center; gap:4px; }
  .eval-legend .swatch { width:10px; height:10px; border-radius:2px; display:inline-block; }
  @media (max-width:768px) {
    body { padding:12px 8px; font-size:13px; }
    h1 { font-size:16px; }
    .tabs { display:none; }
    .mobile-select { display:block; }
    .grid { grid-template-columns:1fr; gap:12px; }
    .stage .name { width:70px; font-size:12px; }
    .stage .dur { width:50px; font-size:11px; }
    .phase { padding-left:20px; font-size:12px; }
    .metrics { grid-template-columns:repeat(3,1fr); gap:8px; }
    .metric .val { font-size:18px; }
    .extra-metrics { grid-template-columns:repeat(2,1fr); }
    .eval-chart-wrap canvas { height:150px; }
    .worker { flex-wrap:wrap; }
    .worker .w-branch { width:100%; padding-left:88px; }
  }
</style>
</head>
<body>
<h1>Dev Harness HUD</h1>
<div class="meta">
  <span id="conn-indicator" class="conn-status conn-off"><span class="indicator"></span><span id="conn-label">connecting</span></span>
  <span id="updated"></span>
</div>
<div class="tabs-bar"><div class="tabs" id="tabs"></div><label class="show-all"><input type="checkbox" id="show-all" onchange="renderTabs()"> show completed</label></div>
<select class="mobile-select" id="mobile-tabs" onchange="switchProject(this.value)"></select>
<div id="app"><div class="no-data">connecting...</div></div>
<div class="eval-section" id="eval-section" style="display:none">
  <div class="eval-chart-wrap">
    <h2>eval trend</h2>
    <canvas id="eval-canvas"></canvas>
    <div class="eval-legend">
      <span><span class="swatch" style="background:#58a6ff"></span>score</span>
      <span><span class="swatch" style="background:#3fb950"></span>pass rate</span>
    </div>
  </div>
</div>
<script>
var projects=[],activeProject=null,evtSource=null,pollTimer=null,connMode='off',evalData=null;

function setConnMode(m){
  connMode=m;
  var el=document.getElementById('conn-indicator'),lb=document.getElementById('conn-label');
  el.className='conn-status conn-'+m;
  lb.textContent=m==='live'?'realtime':m==='poll'?'polling':'disconnected';
}

function startSSE(){
  if(evtSource){evtSource.close();evtSource=null;}
  if(!activeProject)return;
  try{evtSource=new EventSource('/api/events?project='+encodeURIComponent(activeProject));}catch(e){startPoll();return;}
  evtSource.onopen=function(){setConnMode('live');stopPoll();};
  evtSource.onmessage=function(e){try{render(JSON.parse(e.data));}catch(err){}};
  evtSource.addEventListener('projects',function(e){
    try{projects=JSON.parse(e.data);if(projects.length&&!activeProject){activeProject=projects[0].path;startSSE();}renderTabs();}catch(err){}
  });
  evtSource.onerror=function(){setConnMode('poll');if(evtSource){evtSource.close();evtSource=null;}startPoll();};
}
function startPoll(){if(pollTimer)return;setConnMode('poll');pollTimer=setInterval(function(){refresh();},2000);}
function stopPoll(){if(pollTimer){clearInterval(pollTimer);pollTimer=null;}}

async function loadProjects(){
  try{var r=await fetch('/api/projects');if(r.ok)projects=await r.json();
    if(projects.length&&!activeProject)activeProject=projects[0].path;renderTabs();}catch(e){}
}
function renderTabs(){
  var tabsEl=document.getElementById('tabs'),selEl=document.getElementById('mobile-tabs');
  var showAll=document.getElementById('show-all') && document.getElementById('show-all').checked;
  var visible=showAll?projects:projects.filter(function(p){return !p.completed;});
  // 若当前 active 项目被过滤掉，切到第一个可见项目
  if(visible.length && !visible.find(function(p){return p.path===activeProject;})){
    activeProject=visible[0].path;startSSE();refresh();
  }
  if(!visible.length){
    tabsEl.innerHTML='<span style="color:var(--dim);font-size:11px">no active projects'+(projects.length?' ('+projects.length+' completed, tick to show)':'')+'</span>';
    selEl.innerHTML='';return;
  }
  tabsEl.innerHTML=visible.map(function(p){
    var isActive=p.path===activeProject,stage=p.current_stage||'idle',
        dotClass=p.completed?'done':(stage?'running':'idle');
    return '<div class="tab '+(isActive?'active':'')+'" onclick="switchProject(\''+p.path.replace(/\\/g,'\\\\')+'\')">'
      +'<span class="dot '+dotClass+'"></span>'+p.name+' <span style="color:var(--dim);font-size:10px">'+(p.completed?'done':stage)+'</span></div>';
  }).join('');
  selEl.innerHTML=visible.map(function(p){
    return '<option value="'+p.path.replace(/"/g,'&quot;')+'"'+(p.path===activeProject?' selected':'')+'>'+p.name+' ['+(p.completed?'done':p.current_stage||'idle')+']</option>';
  }).join('');
}
function switchProject(path){activeProject=path;renderTabs();startSSE();refresh();}

async function refresh(){
  if(!activeProject){await loadProjects();return;}
  try{var r=await fetch('/api/state?project='+encodeURIComponent(activeProject));
    if(!r.ok){document.getElementById('app').innerHTML='<div class="no-data">waiting...</div>';return;}
    render(await r.json());
  }catch(e){setConnMode('off');}
}

function render(s){
  var task=s.task||{},metrics=s.metrics||{},pipeline=s.pipeline||[],current=s.current_stage||'';
  document.getElementById('updated').textContent=(s.updated_at||'').replace('T',' ').replace('Z','');
  var active=pipeline.filter(function(x){return x.status!=='SKIP';});
  var barHtml=active.map(function(st){
    var cls=st.status==='DONE'?'done':st.status==='IN_PROGRESS'?'active':'pending';
    return '<div class="seg '+cls+'" style="flex:1" title="'+st.name+': '+st.status+'"></div>';
  }).join('');
  var stagesHtml='';
  for(var si=0;si<pipeline.length;si++){
    var st=pipeline[si],isCur=st.name===current;
    var icon=st.status==='DONE'?'\u2713':st.status==='IN_PROGRESS'?'\u25b6':st.status==='SKIP'?'\u2014':st.status==='FAILED'?'\u2717':'\u25cb';
    var dur=calcDur(st);
    var group=st.parallel_group?'<span class="group-tag">\u2ae8 '+st.parallel_group+'</span>':'';
    stagesHtml+='<div class="stage '+(isCur?'current':'')+'">'
      +'<span class="icon '+st.status+'">'+icon+'</span>'
      +'<span class="name">'+st.name+group+'</span>'
      +'<span class="status '+st.status+'">'+st.status+'</span>'
      +'<span class="dur">'+dur+'</span></div>';
    if(st.name==='implement'){
      if(st.phases&&st.phases.length){
        for(var pi=0;pi<st.phases.length;pi++){
          var p=st.phases[pi];
          var pIcon=p.status==='DONE'?'\u2713':p.status==='IN_PROGRESS'?'\u25b6':'\u25cb';
          var gs='';
          if(p.gates){for(var gk in p.gates){if(p.gates.hasOwnProperty(gk))gs+='<span class="gate '+(p.gates[gk]?'pass':'fail')+'">'+gk+':'+(p.gates[gk]?'\u2713':'\u2717')+'</span>';}}
          var err=p.error_count?'<span class="err">\u26a0'+p.error_count+'</span>':'';
          stagesHtml+='<div class="phase"><span class="'+p.status+'">'+pIcon+'</span> '+(p.name||'Phase')+' '+gs+' '+err+'</div>';
        }
      }
      stagesHtml+=renderWorkers(st);
    }
  }
  var done=pipeline.filter(function(x){return x.status==='DONE';}).length;
  var total=pipeline.filter(function(x){return x.status!=='SKIP';}).length;
  var pct=total?Math.round(done/total*100):0;
  document.getElementById('app').innerHTML=
    '<div class="progress-bar">'+barHtml+'</div>'
    +'<div class="grid">'
    +'<div class="card"><h2>\u4efb\u52a1: '+(task.name||'?')+' <span class="session-id">'+(s.session_id?'#'+s.session_id:'')+'</span></h2>'
    +'<div style="color:var(--dim);font-size:12px;margin-bottom:12px">Route: '+(task.route||'?')+' | Branch: '+(task.branch||'-')+' | Module: '+(task.module||'-')+'</div>'
    +stagesHtml+'</div>'
    +'<div class="card"><h2>\u6307\u6807</h2>'
    +'<div class="metrics">'
    +'<div class="metric"><div class="val" style="color:var(--blue)">'+pct+'%</div><div class="label">\u8fdb\u5ea6 ('+done+'/'+total+')</div></div>'
    +'<div class="metric"><div class="val" style="color:var(--yellow)">'+(metrics.auto_continues||0)+'</div><div class="label">\u81ea\u52a8\u7eed\u8dd1</div></div>'
    +'<div class="metric"><div class="val" style="color:'+((metrics.total_errors||0)>0?'var(--red)':'var(--green)')+'">'+(metrics.total_errors||0)+'</div><div class="label">\u9519\u8bef</div></div>'
    +'</div>'
    +'<div class="extra-metrics">'
    +'<div>\u81ea\u52a8\u4fee\u590d: '+(metrics.auto_fixed||0)+'</div>'
    +'<div>\u963b\u65ad: '+(metrics.blocking||0)+'</div>'
    +'<div>\u91cd\u8bd5\u4e0a\u9650: '+(metrics.max_retries||3)+'</div>'
    +'<div>\u5df2\u5b8c\u6210: '+(metrics.stages_completed||0)+'</div>'
    +'</div></div></div>';
}

function renderWorkers(implStage){
  var mode=implStage.mode||'serial',phases=implStage.phases||[],workers=implStage.workers||[];
  if(mode==='serial'&&!workers.length)return '';
  var html='<div class="workers"><h3>Orchestrator <span class="mode-badge">'+mode+'</span></h3>';
  var batches={};
  for(var i=0;i<phases.length;i++){var b=phases[i].batch||0;if(!batches[b])batches[b]=[];batches[b].push(phases[i]);}
  var batchKeys=Object.keys(batches).sort(function(a,b){return a-b;});
  if(batchKeys.length>1){
    for(var bi=0;bi<batchKeys.length;bi++){
      var bk=batchKeys[bi],bp=batches[bk],allDone=bp.every(function(p){return p.status==='DONE';});
      html+='<div class="batch-group" style="border-color:'+(allDone?'var(--green)':'var(--border)')+'"><div class="batch-label">Batch '+(parseInt(bk)+1)+' ('+bp.length+' phases'+(allDone?' \u2713':'')+')</div>';
      for(var j=0;j<bp.length;j++){
        var pi2=bp[j].status==='DONE'?'\u2713':bp[j].status==='IN_PROGRESS'?'\u25b6':'\u25cb';
        html+='<div class="phase"><span class="'+bp[j].status+'">'+pi2+'</span> '+(bp[j].name||'Phase')+'</div>';
      }
      html+='</div>';
    }
  }
  if(workers.length){
    for(var wi=0;wi<workers.length;wi++){
      var w=workers[wi],sc=w.status==='DONE'?'DONE':w.status==='FAILED'||w.status==='TIMEOUT'?'FAILED':'IN_PROGRESS';
      html+='<div class="worker"><span class="w-id">'+(w.worker_id||'?')+'</span><span class="w-phase">'+(w.phase||'-')+'</span><span class="w-branch">'+(w.worktree_branch||'')+'</span><span class="w-status '+sc+'">'+w.status+'</span></div>';
    }
  }
  return html+'</div>';
}

async function loadEvalHistory(){
  try{var r=await fetch('/api/eval-history');if(!r.ok)return;evalData=await r.json();
    if(evalData&&evalData.length>1){document.getElementById('eval-section').style.display='block';drawEvalChart();}
  }catch(e){}
}

function drawEvalChart(){
  if(!evalData||evalData.length<2)return;
  var canvas=document.getElementById('eval-canvas'),rect=canvas.parentElement.getBoundingClientRect();
  var dpr=window.devicePixelRatio||1,W=Math.floor(rect.width-32),H=200;
  canvas.width=W*dpr;canvas.height=H*dpr;canvas.style.width=W+'px';canvas.style.height=H+'px';
  var ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);
  var pad={top:20,right:20,bottom:40,left:50},cw=W-pad.left-pad.right,ch=H-pad.top-pad.bottom,n=evalData.length;
  ctx.fillStyle='#161b22';ctx.fillRect(0,0,W,H);
  ctx.strokeStyle='#30363d';ctx.lineWidth=0.5;
  for(var gi=0;gi<=4;gi++){var gy=pad.top+ch*gi/4;ctx.beginPath();ctx.moveTo(pad.left,gy);ctx.lineTo(pad.left+cw,gy);ctx.stroke();}
  ctx.fillStyle='#8b949e';ctx.font='10px monospace';ctx.textAlign='right';
  for(var yi=0;yi<=4;yi++){ctx.fillText((100-yi*25)+'%',pad.left-6,pad.top+ch*yi/4+3);}
  ctx.textAlign='center';
  var step=Math.max(1,Math.floor(n/8));
  for(var xi=0;xi<n;xi+=step){ctx.fillText(evalData[xi].date.slice(5),pad.left+(xi/(n-1))*cw,H-pad.bottom+16);}
  function drawLine(key,color){
    ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();
    for(var i=0;i<n;i++){var x=pad.left+(i/(n-1))*cw,y=pad.top+ch*(1-evalData[i][key]);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
    ctx.stroke();ctx.fillStyle=color;
    for(var i2=0;i2<n;i2++){var x2=pad.left+(i2/(n-1))*cw,y2=pad.top+ch*(1-evalData[i2][key]);ctx.beginPath();ctx.arc(x2,y2,3,0,Math.PI*2);ctx.fill();}
  }
  drawLine('score','#58a6ff');drawLine('pass_rate','#3fb950');
  if(n>0){var last=evalData[n-1],lx=Math.min(pad.left+cw+4,W-40);
    ctx.fillStyle='#58a6ff';ctx.font='bold 11px monospace';ctx.textAlign='left';
    ctx.fillText((last.score*100).toFixed(1),lx,pad.top+ch*(1-last.score)+4);
    ctx.fillStyle='#3fb950';ctx.fillText((last.pass_rate*100).toFixed(1),lx,pad.top+ch*(1-last.pass_rate)+4);
  }
}

function calcDur(st){
  if(!st.started_at)return '';
  var end=st.completed_at?new Date(st.completed_at):new Date(),d=(end-new Date(st.started_at))/1000;
  if(d<0)return '';
  return d>3600?Math.floor(d/3600)+'h'+('0'+Math.floor(d%3600/60)).slice(-2)+'m'
       :d>60?Math.floor(d/60)+'m'+('0'+Math.floor(d%60)).slice(-2)+'s'
       :Math.floor(d)+'s';
}

loadProjects().then(function(){startSSE();setTimeout(function(){if(connMode==='off')startPoll();},3000);});
setInterval(loadProjects,10000);
loadEvalHistory();
window.addEventListener('resize',function(){if(evalData)drawEvalChart();});
</script>
</body>
</html>"""

def _scan_eval_results():
    """扫描 eval/results/eval-*.json，返回按时间排序的评测历史"""
    eval_dir = Path(__file__).resolve().parent.parent / "eval" / "results"
    if not eval_dir.exists():
        return []
    history = []
    for f in sorted(eval_dir.glob("eval-*.json")):
        try:
            # 部分旧文件可能包含非 UTF-8 字符（GBK 等），做 fallback
            try:
                raw = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = f.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            summary = data.get("summary", {})
            ts = data.get("timestamp", "")
            date_str = ts[:10] if ts else f.stem.replace("eval-", "")[:8]
            if len(date_str) == 8 and "-" not in date_str:
                date_str = date_str[:4] + "-" + date_str[4:6] + "-" + date_str[6:8]
            total = summary.get("total_tests", 0)
            passed = summary.get("total_pass", 0)
            score = summary.get("weighted_score", 0)
            history.append({
                "date": date_str,
                "score": round(score, 4),
                "pass_count": passed,
                "total": total,
                "pass_rate": round(passed / total, 4) if total > 0 else 0,
            })
        except Exception:
            pass
    return history


def _inject_workers_into_state(state, proj_path):
    """将 workers 目录下的 worker 状态注入 implement 阶段的 state 中"""
    if not state:
        return state
    workers_dir = Path(proj_path) / ".claude" / "workers" if proj_path else WORKERS_DIR
    if not workers_dir.exists():
        return state
    workers = []
    for f in sorted(workers_dir.glob("worker-*.json")):
        try:
            w = json.loads(f.read_text(encoding="utf-8"))
            workers.append(w)
        except Exception:
            pass
    if workers:
        for s in state.get("pipeline", []):
            if s["name"] == "implement":
                s["workers"] = workers
                break
    return state


def cmd_web_hud(args):
    """启动多项目 Web HUD 面板（SSE 实时推送 + 轮询 fallback）"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse
    import threading

    port = args.port or WEB_HUD_PORT

    class HUDHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)

            if parsed.path == '/api/projects':
                projects = self._find_all_projects()
                self._json_response(projects)

            elif parsed.path == '/api/state':
                params = urllib.parse.parse_qs(parsed.query)
                proj_path = params.get("project", [None])[0]
                state = self._load_project_state(proj_path)
                if state:
                    state = _inject_workers_into_state(state, proj_path)
                    self._json_response(state)
                else:
                    self.send_response(404)
                    self.end_headers()

            elif parsed.path == '/api/events':
                # SSE 端点：检测 harness-state.json 的 mtime，变化时推送
                params = urllib.parse.parse_qs(parsed.query)
                proj_path = params.get("project", [None])[0]
                self._handle_sse(proj_path)

            elif parsed.path == '/api/eval-history':
                history = _scan_eval_results()
                self._json_response(history)

            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(WEB_HUD_HTML.encode('utf-8'))

        def _handle_sse(self, proj_path):
            """Server-Sent Events：循环检测 mtime，变化时推送 state"""
            if proj_path:
                sf = Path(proj_path) / ".claude" / "harness-state.json"
            else:
                sf = STATE_FILE
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            last_mtime = 0.0
            projects_mtime = 0.0
            try:
                while True:
                    try:
                        cur_mtime = sf.stat().st_mtime if sf.exists() else 0.0
                    except OSError:
                        cur_mtime = 0.0
                    if cur_mtime > last_mtime:
                        last_mtime = cur_mtime
                        state = self._load_project_state(
                            proj_path if proj_path else None
                        )
                        if state:
                            state = _inject_workers_into_state(state, proj_path)
                            payload = json.dumps(state, ensure_ascii=False)
                            self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                            self.wfile.flush()
                    # 每 10 秒推送一次项目列表
                    now_ts = time.time()
                    if now_ts - projects_mtime > 10:
                        projects_mtime = now_ts
                        projs = self._find_all_projects()
                        payload = json.dumps(projs, ensure_ascii=False)
                        self.wfile.write(f"event: projects\ndata: {payload}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        def _is_completed(self, state):
            """判断任务是否已结束: current_stage 为空 或 无 PENDING/IN_PROGRESS 阶段"""
            if not state.get("current_stage"):
                return True
            pipeline = state.get("pipeline", [])
            return not any(s.get("status") in ("PENDING", "IN_PROGRESS") for s in pipeline)

        def _project_info(self, proj_path, state):
            return {
                "path": str(proj_path),
                "name": state.get("project", Path(proj_path).name),
                "task": state.get("task", {}).get("name", ""),
                "current_stage": state.get("current_stage", ""),
                "session_id": state.get("session_id", ""),
                "completed": self._is_completed(state),
                "updated_at": state.get("updated_at", ""),
            }

        def _find_all_projects(self):
            projects = []
            seen = set()
            index = load_session_index()
            for sid in sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True):
                proj = index[sid]["project"]
                if proj in seen:
                    continue
                sf = Path(proj) / ".claude" / "harness-state.json"
                if sf.exists():
                    try:
                        state = json.loads(sf.read_text(encoding="utf-8"))
                        projects.append(self._project_info(proj, state))
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
                            projects.append(self._project_info(proj, state))
                        except Exception:
                            pass
            return projects

        def _load_project_state(self, proj_path):
            if proj_path:
                # C4 修复: 白名单限制 — 只允许访问已注册的项目路径
                allowed = {p.get("path", "") for p in self._find_all_projects()}
                resolved = str(Path(proj_path).resolve())
                if resolved not in {str(Path(a).resolve()) for a in allowed}:
                    return None
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

    # 使用 ThreadingHTTPServer 以支持 SSE 长连接 + 并发请求
    from http.server import ThreadingHTTPServer
    bind_addr = getattr(args, 'bind', None) or '127.0.0.1'
    server = ThreadingHTTPServer((bind_addr, port), HUDHandler)
    server.daemon_threads = True
    print(f"Dev Harness Web HUD: http://{bind_addr}:{port}")
    print("SSE realtime + polling fallback | Ctrl+C stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nWeb HUD stopped")

# ==================== Implement 模式检测 (C6 代码化) ====================

def parse_phases_from_plan_file(project_root):
    """从最新 plan 文件解析 Phase 列表"""
    import re
    plans_dir = project_root / ".claude" / "plans"
    if not plans_dir.exists():
        return []
    plan_files = sorted(plans_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not plan_files:
        return []
    text = plan_files[0].read_text(encoding="utf-8")
    phases = []
    pattern = r'^#{2,3}\s+(?:Phase|PHASE|Task|TASK|阶段|第)\s*(\d+)\s*(?:阶段)?\s*[：:.\-—]?\s*(.*?)$'
    for m in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
        num = int(m.group(1))
        name = m.group(2).strip() or f"Phase {num}"
        phases.append({
            "name": f"Phase {num}: {name}" if name != f"Phase {num}" else name,
            "status": "PENDING",
            "error_count": 0,
        })
    return phases

ORCHESTRATOR_THRESHOLD = 3  # Phase > 此值触发 Orchestrator 模式

def cmd_detect_mode(args):
    """检测 implement 模式（C6: 代码化强制，不依赖 SKILL.md 建议）"""
    phases = parse_phases_from_plan_file(PROJECT_ROOT)
    mode = "orchestrator" if len(phases) > ORCHESTRATOR_THRESHOLD else "serial"

    def updater(state):
        for s in state["pipeline"]:
            if s["name"] == "implement":
                s["phases"] = phases
                s["mode"] = mode
                break

    result = load_and_update_state(updater)
    if result is None:
        print("ERROR: 无 harness 状态", file=sys.stderr)
        sys.exit(1)
    print(json.dumps({
        "mode": mode,
        "phase_count": len(phases),
        "threshold": ORCHESTRATOR_THRESHOLD,
        "phases": [p["name"] for p in phases],
    }, ensure_ascii=False))

# ==================== C5: Orchestrator 依赖分析（代码化） ====================

def cmd_analyze_deps(args):
    """分析 Plan 中 Phase 的文件依赖关系，输出可并行的批次分组"""
    import re
    plans_dir = PROJECT_ROOT / ".claude" / "plans"
    if not plans_dir.exists():
        print(json.dumps({"error": "no plans directory"}, ensure_ascii=False))
        return
    plan_files = sorted(plans_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not plan_files:
        print(json.dumps({"error": "no plan files"}, ensure_ascii=False))
        return

    text = plan_files[0].read_text(encoding="utf-8")

    # 按 Phase 分割文本
    phase_pattern = r'^#{2,3}\s+(?:Phase|PHASE|Task|TASK|阶段|第)\s*(\d+)\s*(?:阶段)?\s*[：:.\-—]?\s*(.*?)$'
    splits = list(re.finditer(phase_pattern, text, re.MULTILINE | re.IGNORECASE))
    if not splits:
        print(json.dumps({"error": "no phases found"}, ensure_ascii=False))
        return

    # 提取每个 Phase 的改动文件列表
    file_pattern = r'[`"\']([\w./\\-]+\.(?:py|ts|tsx|js|jsx|java|go|rs|yaml|yml|json|sql|md|sh|toml|cfg|html|css|vue|svelte))[`"\']'
    phase_files = {}
    for i, m in enumerate(splits):
        num = int(m.group(1))
        start = m.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        section = text[start:end]
        files = set(re.findall(file_pattern, section))
        phase_files[num] = files

    # 构建依赖图：两个 Phase 有共同文件 → 不可并行
    phase_nums = sorted(phase_files.keys())
    batches = []
    assigned = set()

    for num in phase_nums:
        if num in assigned:
            continue
        batch = [num]
        assigned.add(num)
        batch_files = set(phase_files[num])

        for other in phase_nums:
            if other in assigned:
                continue
            if not batch_files & phase_files[other]:  # 无交集 → 可并行
                batch.append(other)
                assigned.add(other)
                batch_files |= phase_files[other]

        batches.append(batch)

    result = {
        "plan_file": str(plan_files[0].name),
        "total_phases": len(phase_nums),
        "batches": [{"phases": b, "parallel": len(b) > 1} for b in batches],
        "phase_files": {str(k): sorted(v) for k, v in phase_files.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

# ==================== Worker 管理 (Layer 2) ====================

WORKERS_DIR = PROJECT_ROOT / ".claude" / "workers"
WORKER_TIMEOUT_SEC = 600  # Worker 无心跳超过 10 分钟视为超时

def cmd_worker_report(args):
    """Worker 汇报完成状态（H3: 加锁 + heartbeat）"""
    WORKERS_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "worker_id": args.worker_id,
        "phase": args.phase,
        "status": args.status.upper(),
        "worktree_branch": args.branch or "",
        "completed_at": now_iso(),
        "heartbeat_at": now_iso(),
    }
    report_file = WORKERS_DIR / f"worker-{args.worker_id}.json"
    lock = FileLock(str(report_file) + ".lock", timeout=5)
    with lock:
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))

def cmd_worker_status(args):
    """Orchestrator 查询所有 Worker 状态（H3: 超时检测）"""
    if not WORKERS_DIR.exists():
        print(json.dumps({"workers": [], "total": 0, "done": 0, "failed": 0, "timed_out": 0, "all_done": False}, ensure_ascii=False))
        return
    workers = []
    now_dt = datetime.now(timezone.utc)
    for f in sorted(WORKERS_DIR.glob("worker-*.json")):
        try:
            lock = FileLock(str(f) + ".lock", timeout=2)
            with lock:
                w = json.loads(f.read_text(encoding="utf-8"))
            # 超时检测：IN_PROGRESS 且 heartbeat 超过阈值
            if w.get("status") == "IN_PROGRESS":
                hb = w.get("heartbeat_at", "")
                if hb:
                    hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                    if (now_dt - hb_dt).total_seconds() > WORKER_TIMEOUT_SEC:
                        w["status"] = "TIMEOUT"
                        # 写回文件持久化超时状态
                        with FileLock(str(f) + ".lock", timeout=2):
                            f.write_text(json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
            workers.append(w)
        except (json.JSONDecodeError, OSError):
            pass
    done_count = sum(1 for w in workers if w["status"] == "DONE")
    failed_count = sum(1 for w in workers if w["status"] in ("FAILED", "TIMEOUT"))
    all_done = (done_count + failed_count) == len(workers) if workers else False
    print(json.dumps({
        "workers": workers,
        "total": len(workers),
        "done": done_count,
        "failed": failed_count,
        "timed_out": sum(1 for w in workers if w["status"] == "TIMEOUT"),
        "all_done": all_done,
    }, ensure_ascii=False))

def cmd_worker_cleanup(args):
    """清理 Worker 状态文件"""
    import shutil
    if WORKERS_DIR.exists():
        shutil.rmtree(WORKERS_DIR, ignore_errors=True)
    print('{"cleaned": true}')

# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Dev Harness")
    sub = parser.add_subparsers(dest="cmd")

    # init
    p_init = sub.add_parser("init")
    p_init.add_argument("task_name")
    p_init.add_argument("--route", default="C")
    p_init.add_argument("--mode", default="pipeline", choices=["pipeline", "single", "conversation"])
    p_init.add_argument("--skills", default="", help="single 模式下要执行的阶段（逗号分隔）")
    p_init.add_argument("--module", default="")
    p_init.add_argument("--branch", default="")
    p_init.add_argument("--session-id", dest="session_id", default="")

    # check-continue (legacy, used by old stop-hook)
    sub.add_parser("check-continue")

    # update
    p_upd = sub.add_parser("update")
    p_upd.add_argument("stage")
    p_upd.add_argument("status")
    p_upd.add_argument("--phase", type=int, default=None)
    p_upd.add_argument("--gate", action="append", default=[])
    p_upd.add_argument("--error", action="store_true")
    p_upd.add_argument("--auto-fixed", action="store_true")

    # hud (basic)
    p_hud = sub.add_parser("hud")
    p_hud.add_argument("--watch", action="store_true")
    p_hud.add_argument("--rich", action="store_true", help="使用 Rich 库增强版")
    p_hud.add_argument("--project", default=None, help="指定项目目录")

    # eval
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--report", action="store_true")

    # autoloop-status
    sub.add_parser("autoloop-status")

    # autoloop-log
    p_alog = sub.add_parser("autoloop-log")
    p_alog.add_argument("--lines", type=int, default=20)

    # web-hud
    p_web = sub.add_parser("web-hud")
    p_web.add_argument("--port", type=int, default=WEB_HUD_PORT)
    p_web.add_argument("--project", default=None, help="指定项目目录（默认从 cwd 向上查找 .git）")
    p_web.add_argument("--bind", default="127.0.0.1", help="绑定地址（默认 127.0.0.1，需外部访问时用 0.0.0.0）")

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

    # detect-mode (C6: 自动检测 implement 模式)
    sub.add_parser("detect-mode")

    # analyze-deps (C5: Orchestrator 依赖分析)
    sub.add_parser("analyze-deps")

    # log (write autoloop log entry)
    p_log = sub.add_parser("log")
    p_log.add_argument("stage")
    p_log.add_argument("--phase", default="")
    p_log.add_argument("--action", default="execute")
    p_log.add_argument("--result", default="PASS")
    p_log.add_argument("--detail", default="")

    args = parser.parse_args()
    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "check-continue":
        cmd_check_continue(args)
    elif args.cmd == "update":
        cmd_update(args)
    elif args.cmd == "hud":
        if getattr(args, 'rich', False):
            cmd_rich_hud(args)
        else:
            cmd_hud(args)
    elif args.cmd == "eval":
        cmd_eval(args)
    elif args.cmd == "autoloop-status":
        cmd_autoloop_status(args)
    elif args.cmd == "autoloop-log":
        cmd_autoloop_log(args)
    elif args.cmd == "web-hud":
        cmd_web_hud(args)
    elif args.cmd == "worker-report":
        cmd_worker_report(args)
    elif args.cmd == "worker-status":
        cmd_worker_status(args)
    elif args.cmd == "worker-cleanup":
        cmd_worker_cleanup(args)
    elif args.cmd == "detect-mode":
        cmd_detect_mode(args)
    elif args.cmd == "analyze-deps":
        cmd_analyze_deps(args)
    elif args.cmd == "log":
        autoloop_log(args.stage, args.phase, args.action, args.result, args.detail)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
