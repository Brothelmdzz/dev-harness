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
from filelock import FileLock

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
    """原子化 read-modify-write：在同一把锁内读取、修改、保存状态"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with _state_lock():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        result = updater_fn(state)
        state["updated_at"] = now_iso()
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

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
    active_stages = ROUTE_STAGES.get(route, ROUTE_STAGES["C"])

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
        if s["status"] not in ("PENDING", "WAITING"):
            continue
        group = s.get("parallel_group")
        if group:
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps["status"] in ("PENDING", "WAITING")]
        return [s["name"]]
    return []

# ==================== 状态更新 ====================

def cmd_update(args):
    """原子化状态更新：read-modify-write 在同一把锁内完成（修复 C1+C2）"""
    stage_name = args.stage
    new_status = args.status.upper()

    def updater(state):
        for s in state["pipeline"]:
            if s["name"] == stage_name:
                s["status"] = new_status
                if new_status == "DONE":
                    s["completed_at"] = now_iso()
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
                                    p["gates"][parts[0]] = parts[1] == "pass"

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
    print(json.dumps({"stage": stage_name, "status": new_status}, ensure_ascii=False))

# ==================== HUD 面板 ====================

def cmd_hud(args):
    global PROJECT_ROOT, STATE_FILE
    if getattr(args, 'project', None):
        PROJECT_ROOT = find_project_root(args.project)
        STATE_FILE = PROJECT_ROOT / ".claude" / "harness-state.json"
    elif not STATE_FILE.exists():
        proj = find_latest_session_project()
        if proj:
            PROJECT_ROOT = proj
            STATE_FILE = PROJECT_ROOT / ".claude" / "harness-state.json"

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
    pending = [s for s in pipeline if s["status"] in ("PENDING", "WAITING")]

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
                "WAITING": "white", "BLOCKED": "red bold",
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
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { --bg:#0d1117; --card:#161b22; --border:#30363d; --text:#c9d1d9; --dim:#8b949e;
          --green:#3fb950; --yellow:#d29922; --red:#f85149; --blue:#58a6ff; --purple:#bc8cff; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:var(--bg); color:var(--text); font-family:'JetBrains Mono',Consolas,monospace; font-size:14px; padding:20px; }
  h1 { color:var(--blue); font-size:18px; margin-bottom:4px; }
  .meta { color:var(--dim); font-size:12px; margin-bottom:16px; }
  .tabs { display:flex; gap:4px; margin-bottom:16px; flex-wrap:wrap; }
  .tab { padding:6px 16px; border-radius:6px 6px 0 0; cursor:pointer; font-size:12px;
         background:var(--card); border:1px solid var(--border); border-bottom:none; color:var(--dim); }
  .tab.active { background:var(--bg); color:var(--blue); border-color:var(--blue); border-bottom:1px solid var(--bg); }
  .tab .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
  .dot.running { background:var(--yellow); } .dot.done { background:var(--green); } .dot.idle { background:var(--dim); }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--border); border-radius:8px; padding:16px; }
  .card h2 { color:var(--blue); font-size:14px; margin-bottom:12px; border-bottom:1px solid var(--border); padding-bottom:8px; }
  .progress-bar { display:flex; height:6px; border-radius:3px; overflow:hidden; margin-bottom:16px; background:var(--border); }
  .progress-bar .seg { height:100%; }
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
  .workers h3 { font-size:12px; color:var(--purple); margin-bottom:8px; }
  .worker { display:flex; gap:8px; font-size:12px; padding:3px 0; }
  .metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  .metric { text-align:center; }
  .metric .val { font-size:24px; font-weight:bold; }
  .metric .label { font-size:11px; color:var(--dim); margin-top:4px; }
  .extra-metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:16px;
                   padding-top:12px; border-top:1px solid var(--border); font-size:12px; color:var(--dim); text-align:center; }
  .no-data { color:var(--dim); text-align:center; padding:40px; }
  .session-id { color:var(--purple); font-size:12px; }
</style>
</head>
<body>
<h1>Dev Harness HUD</h1>
<div class="meta">Auto-refresh 2s | <span id="updated"></span></div>
<div class="tabs" id="tabs"></div>
<div id="app"><div class="no-data">正在搜索活跃项目...</div></div>
<script>
let projects = [];
let activeProject = null;

async function loadProjects() {
  try {
    const r = await fetch('/api/projects');
    if (r.ok) projects = await r.json();
    if (projects.length && !activeProject) activeProject = projects[0].path;
    renderTabs();
  } catch(e) {}
}

function renderTabs() {
  if (!projects.length) { document.getElementById('tabs').innerHTML = ''; return; }
  document.getElementById('tabs').innerHTML = projects.map(p => {
    const isActive = p.path === activeProject;
    const stage = p.current_stage || '';
    const dotClass = stage ? (stage === 'remember' ? 'done' : 'running') : 'idle';
    return `<div class="tab ${isActive?'active':''}" onclick="switchProject('${p.path.replace(/\\/g,'\\\\')}')">
      <span class="dot ${dotClass}"></span>${p.name} <span style="color:var(--dim);font-size:10px">${stage}</span>
    </div>`;
  }).join('');
}

function switchProject(path) { activeProject = path; refresh(); renderTabs(); }

async function refresh() {
  if (!activeProject) { await loadProjects(); return; }
  try {
    const r = await fetch('/api/state?project=' + encodeURIComponent(activeProject));
    if (!r.ok) { document.getElementById('app').innerHTML = '<div class="no-data">等待 harness 会话启动...</div>'; return; }
    const s = await r.json();
    render(s);
  } catch(e) {}
}

function render(s) {
  const task = s.task || {};
  const metrics = s.metrics || {};
  const pipeline = s.pipeline || [];
  const current = s.current_stage || '';
  document.getElementById('updated').textContent = (s.updated_at||'').replace('T',' ').replace('Z','');

  // 进度条
  const active = pipeline.filter(x=>x.status!=='SKIP');
  let barHtml = active.map(st => {
    const cls = st.status==='DONE'?'done':st.status==='IN_PROGRESS'?'active':'pending';
    return `<div class="seg ${cls}" style="flex:1" title="${st.name}: ${st.status}"></div>`;
  }).join('');

  let stagesHtml = '';
  for (const st of pipeline) {
    const isCur = st.name === current;
    const icon = st.status==='DONE'?'✓':st.status==='IN_PROGRESS'?'▶':st.status==='SKIP'?'—':st.status==='FAILED'?'✗':'○';
    const dur = calcDur(st);
    const group = st.parallel_group ? `<span class="group-tag">⫘ ${st.parallel_group}</span>` : '';
    stagesHtml += `<div class="stage ${isCur?'current':''}">
      <span class="icon ${st.status}">${icon}</span>
      <span class="name">${st.name}${group}</span>
      <span class="status ${st.status}">${st.status}</span>
      <span class="dur">${dur}</span>
    </div>`;
    if (st.name==='implement' && st.phases && st.phases.length) {
      for (const p of st.phases) {
        const pi = p.status==='DONE'?'✓':p.status==='IN_PROGRESS'?'▶':'○';
        let gs = '';
        if (p.gates) for (const [k,v] of Object.entries(p.gates))
          gs += `<span class="gate ${v?'pass':'fail'}">${k}:${v?'✓':'✗'}</span>`;
        const err = p.error_count ? `<span class="err">⚠${p.error_count}</span>` : '';
        stagesHtml += `<div class="phase"><span class="${p.status}">${pi}</span> ${p.name||'Phase'} ${gs} ${err}</div>`;
      }
    }
  }

  const done = pipeline.filter(x=>x.status==='DONE').length;
  const total = pipeline.filter(x=>x.status!=='SKIP').length;
  const pct = total ? Math.round(done/total*100) : 0;

  document.getElementById('app').innerHTML = `
    <div class="progress-bar">${barHtml}</div>
    <div class="grid">
      <div class="card">
        <h2>任务: ${task.name||'?'} <span class="session-id">${s.session_id?'#'+s.session_id:''}</span></h2>
        <div style="color:var(--dim);font-size:12px;margin-bottom:12px">
          Route: ${task.route||'?'} | Branch: ${task.branch||'-'} | Module: ${task.module||'-'}
        </div>
        ${stagesHtml}
      </div>
      <div class="card">
        <h2>指标</h2>
        <div class="metrics">
          <div class="metric"><div class="val" style="color:var(--blue)">${pct}%</div><div class="label">进度 (${done}/${total})</div></div>
          <div class="metric"><div class="val" style="color:var(--yellow)">${metrics.auto_continues||0}</div><div class="label">自动续跑</div></div>
          <div class="metric"><div class="val" style="color:${(metrics.total_errors||0)>0?'var(--red)':'var(--green)'}">${metrics.total_errors||0}</div><div class="label">错误</div></div>
        </div>
        <div class="extra-metrics">
          <div>自动修复: ${metrics.auto_fixed||0}</div>
          <div>阻断: ${metrics.blocking||0}</div>
          <div>重试上限: ${metrics.max_retries||3}</div>
          <div>已完成: ${metrics.stages_completed||0}</div>
        </div>
      </div>
    </div>`;
}
function calcDur(st) {
  if (!st.started_at) return '';
  const end = st.completed_at ? new Date(st.completed_at) : new Date();
  const d = (end - new Date(st.started_at)) / 1000;
  if (d < 0) return '';
  return d > 3600 ? Math.floor(d/3600)+'h'+('0'+Math.floor(d%3600/60)).slice(-2)+'m'
       : d > 60 ? Math.floor(d/60)+'m'+('0'+Math.floor(d%60)).slice(-2)+'s'
       : Math.floor(d)+'s';
}
loadProjects();
setInterval(refresh, 2000);
setInterval(loadProjects, 10000);
</script>
</body>
</html>"""

def cmd_web_hud(args):
    """启动多项目 Web HUD 面板"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

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
    print("多项目模式 | Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        print("\nWeb HUD 已停止")

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

    load_and_update_state(updater)
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
    phase_pattern = r'^#{2,3}\s+(?:Phase|Task|阶段)\s*(\d+)\s*[：:.\-—]?\s*(.*?)$'
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
                    from datetime import timezone as tz
                    hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                    if (now_dt - hb_dt).total_seconds() > WORKER_TIMEOUT_SEC:
                        w["status"] = "TIMEOUT"
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
    p_upd.add_argument("--gate", nargs="*")
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
