#!/usr/bin/env python3
"""
Dev Harness Stop Hook — 阻止 Claude 在 Pipeline 未完成时停下

机制（Claude Code 官方）:
  - Stop hook 通过 stdin 接收 JSON: {session_id, stop_hook_active, last_assistant_message}
  - 输出 {"decision": "block", "reason": "..."} → Claude 自动续跑
  - 输出空/exit 0 → Claude 正常停止
  - stop_hook_active=true → 已经续跑过一轮，需检查是否应该停止（防无限循环）

v3.0 改进:
  - 防线 1: Rate Limit 自动检测 → 暂停并记录恢复时间
  - 防线 2: 上下文使用率 > 80% → 转入 remember 阶段
  - 防线 3: 单阶段超时 (默认 30min)
  - 防线 4: 总运行时长上限 (默认 2h)
  - 防线 5: 滑动窗口频率限制 (5min 内 > 10 次 → 死循环)
  - 防线 6: error_count >= max_retries → 死循环
"""
import json, sys, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    from filelock import FileLock
except ImportError:
    class FileLock:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass

# ==================== 常量 ====================

STAGE_TIMEOUT_SEC = 1800       # 单阶段超时: 30 分钟
DEFAULT_MAX_DURATION = 7200    # 总时长上限: 2 小时
SLIDING_WINDOW_MIN = 5         # 滑动窗口: 5 分钟
SLIDING_WINDOW_MAX_EVENTS = 10 # 窗口内最大续跑次数
CONTEXT_OVERFLOW_PCT = 80      # 上下文使用率阈值
RATE_LIMIT_KEYWORDS = ["rate limit", "hit your limit", "resets", "rate_limit", "too many requests"]
RATE_LIMIT_PAUSE_MIN = 15      # rate limit 暂停时长

# ==================== 工具函数 ====================

def find_project_root():
    """
    查找项目根目录（C4: 与 harness.py 逻辑统一）。
    优先级: cwd 向上找 .git → cwd 有 harness-state → 扫描常见目录
    """
    # 方式 1: 从 cwd 向上查找 .git（与 harness.py 一致）
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent

    # 方式 2: cwd 下有 harness-state.json（非 git 项目）
    if (Path.cwd() / ".claude" / "harness-state.json").exists():
        return Path.cwd()

    # 方式 3: 扫描常见目录（限制扫描量，最多 100 个目录）
    scan_roots = [Path.home() / "work", Path.home() / "projects", Path.home() / "dev"]
    if os.name == "nt":
        scan_roots.extend(Path(f"{d}:/work") for d in ["C", "D"])
    best, best_mtime = None, 0
    for root in scan_roots:
        try:
            if not root.is_dir():
                continue
            for d in list(root.iterdir())[:100]:
                if not d.is_dir():
                    continue
                sf = d / ".claude" / "harness-state.json"
                if sf.exists():
                    mtime = sf.stat().st_mtime
                    if mtime > best_mtime:
                        best_mtime = mtime
                        best = d
        except (PermissionError, OSError):
            pass
    return best or Path.cwd()

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def now_utc():
    return datetime.now(timezone.utc)

def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

def elapsed_seconds(iso_str):
    t = parse_iso(iso_str)
    if not t:
        return 0
    return (now_utc() - t).total_seconds()

def log_eval(project_root, state, event, detail):
    log_file = project_root / ".claude" / "harness-eval.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": now_iso(),
        "project": state.get("project", ""),
        "task": state.get("task", {}).get("name", ""),
        "event": event,
        "detail": detail,
        "stage": state.get("current_stage", ""),
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def parse_phases_from_plan(project_root):
    """从最新 plan 文件解析 Phase 列表（fallback：phases 为空时自动补救）"""
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

