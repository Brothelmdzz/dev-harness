"""
Dev Harness — 状态管理 + HUD 面板 + Hook 入口
用法:
  python harness.py init <task_name> [--route B] [--module portal]
  python harness.py check-continue
  python harness.py update <stage> <status> [--phase N] [--gate build=pass]
  python harness.py hud [--watch]
  python harness.py eval [--report]
"""
import json, os, sys, time, argparse, uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.compat import FileLock, require_filelock
from lib.project import find_project_root
from lib.utils import now_iso, parse_iso as _parse_iso
from lib.config import parse_simple_yaml as _parse_simple_yaml
from lib.pipeline import (
    find_next_runnable,
    validate_dag as validate_pipeline_dag,
    pipeline_is_terminal as _pipeline_is_terminal,
)
from lib.plan import parse_phases, parse_phases_from_plan_dir
from lib.pitfall import capture_failure as _pitfall_capture_failure

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
    # 限制文件权限，防止多用户共享机器时信息泄露
    if os.name != "nt":
        try:
            os.chmod(SESSION_INDEX, 0o600)
        except OSError:
            pass

SESSION_GRACE_SEC = 600  # pipeline 完成后保留 10 分钟，再从索引移除

def register_session(session_id, project_path):
    """注册/更新 session → 项目路径映射（upsert 语义，同步清零 finished_at）"""
    index = load_session_index()
    if session_id in index:
        # 同 session 重新注册（比如 update 时自愈旧 state），保留 started_at
        index[session_id]["project"] = str(project_path)
        index[session_id]["finished_at"] = None
    else:
        index[session_id] = {
            "project": str(project_path),
            "started_at": now_iso(),
            "finished_at": None,
        }
    if len(index) > 50:
        sorted_keys = sorted(index, key=lambda k: index[k].get("started_at", ""), reverse=True)
        index = {k: index[k] for k in sorted_keys[:50]}
    save_session_index(index)

def finalize_session(session_id):
    """标记 session 为已完成（pipeline 终态触发），后续 prune 会按 grace period 清理"""
    if not session_id:
        return
    index = load_session_index()
    if session_id in index and not index[session_id].get("finished_at"):
        index[session_id]["finished_at"] = now_iso()
        save_session_index(index)

def prune_sessions(grace_sec=SESSION_GRACE_SEC):
    """清理索引：(1) state 文件丢失立即删 (2) finished_at 超过 grace 删
    (3) state 存在且已终态但缺 finished_at → 自愈补录
    返回清理后的 index"""
    index = load_session_index()
    changed = False
    now_dt = datetime.now(timezone.utc)
    for sid in list(index.keys()):
        entry = index[sid]
        proj = Path(entry.get("project", ""))
        sf = proj / ".claude" / "harness-state.json"
        if not sf.exists():
            del index[sid]
            changed = True
            continue
        finished_at = entry.get("finished_at")
        if finished_at:
            ft = _parse_iso(finished_at)
            if ft and (now_dt - ft).total_seconds() > grace_sec:
                del index[sid]
                changed = True
                continue
        else:
            # 自愈：state 已终态但索引没标记 finished_at（常见于异常崩溃/旧版本状态）
            try:
                st = json.loads(sf.read_text(encoding="utf-8"))
                if _pipeline_is_terminal(st.get("pipeline", [])):
                    entry["finished_at"] = now_iso()
                    changed = True
            except (OSError, json.JSONDecodeError):
                pass
    if changed:
        save_session_index(index)
    return index

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
    """原子化写入 state（先写 .tmp 再 os.replace，防损坏）"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now_iso()
    tmp_file = STATE_FILE.with_suffix(".json.tmp")
    with _state_lock():
        tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp_file), str(STATE_FILE))

def load_and_update_state(updater_fn):
    """原子化 read-modify-write：在同一把锁内读取、修改、保存状态
    返回更新后的 state dict（文件不存在时返回 None）"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = STATE_FILE.with_suffix(".json.tmp")
    with _state_lock():
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        updater_fn(state)
        state["updated_at"] = now_iso()
        tmp_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp_file), str(STATE_FILE))
        return state

