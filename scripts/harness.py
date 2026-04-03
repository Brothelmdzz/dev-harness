"""
Dev Harness — 状态管理 + HUD 面板 + Hook 入口
用法:
  python harness.py init <task_name> [--route B] [--module portal]
  python harness.py check-continue
  python harness.py update <stage> <status> [--phase N] [--gate build=pass]
  python harness.py hud [--watch]
  python harness.py eval [--report]
"""
import json, os, sys, time, glob, argparse
from datetime import datetime, timezone
from pathlib import Path

# ==================== 路径 ====================

def find_project_root():
    """向上查找 .git 目录定位项目根"""
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

# ==================== 状态读写 ====================

def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
        return None

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# ==================== 初始化 ====================

DEFAULT_PIPELINE = [
    {"name": "research",  "status": "SKIP"},
    {"name": "prd",       "status": "SKIP"},
    {"name": "plan",      "status": "PENDING"},
    {"name": "implement", "status": "PENDING", "phases": []},
    {"name": "audit",     "status": "PENDING", "parallel_with": "docs"},
    {"name": "docs",      "status": "PENDING", "parallel_with": "audit"},
    {"name": "test",      "status": "PENDING"},
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

    state = {
        "version": "1.0",
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
    print(json.dumps({"action": "init", "task": args.task_name, "route": route}, ensure_ascii=False))

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

        # 更新 current_stage
        state["current_stage"] = next_stages[0]
        for ns in next_stages:
            for s in pipeline:
                if s["name"] == ns:
                    s["status"] = "PENDING"
        save_state(state)

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
    """找到下一个可执行的阶段（考虑并行组）"""
    found_current = False
    result = []
    for s in pipeline:
        if s["name"] == current_name:
            found_current = True
            continue
        if found_current and s["status"] in ("PENDING", "WAITING"):
            result.append(s["name"])
            # 检查是否有并行伙伴
            parallel = s.get("parallel_with")
            if parallel:
                for ps in pipeline:
                    if ps["name"] == parallel and ps["status"] in ("PENDING", "WAITING"):
                        if ps["name"] not in result:
                            result.append(ps["name"])
            break  # 只返回下一组
    return result

# ==================== 状态更新 ====================

def cmd_update(args):
    state = load_state()
    if not state:
        print("ERROR: 无 harness 状态", file=sys.stderr)
        sys.exit(1)

    stage_name = args.stage
    new_status = args.status.upper()

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
                            k, v = g.split("=")
                            if "gates" not in p:
                                p["gates"] = {}
                            p["gates"][k] = v == "pass"

            # 错误计数
            if args.error:
                state["metrics"]["total_errors"] += 1
                if args.auto_fixed:
                    state["metrics"]["auto_fixed"] += 1
                else:
                    state["metrics"]["blocking"] += 1

            break

    # 更新 current_stage
    if new_status == "DONE":
        next_stages = find_next_runnable(state["pipeline"], stage_name)
        if next_stages:
            state["current_stage"] = next_stages[0]

    save_state(state)
    log_eval_event(state, "update", f"{stage_name} -> {new_status}")
    print(json.dumps({"stage": stage_name, "status": new_status}, ensure_ascii=False))

# ==================== HUD 面板 ====================

def cmd_hud(args):
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

    # eval
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--report", action="store_true")

    # autoloop-status
    sub.add_parser("autoloop-status")

    # autoloop-log
    p_alog = sub.add_parser("autoloop-log")
    p_alog.add_argument("--lines", type=int, default=20)

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
    elif args.cmd == "log":
        autoloop_log(args.stage, args.phase, args.action, args.result, args.detail)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