def count_recent_events(eval_log_path, minutes=5):
    if not eval_log_path.exists():
        return 0
    cutoff = now_utc() - timedelta(minutes=minutes)
    count = 0
    try:
        for line in eval_log_path.read_text(encoding="utf-8").strip().split("\n"):
            if not line:
                continue
            entry = json.loads(line)
            if entry.get("event") != "auto_continue":
                continue
            t = parse_iso(entry.get("timestamp", ""))
            if t and t > cutoff:
                count += 1
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return count

# ==================== 旧格式迁移 ====================

def migrate_legacy_state(old):
    """
    将旧格式 {"stages": {"implement": {...}, ...}} 转换为
    新格式 {"pipeline": [{"name": "implement", ...}], "metrics": {...}}

    旧格式来源: Claude 手写 harness-state.json（未通过 harness.py init）
    """
    stages_dict = old.get("stages", {})
    pipeline = []
    stage_order = ["research", "prd", "plan", "implement", "audit", "docs", "test", "review", "remember"]

    for name in stage_order:
        if name in stages_dict:
            s = dict(stages_dict[name])
            s["name"] = name
            # 旧格式 phases 可能在 stages.implement.phases 里
            pipeline.append(s)

    # 保留旧字段中有用的信息
    task_name = old.get("task", "")
    if isinstance(task_name, str):
        task_obj = {"name": task_name, "route": old.get("route", "C"),
                    "branch": "", "module": "", "started_at": old.get("created", "")}
    else:
        task_obj = task_name  # 已经是对象

    return {
        "version": "1.0",
        "project": old.get("project", ""),
        "task": task_obj,
        "pipeline": pipeline,
        "current_stage": old.get("current_stage", ""),
        "paused": old.get("paused", False),
        "metrics": {
            "total_errors": 0, "auto_fixed": 0, "blocking": 0,
            "max_retries": 3, "stages_completed": 0, "auto_continues": 0,
            "max_duration": 7200,
        },
        "_migrated_from": "legacy",
    }

# ==================== 主逻辑 ====================

def _handle_implement_continue(state, stage, project_root, state_file, max_retries, source=""):
    """implement 阶段续跑统一逻辑（M8 去重）
    返回 (action, reason):
      - ("continue", reason) → 输出 block 继续执行
      - ("exit", "")         → 退出，不续跑
      - ("mark_done", "")    → phases 全部完成，标记 DONE 后推进
    """
    phases = stage.get("phases", [])
    # fallback: phases 为空时从 plan 文件解析
    if not phases:
        phases = parse_phases_from_plan(project_root)
        if phases:
            stage["phases"] = phases
            save_state(state, state_file)
            log_eval(project_root, state, "phases_fallback",
                     f"从 plan 文件解析到 {len(phases)} 个 Phase ({source})")
    # 检查死循环
    for p in phases:
        if p.get("error_count", 0) >= max_retries:
            return ("exit", "")
    # 查找待执行 Phase
    pending = [p for p in phases if p.get("status") == "PENDING"]
    if pending:
        reason = f"继续实现下一个 Phase: {pending[0].get('name', '?')}。读取 plan 文件确认内容后执行。完成后更新 harness-state.json。"
        return ("continue", reason)
    if not phases:
        return ("exit", "")
    # phases 非空且全部完成 → 标记 DONE
    stage["status"] = "DONE"
    stage["completed_at"] = now_iso()
    state["metrics"]["stages_completed"] = state["metrics"].get("stages_completed", 0) + 1
    return ("mark_done", "")

def output_continue():
    """允许停止（不阻拦），学习 OMC 的 {continue: true} 模式"""
    print(json.dumps({"continue": True, "suppressOutput": True}))

def is_context_limit_stop(hook_input):
    """
    检测是否因上下文满而停止。
    阻止 context-limit 停止会导致死锁：无法 compact 因为无法停止，无法继续因为上下文满。
    学习自 OMC issue #213。
    """
    for key in ["stop_reason", "stopReason", "end_turn_reason", "endTurnReason", "reason"]:
        reason = str(hook_input.get(key, "")).lower()
        if any(p in reason for p in ["context", "token limit", "max_tokens", "context_length", "too long"]):
            return True
    return False