# ==================== 配置加载 ====================

DEFAULT_LIMITS = {
    "stage_timeout": 1800,          # 单阶段超时（秒）
    "max_duration": 7200,           # 总运行时长（秒）
    "window_minutes": 5,            # 滑动窗口（分钟）
    "max_events": 10,               # 窗口内最大续跑次数
    "context_overflow_pct": 80,     # 上下文溢出阈值（%）
    "rate_limit_pause_min": 15,     # Rate limit 暂停（分钟）
    "max_retries": 3,               # 最大重试次数
    "max_auto_phases": 10,          # 最大自动 Phase 数
}

LIMITS_BOUNDS = {
    "stage_timeout":        (300, 7200),
    "max_duration":         (600, 28800),
    "window_minutes":       (2, 30),
    "max_events":           (3, 50),
    "context_overflow_pct": (50, 95),
    "rate_limit_pause_min": (5, 60),
    "max_retries":          (1, 10),
    "max_auto_phases":      (1, 50),
}

def _load_dev_config():
    """读取 .claude/dev-config.yml"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return _parse_simple_yaml(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_and_validate_limits(config):
    """从 dev-config 加载 limits，校验范围，fallback 默认值。

    v3.4.4 MEDIUM-D fix：clamp / parse 失败时 stderr WARN，
    避免用户写错配置（如 stage_timeout: 30sec）后沉默 fallback 不自知。
    """
    raw = config.get("limits", {})
    if isinstance(raw, str):
        raw = {}
    result = dict(DEFAULT_LIMITS)
    for key, default in DEFAULT_LIMITS.items():
        val = raw.get(key)
        if val is None:
            continue
        try:
            val = type(default)(val)
        except (ValueError, TypeError):
            print(f"WARN: dev-config.yml limits.{key}={raw[key]!r} 无法转换为 {type(default).__name__}，"
                  f"fallback 默认值 {default}", file=sys.stderr)
            result[key] = default
            continue
        lo, hi = LIMITS_BOUNDS.get(key, (None, None))
        orig = val
        if lo is not None and val < lo:
            val = lo
        if hi is not None and val > hi:
            val = hi
        if val != orig:
            print(f"WARN: dev-config.yml limits.{key}={orig} 超出范围 [{lo},{hi}]，clamp 到 {val}",
                  file=sys.stderr)
        result[key] = val
    return result

# ==================== 初始化 ====================

DEFAULT_PIPELINE = [
    {"name": "research",  "status": "SKIP",    "depends_on": []},
    {"name": "prd",       "status": "SKIP",    "depends_on": ["research"]},
    {"name": "plan",      "status": "PENDING", "depends_on": ["prd"]},
    {"name": "implement", "status": "PENDING", "depends_on": ["plan"], "phases": []},
    {"name": "audit",     "status": "PENDING", "depends_on": ["implement"], "parallel_group": "post-implement"},
    {"name": "docs",      "status": "PENDING", "depends_on": ["implement"], "parallel_group": "post-implement"},
    {"name": "test",      "status": "PENDING", "depends_on": ["implement"], "parallel_group": "post-implement"},
    {"name": "review",    "status": "PENDING", "depends_on": ["audit", "docs", "test"]},
    {"name": "remember",  "status": "PENDING", "depends_on": ["review"]},
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

    # 加载项目配置，提取 limits 参数（支持 dev-config.yml 覆盖默认值）
    config = _load_dev_config()
    limits = _load_and_validate_limits(config)

    state = {
        "version": "1.2",
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
        "limits": limits,
        "metrics": {
            "total_errors": 0,
            "auto_fixed": 0,
            "blocking": 0,
            "max_retries": limits["max_retries"],
            "max_duration": limits["max_duration"],
            "stage_timeout": limits["stage_timeout"],
            "stages_completed": 0,
            "auto_continues": 0,
        },
        # 细粒度活动流：由 hooks/activity-watcher.py 追加，环形缓冲最多 30 条
        "activity": [],
    }
    # DAG 合法性校验（仅当 pipeline 含 depends_on 时）
    try:
        validate_pipeline_dag(pipeline)
    except ValueError as e:
        print(json.dumps({"error": f"Pipeline DAG invalid: {e}"}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

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

VALID_STATUSES = {"PENDING", "IN_PROGRESS", "DONE", "SKIP", "FAILED", "BLOCKED", "RETRY"}

def cmd_update(args):
    """原子化状态更新：read-modify-write 在同一把锁内完成（修复 C1+C2）"""
    stage_name = args.stage
    new_status = args.status.upper()

    if new_status not in VALID_STATUSES:
        print(json.dumps({"error": f"Invalid status '{new_status}'. Valid: {sorted(VALID_STATUSES)}"},
                         ensure_ascii=False))
        sys.exit(1)

    # RETRY 语义: 重置 FAILED→PENDING（P2-2: 死状态恢复）
    # v3.4.4 HIGH-B fix：同时重置当前 stage 下所有 phase 的 error_count + gates。
    # 原先只改 stage status，但 phase.error_count 还保留 >= max_retries，下次 stop-hook
    # 续跑时立即被防线 6 拦下 → 用户主动 RETRY 没生效。
    _retry_reset = (new_status == "RETRY")
    if new_status == "RETRY":
        new_status = "PENDING"

    def updater(state):
        for s in state["pipeline"]:
            if s["name"] == stage_name:
                prev_status = s["status"]
                s["status"] = new_status
                # HIGH-B 续：RETRY 时清空当前 stage 的 phase 错误计数和门禁结果
                if _retry_reset and "phases" in s:
                    for ph in s["phases"]:
                        ph["error_count"] = 0
                        if "gates" in ph:
                            ph["gates"] = {}
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
                            # v4.0 Gate Feedback Loop：失败的 gate 自动入 pitfall journal，
                            # 续跑前 build_pitfall_context() 会把它当 ground truth 注入下一轮 prompt
                            detail_map = {}
                            for d in (args.gate_detail or []):
                                k, _, v = d.partition("=")
                                if k and v:
                                    detail_map[k] = v
                            for g in args.gate:
                                parts = g.split("=", 1)
                                if len(parts) != 2:
                                    continue
                                gate_name, gate_result = parts[0], parts[1].lower()
                                if "gates" not in p:
                                    p["gates"] = {}
                                p["gates"][gate_name] = (gate_result == "pass")
                                if gate_result != "pass":
                                    # v3.4.4 HIGH-1 fix：gate fail 显然属于 phase 出错，递增 error_count
                                    # 让防线 6（stop-hook _handle_implement_continue 检查
                                    # error_count >= max_retries）对 build/test 反复失败也能正常兜底。
                                    # 不依赖用户额外传 --error。
                                    p["error_count"] = p.get("error_count", 0) + 1
                                    detail = detail_map.get(gate_name, "")
                                    try:
                                        _pitfall_capture_failure(
                                            PROJECT_ROOT,
                                            category=gate_name if gate_name in ("build", "test", "lint", "runtime", "deploy") else "other",
                                            phase=stage_name,
                                            summary=(detail.split("\n", 1)[0][:160] if detail else f"{gate_name} 门禁失败（{stage_name} phase {args.phase}）"),
                                            root_cause=detail,
                                            resolution="",
                                            extra={"phase_name": p.get("name", ""), "gate": gate_name},
                                        )
                                    except Exception as _pitfall_err:
                                        # v3.4.4 MEDIUM-1 fix：不能让 pitfall 写入失败导致 CLI 退出，
                                        # 但要可见——写 stderr 而不是 `pass` 完全吞错，
                                        # 让运维能从 hook log / CI log 看到磁盘满 / 权限错 / 锁超时等。
                                        print(f"WARN: pitfall capture failed for gate '{gate_name}': {_pitfall_err}",
                                              file=sys.stderr)

                # 错误计数
                if args.error:
                    state["metrics"]["total_errors"] += 1
                    if args.auto_fixed:
                        state["metrics"]["auto_fixed"] += 1
                    else:
                        state["metrics"]["blocking"] += 1
                    # P2-4: 递增 phase 级 error_count（防线 6 依赖此字段）
                    if args.phase is not None and "phases" in s:
                        idx = args.phase - 1
                        if 0 <= idx < len(s["phases"]):
                            s["phases"][idx]["error_count"] = s["phases"][idx].get("error_count", 0) + 1
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

    state = load_and_update_state(updater)
    if state is None:
        print("ERROR: 无 harness 状态", file=sys.stderr)
        sys.exit(1)
    # P2-10: 直接使用 load_and_update_state 返回值，不再锁外重读
    log_eval_event(state, "update", f"{stage_name} -> {new_status}")
    sid = state.get("session_id")
    if sid and not os.environ.get("DH_EVAL"):
        index = load_session_index()
        if sid not in index or index[sid].get("project") != str(PROJECT_ROOT):
            register_session(sid, PROJECT_ROOT)
    _try_notify_pipeline(state, new_status)
    if new_status in ("DONE", "FAILED") and _pipeline_is_terminal(state.get("pipeline", [])):
        if sid:
            finalize_session(sid)
    print(json.dumps({"stage": stage_name, "status": new_status}, ensure_ascii=False))
    # update 输出自带 hud 快照：让状态落盘的同时把完成裁判证据落进 transcript，
    # 模型无需再单独跑 hud（原 PostToolUse hud-context 兜底通道已随之删除）
    print(_hud_snapshot(state))

# ==================== HUD 面板 ====================

def cmd_hud(args):
    if getattr(args, 'project', None):
        set_project_root(args.project)
    elif not STATE_FILE.exists():
        # 从中央索引挑最新的活跃 session
        index = prune_sessions()
        active = [(sid, e) for sid, e in index.items() if not e.get("finished_at")]
        if active:
            active.sort(key=lambda x: x[1].get("started_at", ""), reverse=True)
            set_project_root(active[0][1]["project"])

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

def _hud_snapshot(state):
    """紧凑 hud 快照（纯 ASCII）：一行一个 stage，供 `update` 输出自带完成裁判证据。
    与 hud 命令共用状态源，格式对齐 prompt 完成裁判可读的最简文本，避免模型再单独跑 hud。
    implement 阶段附带 phase 进度与失败 gate；末尾给 current_stage / error_count / paused。"""
    lines = ["[dev-harness hud]"]
    for s in state.get("pipeline", []):
        name = s.get("name", "?")
        status = s.get("status", "PENDING")
        parts = [f"{name} -> {status}"]
        gate_bits = [f"{k}={'pass' if v else 'FAIL'}" for k, v in (s.get("gates") or {}).items()]
        phases = s.get("phases") or []
        if phases:
            done = sum(1 for p in phases if p.get("status") == "DONE")
            parts.append(f"({done}/{len(phases)} phases)")
            # implement 的 gate 挂在 phase 上，只强调失败项——失败 gate 是裁判最需要的 ground truth
            for p in phases:
                for k, v in (p.get("gates") or {}).items():
                    if not v:
                        gate_bits.append(f"{p.get('name', '?')}:{k}=FAIL")
        if gate_bits:
            parts.append("[" + " ".join(gate_bits) + "]")
        lines.append(" ".join(parts))
    lines.append(f"error_count={state.get('metrics', {}).get('total_errors', 0)}")
    cur = state.get("current_stage", "")
    if cur:
        lines.append(f"current_stage={cur}")
    if state.get("paused"):
        lines.append(f"paused: {state.get('pause_reason', '')}")
    return "\n".join(lines)

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
    if state.get("paused"):
        paused_line = f"PAUSED: {state.get('pause_reason', '')}"
        print(f"| {pad_to_width(paused_line, W)} |")
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
            except (ValueError, TypeError, OSError):
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
        except (ValueError, TypeError, OSError):
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
                    except (ValueError, TypeError, OSError):
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
                except (OSError, UnicodeDecodeError):
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


def cmd_web_hud(args):
    """启动多项目 Web HUD 面板 — 委托给 web_hud 模块"""
    from web_hud import start_web_hud
    start_web_hud(
        port=args.port or WEB_HUD_PORT,
        bind=getattr(args, 'bind', None) or '127.0.0.1',
        prune_sessions_fn=prune_sessions,
        load_state_fn=load_state,
        state_file=STATE_FILE,
    )

# ==================== Implement 模式检测 (C6 代码化) ====================

ORCHESTRATOR_THRESHOLD = 3  # Phase > 此值触发 Orchestrator 模式

def cmd_detect_mode(args):
    """检测 implement 模式（C6: 代码化强制，不依赖 SKILL.md 建议）"""
    phases = parse_phases_from_plan_dir(PROJECT_ROOT)
    mode = "orchestrator" if len(phases) > ORCHESTRATOR_THRESHOLD else "serial"

    if mode == "orchestrator":
        require_filelock("Orchestrator 多 Worker 并行")

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
            # v3.4.4 HIGH-C fix：read + check + write 全在同一把锁内，
            # 否则两段锁之间 worker 自己可能写入 status=DONE，被这里覆盖回 TIMEOUT 丢失结果。
            lock = FileLock(str(f) + ".lock", timeout=2)
            with lock:
                w = json.loads(f.read_text(encoding="utf-8"))
                if w.get("status") == "IN_PROGRESS":
                    hb = w.get("heartbeat_at", "")
                    if hb:
                        hb_dt = datetime.fromisoformat(hb.replace("Z", "+00:00"))
                        if (now_dt - hb_dt).total_seconds() > WORKER_TIMEOUT_SEC:
                            w["status"] = "TIMEOUT"
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

# ==================== Sessions 管理（中央索引 CLI） ====================

def cmd_sessions(args):
    """操作中央 session 索引: list / prune / finalize / register"""
    action = getattr(args, "session_action", None)
    if action == "list":
        index = prune_sessions()
        rows = []
        for sid, entry in sorted(index.items(), key=lambda kv: kv[1].get("started_at", ""), reverse=True):
            proj = Path(entry.get("project", ""))
            sf = proj / ".claude" / "harness-state.json"
            row = {
                "session_id": sid,
                "project": str(proj),
                "started_at": entry.get("started_at"),
                "finished_at": entry.get("finished_at"),
                "state_exists": sf.exists(),
            }
            if sf.exists():
                try:
                    st = json.loads(sf.read_text(encoding="utf-8"))
                    row["current_stage"] = st.get("current_stage", "")
                    row["task"] = st.get("task", {}).get("name", "")
                except Exception:
                    pass
            rows.append(row)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    elif action == "prune":
        grace = getattr(args, "grace", SESSION_GRACE_SEC)
        before = load_session_index()
        after = prune_sessions(grace_sec=grace)
        removed = sorted(set(before) - set(after))
        print(json.dumps({"removed": removed, "remaining": len(after)}, ensure_ascii=False, indent=2))
    elif action == "finalize":
        sid = getattr(args, "session_id", None)
        if not sid:
            print("ERROR: 需要 --session-id", file=sys.stderr)
            sys.exit(1)
        finalize_session(sid)
        print(json.dumps({"finalized": sid}, ensure_ascii=False))
    elif action == "register":
        sid = getattr(args, "session_id", None)
        proj = getattr(args, "project", None)
        if not sid or not proj:
            print("ERROR: 需要 --session-id 和 --project", file=sys.stderr)
            sys.exit(1)
        register_session(sid, Path(proj).resolve())
        print(json.dumps({"registered": sid, "project": str(Path(proj).resolve())}, ensure_ascii=False))
    else:
        print("用法: harness.py sessions {list|prune|finalize|register}", file=sys.stderr)
        sys.exit(1)

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
    p_init.set_defaults(func=cmd_init)

    # check-continue
    sub.add_parser("check-continue").set_defaults(func=cmd_check_continue)

    # update
    p_upd = sub.add_parser("update")
    p_upd.add_argument("stage")
    p_upd.add_argument("status")
    p_upd.add_argument("--phase", type=int, default=None)
    p_upd.add_argument("--gate", action="append", default=[],
                       help="门禁结果，格式 name=pass|fail，可重复")
    p_upd.add_argument("--gate-detail", action="append", default=[],
                       help="门禁失败详情，格式 name=具体错误信息，可重复；fail 时自动入 pitfall journal")
    p_upd.add_argument("--error", action="store_true")
    p_upd.add_argument("--auto-fixed", action="store_true")
    p_upd.set_defaults(func=cmd_update)

    # hud
    p_hud = sub.add_parser("hud")
    p_hud.add_argument("--watch", action="store_true")
    p_hud.add_argument("--rich", action="store_true", help="使用 Rich 库增强版")
    p_hud.add_argument("--project", default=None, help="指定项目目录")
    p_hud.set_defaults(func=lambda a: cmd_rich_hud(a) if getattr(a, 'rich', False) else cmd_hud(a))

    # eval
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("--report", action="store_true")
    p_eval.set_defaults(func=cmd_eval)

    # autoloop-status
    sub.add_parser("autoloop-status").set_defaults(func=cmd_autoloop_status)

    # autoloop-log
    p_alog = sub.add_parser("autoloop-log")
    p_alog.add_argument("--lines", type=int, default=20)
    p_alog.set_defaults(func=cmd_autoloop_log)

    # web-hud
    p_web = sub.add_parser("web-hud")
    p_web.add_argument("--port", type=int, default=WEB_HUD_PORT)
    p_web.add_argument("--project", default=None)
    p_web.add_argument("--bind", default="127.0.0.1")
    p_web.set_defaults(func=cmd_web_hud)

    # worker-report
    p_wr = sub.add_parser("worker-report")
    p_wr.add_argument("worker_id")
    p_wr.add_argument("--phase", required=True)
    p_wr.add_argument("--status", required=True)
    p_wr.add_argument("--branch", default="")
    p_wr.set_defaults(func=cmd_worker_report)

    # worker-status
    sub.add_parser("worker-status").set_defaults(func=cmd_worker_status)

    # worker-cleanup
    sub.add_parser("worker-cleanup").set_defaults(func=cmd_worker_cleanup)

    # detect-mode
    sub.add_parser("detect-mode").set_defaults(func=cmd_detect_mode)

    # analyze-deps
    sub.add_parser("analyze-deps").set_defaults(func=cmd_analyze_deps)

    # sessions
    p_sess = sub.add_parser("sessions")
    p_sess.add_argument("session_action", choices=["list", "prune", "finalize", "register"])
    p_sess.add_argument("--session-id", dest="session_id", default=None)
    p_sess.add_argument("--project", default=None)
    p_sess.add_argument("--grace", type=int, default=SESSION_GRACE_SEC)
    p_sess.set_defaults(func=cmd_sessions)

    # log
    p_log = sub.add_parser("log")
    p_log.add_argument("stage")
    p_log.add_argument("--phase", default="")
    p_log.add_argument("--action", default="execute")
    p_log.add_argument("--result", default="PASS")
    p_log.add_argument("--detail", default="")
    p_log.set_defaults(func=lambda a: autoloop_log(a.stage, a.phase, a.action, a.result, a.detail))

    args = parser.parse_args()
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
