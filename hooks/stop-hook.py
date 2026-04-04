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
    查找项目根目录。优先从 cwd 向上找 .git，
    如果找不到（Hook cwd 可能不在项目目录下），
    则扫描常见工作目录下最近修改的 harness-state.json。
    """
    # 方式 1: 从 cwd 向上查找
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists() and (p / ".claude" / "harness-state.json").exists():
            return p
        p = p.parent

    # 方式 2: cwd 下直接有 .claude/harness-state.json（非 git 项目）
    cwd = Path.cwd()
    if (cwd / ".claude" / "harness-state.json").exists():
        return cwd

    # 方式 3: 扫描常见工作目录，找最近修改的 harness-state.json
    scan_dirs = []
    work_candidates = [
        Path("C:/work"),           # Windows 常见
        Path.home() / "work",      # ~/work
        Path.home() / "projects",  # ~/projects
        Path.home() / "src",       # ~/src
    ]
    for wc in work_candidates:
        try:
            if wc.exists() and wc.is_dir():
                scan_dirs.extend(d for d in wc.iterdir() if d.is_dir())
        except (PermissionError, OSError):
            pass

    best = None
    best_mtime = 0
    for d in scan_dirs:
        state = d / ".claude" / "harness-state.json"
        if state.exists():
            mtime = state.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = d

    if best:
        return best

    return Path.cwd()

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

def main():
    # ==================== 读取 hook 输入 ====================
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        hook_input = {}

    stop_hook_active = hook_input.get("stop_hook_active", False)

    # ==================== 读取 harness 状态 ====================
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

    # ==================== 防线 1: Rate Limit 检测 ====================
    last_msg = hook_input.get("last_assistant_message", "")
    if any(kw in last_msg.lower() for kw in RATE_LIMIT_KEYWORDS):
        state["paused"] = True
        state["pause_reason"] = "rate_limit"
        state["resume_at"] = (now_utc() + timedelta(minutes=RATE_LIMIT_PAUSE_MIN)).isoformat()
        save_state(state, state_file)
        log_eval(project_root, state, "rate_limit_pause",
                 f"暂停 {RATE_LIMIT_PAUSE_MIN}min，恢复时间: {state['resume_at']}")
        sys.exit(0)

    # ==================== 防线 2: 上下文使用率 ====================
    ctx = hook_input.get("context_window", {})
    ctx_used = ctx.get("used", 0)
    ctx_total = ctx.get("total", 1)
    ctx_pct = (ctx_used / ctx_total * 100) if ctx_total > 0 else 0
    if ctx_pct > CONTEXT_OVERFLOW_PCT:
        state["current_stage"] = "remember"
        for s in pipeline:
            if s["name"] == "remember":
                s["status"] = "PENDING"
        save_state(state, state_file)
        reason = f"上下文使用率 {ctx_pct:.0f}% > {CONTEXT_OVERFLOW_PCT}%，转入 remember 阶段保存进度。"
        output_block(reason, state, project_root)
        log_eval(project_root, state, "context_overflow", f"ctx={ctx_pct:.0f}%")
        return

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

    # ==================== 防循环: stop_hook_active ====================
    if stop_hook_active:
        if current == "implement" and stage.get("status") == "IN_PROGRESS":
            phases = stage.get("phases", [])
            for p in phases:
                if p.get("error_count", 0) >= max_retries:
                    sys.exit(0)
            pending = [p for p in phases if p.get("status") == "PENDING"]
            if pending:
                reason = f"继续实现下一个 Phase: {pending[0].get('name', '?')}。读取 plan 文件确认内容后执行。完成后更新 harness-state.json。"
                output_block(reason, state, project_root)
                return
        sys.exit(0)

    # ==================== 首次触发 ====================
    if current == "implement" and stage.get("status") == "IN_PROGRESS":
        phases = stage.get("phases", [])
        for p in phases:
            if p.get("error_count", 0) >= max_retries:
                sys.exit(0)
        pending = [p for p in phases if p.get("status") == "PENDING"]
        if pending:
            reason = f"继续实现下一个 Phase: {pending[0].get('name', '?')}。读取 plan 文件确认该 Phase 内容，然后执行。完成后更新 harness-state.json。"
            output_block(reason, state, project_root)
            return
        stage["status"] = "DONE"
        stage["completed_at"] = now_iso()
        state["metrics"]["stages_completed"] = state["metrics"].get("stages_completed", 0) + 1
        save_state(state, state_file)

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
            names = " 和 ".join(next_names)
            reason = f"上一阶段 {current} 已完成。并行启动 {names} 阶段。用 background Agent 并行执行两者。完成后更新 harness-state.json。"
        output_block(reason, state, project_root)
        return

    sys.exit(0)

def find_next(pipeline, current_name):
    found = False
    result = []
    for s in pipeline:
        if s["name"] == current_name:
            found = True
            continue
        if found and s.get("status") in ("PENDING", "WAITING"):
            result.append(s["name"])
            parallel = s.get("parallel_with")
            if parallel:
                for ps in pipeline:
                    if ps["name"] == parallel and ps.get("status") in ("PENDING", "WAITING"):
                        if ps["name"] not in result:
                            result.append(ps["name"])
            break
    return result

def output_block(reason, state, project_root):
    decision = {"decision": "block", "reason": reason}
    print(json.dumps(decision, ensure_ascii=False))
    log_eval(project_root, state, "auto_continue", reason)

def save_state(state, path):
    state["updated_at"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