def is_user_abort(hook_input):
    """检测用户主动中断（Ctrl+C / cancel）"""
    if hook_input.get("user_requested") or hook_input.get("userRequested"):
        return True
    reason = str(hook_input.get("stop_reason", hook_input.get("stopReason", ""))).lower()
    return reason in ("aborted", "abort", "cancel", "interrupt")

def main():
    # ==================== 读取 hook 输入 ====================
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    stop_hook_active = hook_input.get("stop_hook_active", False)

    # ==================== 关键: 从 hook 输入获取项目目录 ====================
    # Claude Code 传入 cwd 字段，比 find_project_root() 更可靠
    hook_cwd = hook_input.get("cwd") or hook_input.get("directory") or ""

    # ==================== 必须放行的停止类型 ====================
    # 上下文满 → 必须放行，否则死锁（无法 compact）
    if is_context_limit_stop(hook_input):
        output_continue()
        sys.exit(0)

    # 用户主动中断 → 尊重用户意愿
    if is_user_abort(hook_input):
        output_continue()
        sys.exit(0)

    # ==================== 读取 harness 状态 ====================
    if hook_cwd:
        project_root = Path(hook_cwd)
    else:
        project_root = find_project_root()

    state_file = project_root / ".claude" / "harness-state.json"
    eval_log = project_root / ".claude" / "harness-eval.jsonl"

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        sys.exit(0)

    # ==================== 旧格式兼容 ====================
    # v2 之前的 /dev skill 可能手写 state，格式为 {"stages": {...}} 而非 {"pipeline": [...]}
    # 这里自动转换，确保 Stop Hook 能正常工作
    if "stages" in state and "pipeline" not in state:
        state = migrate_legacy_state(state)
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # ==================== 多模式分流（v3.3） ====================
    mode = state.get("mode", "pipeline")
    if mode == "conversation":
        # conversation 模式不干预
        sys.exit(0)

    # ==================== Session ID 隔离 ====================
    # 如果 hook 输入中有 session_id，且 state 中也有，两者必须匹配
    # 防止多 session 互相干扰
    hook_session = hook_input.get("session_id", "")
    state_session = state.get("session_id", "")
    if hook_session and state_session and hook_session != state_session:
        # 不同 session 的状态，不干预
        sys.exit(0)

    if state.get("paused"):
        if state.get("pause_reason") == "rate_limit":
            resume_at = parse_iso(state.get("resume_at", ""))
            if resume_at and now_utc() >= resume_at:
                state["paused"] = False
                state["pause_reason"] = ""
                state["resume_at"] = ""
                save_state(state, state_file)
                reason = "Rate limit 暂停已恢复，继续执行当前阶段。"
                output_block(reason, state, project_root)
                return
        sys.exit(0)

    current = state.get("current_stage")
    if not current:
        sys.exit(0)

    pipeline = state.get("pipeline", [])
    stage = next((s for s in pipeline if s["name"] == current), None)
    if not stage:
        sys.exit(0)

    max_retries = state.get("metrics", {}).get("max_retries", 3)

    # ==================== 防线优先级（C3: 从互斥改为有序聚合） ====================
    # 优先级: context_overflow > rate_limit > 超时/频率
    # context_overflow 必须最先检查——上下文满时必须放行让 compact，其他防线都无意义

    # ==================== 防线 1: 上下文使用率（最高优先级） ====================
    ctx = hook_input.get("context_window", {})
    ctx_used = ctx.get("used", 0)
    ctx_total = ctx.get("total", 1)
    ctx_pct = (ctx_used / ctx_total * 100) if ctx_total > 0 else 0
    if ctx_pct > CONTEXT_OVERFLOW_PCT:
        for s in pipeline:
            if s["name"] == "remember":
                s["status"] = "PENDING"
        save_state(state, state_file)
        log_eval(project_root, state, "context_overflow", f"ctx={ctx_pct:.0f}%，放行让 compact")
        output_continue()
        sys.exit(0)

    # ==================== 防线 2: Rate Limit 检测 ====================
    last_msg = hook_input.get("last_assistant_message", "")
    if any(kw in last_msg.lower() for kw in RATE_LIMIT_KEYWORDS):
        state["paused"] = True
        state["pause_reason"] = "rate_limit"
        state["resume_at"] = (now_utc() + timedelta(minutes=RATE_LIMIT_PAUSE_MIN)).isoformat()
        save_state(state, state_file)
        log_eval(project_root, state, "rate_limit_pause",
                 f"暂停 {RATE_LIMIT_PAUSE_MIN}min，恢复时间: {state['resume_at']}")
        sys.exit(0)

    # ==================== 防线 3: 单阶段超时 ====================
    stage_timeout = state.get("metrics", {}).get("stage_timeout", STAGE_TIMEOUT_SEC)
    if stage.get("started_at"):
        stage_elapsed = elapsed_seconds(stage["started_at"])
        if stage_elapsed > stage_timeout:
            log_eval(project_root, state, "stage_timeout",
                     f"{current} 运行 {stage_elapsed:.0f}s > {stage_timeout}s")
            sys.exit(0)

    # ==================== 防线 4: 总运行时长 ====================
    max_duration = state.get("metrics", {}).get("max_duration", DEFAULT_MAX_DURATION)
    task_started = state.get("task", {}).get("started_at", "")
    if task_started:
        total_elapsed = elapsed_seconds(task_started)
        if total_elapsed > max_duration:
            log_eval(project_root, state, "total_timeout",
                     f"总时长 {total_elapsed:.0f}s > {max_duration}s")
            sys.exit(0)

    # ==================== 防线 5: 滑动窗口频率限制 ====================
    recent_count = count_recent_events(eval_log, minutes=SLIDING_WINDOW_MIN)
    if recent_count > SLIDING_WINDOW_MAX_EVENTS:
        log_eval(project_root, state, "frequency_limit",
                 f"{SLIDING_WINDOW_MIN}min 内 {recent_count} 次续跑 > {SLIDING_WINDOW_MAX_EVENTS}")
        sys.exit(0)

    # ==================== implement 阶段续跑逻辑（统一处理） ====================
    if current == "implement" and stage.get("status") == "IN_PROGRESS":
        action, reason = _handle_implement_continue(
            state, stage, project_root, state_file, max_retries,
            source="stop_hook_active" if stop_hook_active else "首次触发"
        )
        if action == "continue":
            output_block(reason, state, project_root)
            return
        elif action == "mark_done":
            save_state(state, state_file)
            # fall through 到阶段推进逻辑
        else:  # action == "exit"
            sys.exit(0)
    elif stop_hook_active:
        # 非 implement 阶段的 stop_hook_active → 不再续跑
        sys.exit(0)

    # ==================== 阶段产出验证 ====================

    def has_valid_reports(pattern, min_size=100):
        """H2: 检查报告文件存在且非空（>100 字节）"""
        reports_dir = project_root / ".claude" / "reports"
        if not reports_dir.exists():
            return False
        return any(f.stat().st_size >= min_size for f in reports_dir.glob(pattern))

    # audit 阶段标记 DONE 但缺少审计报告 → 打回重做
    if current == "audit" and stage.get("status") == "DONE":
        if not has_valid_reports("audit-*.md"):
            stage["status"] = "IN_PROGRESS"
            save_state(state, state_file)
            reason = (
                "audit 阶段缺少有效审计报告。请按 generic-audit skill 执行代码审计，"
                "输出报告到 .claude/reports/audit-{module}-{date}.md（不少于 100 字节），再标记 audit DONE。"
            )
            output_block(reason, state, project_root)
            return

    # review 阶段标记 DONE 但缺少审查报告 → 打回重做
    if current == "review" and stage.get("status") == "DONE":
        has_review = has_valid_reports("review-*.md")
        has_final = has_valid_reports("final-review*")
        if not has_review and not has_final:
            stage["status"] = "IN_PROGRESS"
            save_state(state, state_file)
            reason = (
                "review 阶段缺少审查报告。请按 generic-review skill 要求执行三路并行审查：\n"
                "1. Agent(run_in_background=true): 代码质量审查 → .claude/reports/review-code.md\n"
                "2. Agent(run_in_background=true): 安全审查 → .claude/reports/review-security.md\n"
                "3. Agent(run_in_background=true): 架构审查 → .claude/reports/review-arch.md\n"
                "三路完成后汇总到 .claude/reports/final-review.md，再标记 review DONE。"
            )
            output_block(reason, state, project_root)
            return

    # ==================== 并行组检查 ====================
    current_group = stage.get("parallel_group")
    if current_group and stage.get("status") == "DONE":
        # H1: 按 pipeline 原始顺序排序，确保确定性
        pipeline_order = {s["name"]: i for i, s in enumerate(pipeline)}
        group_stages = sorted(
            [s for s in pipeline if s.get("parallel_group") == current_group],
            key=lambda s: pipeline_order.get(s["name"], 999)
        )
        pending = [s for s in group_stages if s["status"] in ("PENDING", "IN_PROGRESS")]
        if pending:
            # H5: 并行组超时检测——IN_PROGRESS 超过 30 分钟视为卡住
            stuck = []
            for ps in pending:
                if ps.get("status") == "IN_PROGRESS" and ps.get("started_at"):
                    if elapsed_seconds(ps["started_at"]) > STAGE_TIMEOUT_SEC:
                        stuck.append(ps["name"])
            if stuck:
                log_eval(project_root, state, "parallel_group_timeout",
                         f"并行组 {current_group} 中 {'、'.join(stuck)} 超时")
            # 组内还有未完成的，不推进
            sys.exit(0)
        # 组内全部完成，推进到下一阶段
        last_in_group = group_stages[-1]["name"]
        next_names = find_next(pipeline, last_in_group)
        if not next_names:
            sys.exit(0)
        state["current_stage"] = next_names[0]
        state["metrics"]["auto_continues"] = state["metrics"].get("auto_continues", 0) + 1
        save_state(state, state_file)
        reason = f"并行组 {current_group} 全部完成（{'、'.join(s['name'] for s in group_stages)}）。继续执行 {next_names[0]} 阶段。"
        output_block(reason, state, project_root)
        return

    if stage.get("status") == "DONE":
        # single 模式: 所有指定阶段完成即结束
        if mode == "single":
            pending_stages = [s for s in pipeline if s["status"] == "PENDING"]
            if not pending_stages:
                sys.exit(0)  # 全部完成，正常结束
            # 还有待执行的阶段 → 续跑
            next_name = pending_stages[0]["name"]
            state["current_stage"] = next_name
            state["metrics"]["auto_continues"] = state["metrics"].get("auto_continues", 0) + 1
            save_state(state, state_file)
            reason = f"单 Skill 模式: {current} 完成。继续执行 {next_name}。"
            output_block(reason, state, project_root)
            return

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

    sys.exit(0)

def find_next(pipeline, current_name):
    """找到下一组可执行阶段（支持 parallel_group）"""
    found = False
    for s in pipeline:
        if s["name"] == current_name:
            found = True
            continue
        if not found:
            continue
        if s.get("status") != "PENDING":
            continue
        group = s.get("parallel_group")
        if group:
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps.get("status") == "PENDING"]
        return [s["name"]]
    return []

def output_block(reason, state, project_root):
    decision = {"decision": "block", "reason": reason}
    print(json.dumps(decision, ensure_ascii=False))
    log_eval(project_root, state, "auto_continue", reason)

def save_state(state, path):
    state["updated_at"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock", timeout=10)
    with lock:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
