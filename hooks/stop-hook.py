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
  - （原防线 2 上下文使用率检测已于 v4.5 删除：context_window 字段不在两平台 Stop schema 内）
  - 防线 3: 单阶段超时 (默认 30min)
  - 防线 4: 总运行时长上限 (默认 2h)
  - 防线 5: 滑动窗口频率限制 (5min 内 > 10 次 → 死循环)
  - 防线 6: error_count >= max_retries → 死循环

v3.4.2 改进（Nudge 软提醒层）:
  - 防线 3/4/5 首次触发 → advisory + 续跑（让 Claude 自纠偏），
    同 stage 内再次触发 → 原硬停逻辑。计数器在 stage 切换时自动重置。
  - 设计动机：保留"硬续跑"差异化优势，但在硬停之前给一次软提醒，
    让 Claude 有机会自己产出阶段结果或转 remember；
    跟 barkain 风格的"5 级 nudge"思路同源但更轻量（不引入 PreToolUse hook）。
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Windows GBK 控制台防御：block reason 摘要含 U+2192(→) 等非 ASCII 字符，
# 若 stdout 仍是 GBK 编码，print(json.dumps(..., ensure_ascii=False)) 会 UnicodeEncodeError
# → hook 崩溃 → 不输出 decision → pipeline 断裂。强制 UTF-8（CLAUDE.md Windows 编码铁律）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# 让 hooks 能 import scripts/lib/
_plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_plugin_root / "scripts"))

from lib.compat import FileLock
from lib.state import save_state as _lib_save_state
from lib.hook_trace import hook_start as _hook_start, hook_end as _hook_end, check_stale_hooks, log_stale_hooks

# ==================== 默认常量（可通过 dev-config.yml 的 limits 段覆盖） ====================

_DEFAULT_STAGE_TIMEOUT_SEC = 1800
_DEFAULT_MAX_DURATION = 7200
_DEFAULT_SLIDING_WINDOW_MIN = 5
_DEFAULT_SLIDING_WINDOW_MAX_EVENTS = 10
_DEFAULT_CONTEXT_OVERFLOW_PCT = 80
_DEFAULT_RATE_LIMIT_PAUSE_MIN = 15
# v3.4.4 HIGH-A fix：原来用列表子串匹配（含裸 "resets"），用户讨论 rate limit / session reset
# 等任何话题都会误触发 → 整个 pipeline 暂停 15 分钟。改用严格 regex 模式，要求强信号词组：
# - 完整词边界 "rate limit / rate_limit"
# - 平台明确告知短语 "hit your/the limit"
# - HTTP 429 状态码（独立词）
# - "too many requests" 短语
# - "limit resets at/in" 平台告知短语（不再匹配裸 "resets"）
import re as _re_rl
# v3.4.4 HIGH-A 严格化：必须是 强动词 + (rate )limit 才算信号，单独 "rate limit" / "rate limiting"
# 不触发——用户讨论"如何实现 rate limiting"等场景太常见。
# 触发条件（OR）：
#   1. <hit|reached|exceeded|encountered|exhausted> [the/your/a/my/our] (rate-)limit
#   2. rate-limit <exceeded|reached|exhausted|hit|hits>（动词在后）
#   3. 标准 HTTP 信号：429 / too many requests
#   4. 平台告知格式："limit resets at/in ..."
#   5. HTTP header 名 x-rate-limit-*
RATE_LIMIT_RE = _re_rl.compile(
    r"\b(?:hit|reached|exceeded|encountered|exhausted)\s+"
    r"(?:the\s+|your\s+|a\s+|my\s+|our\s+)?(?:rate[\s_-]?)?limit"
    r"|rate[\s_-]?limit\s+(?:has\s+been\s+|was\s+|were\s+|been\s+)?"
    r"(?:exceeded|reached|exhausted|hit|hits)"
    r"|too\s+many\s+requests"
    r"|\b429\b"
    r"|limit\s+resets?\s+(?:at|in)\b"
    r"|x[-_]?rate[-_]?limit",
    _re_rl.IGNORECASE,
)

def _get_limits(state):
    """从 state["limits"] 读取参数，fallback 硬编码默认值"""
    limits = state.get("limits", {})
    # 同时兼容旧版 state 中 metrics 里的值
    metrics = state.get("metrics", {})
    return {
        "stage_timeout":        limits.get("stage_timeout",        metrics.get("stage_timeout", _DEFAULT_STAGE_TIMEOUT_SEC)),
        "max_duration":         limits.get("max_duration",         metrics.get("max_duration", _DEFAULT_MAX_DURATION)),
        "window_minutes":       limits.get("window_minutes",       _DEFAULT_SLIDING_WINDOW_MIN),
        "max_events":           limits.get("max_events",           _DEFAULT_SLIDING_WINDOW_MAX_EVENTS),
        "context_overflow_pct": limits.get("context_overflow_pct", _DEFAULT_CONTEXT_OVERFLOW_PCT),
        "rate_limit_pause_min": limits.get("rate_limit_pause_min", _DEFAULT_RATE_LIMIT_PAUSE_MIN),
    }

# ==================== 共享库导入 ====================
from lib.project import find_project_root as _lib_find_project_root
from lib.utils import now_iso, now_utc, parse_iso, elapsed_seconds
from lib.plan import parse_phases_from_plan_dir as _parse_phases_from_plan_dir
from lib.pipeline import (
    has_depends_on as _has_depends_on,
    find_next_by_deps as _find_next_by_deps,
    find_next_by_order as _find_next_by_order,
    find_next_runnable as _lib_find_next,
)
from lib.pitfall import build_pitfall_context, capture_failure

def find_project_root():
    """stop-hook 需要 scan_fallback=True（hook cwd 可能不在项目目录）"""
    return _lib_find_project_root(scan_fallback=True)

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
    """从最新 plan 文件解析 Phase 列表（委托给 lib.plan）"""
    return _parse_phases_from_plan_dir(project_root)

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

    # v3.4.4 MEDIUM-G fix：迁移时主动加载 dev-config.yml 的 limits 段，
    # 否则迁移后的 state 没 limits 段，stop-hook _get_limits() 只能 fallback 硬编码默认值，
    # 用户在 dev-config.yml 配置的所有 limits 失效。
    try:
        from lib.config import load_dev_config as _lib_load_dev_config
        _project_for_cfg = old.get("_project_root") or "."
        _cfg = _lib_load_dev_config(_project_for_cfg)
        _raw_limits = _cfg.get("limits", {}) if isinstance(_cfg.get("limits"), dict) else {}
        _limits = {
            "stage_timeout":        int(_raw_limits.get("stage_timeout", 1800)),
            "max_duration":         int(_raw_limits.get("max_duration", 7200)),
            "window_minutes":       int(_raw_limits.get("window_minutes", 5)),
            "max_events":           int(_raw_limits.get("max_events", 10)),
            "context_overflow_pct": int(_raw_limits.get("context_overflow_pct", 80)),
            "rate_limit_pause_min": int(_raw_limits.get("rate_limit_pause_min", 15)),
            "max_retries":          int(_raw_limits.get("max_retries", 3)),
        }
    except Exception:
        _limits = {}  # 任何异常都不影响迁移本身，_get_limits 会 fallback 硬编码默认值
    return {
        "version": "1.0",
        "project": old.get("project", ""),
        "task": task_obj,
        "pipeline": pipeline,
        "current_stage": old.get("current_stage", ""),
        "paused": old.get("paused", False),
        "limits": _limits,
        "metrics": {
            "total_errors": 0, "auto_fixed": 0, "blocking": 0,
            "max_retries": _limits.get("max_retries", 3),
            "stages_completed": 0, "auto_continues": 0,
            "max_duration": _limits.get("max_duration", 7200),
        },
        "_migrated_from": "legacy",
    }

# ==================== 上下文摘要（注入 block reason） ====================

def _build_context_summary(state, project_root):
    """构建简洁的 Pipeline 上下文摘要，附加到 block reason 尾部。
    最多 5 行，帮助 Claude 知道当前位置和已发生的事。"""
    lines = []

    # 1. Pipeline 进度一览
    pipeline = state.get("pipeline", [])
    if pipeline:
        stage_parts = []
        for s in pipeline:
            name = s.get("name", "?")
            status = s.get("status", "PENDING")
            current = state.get("current_stage", "")
            if status == "DONE":
                tag = "DONE"
            elif status == "IN_PROGRESS":
                # implement 阶段附加 phase 进度
                phases = s.get("phases", [])
                if phases:
                    done_count = sum(1 for p in phases if p.get("status") == "DONE")
                    tag = f"IN_PROGRESS {done_count}/{len(phases)}"
                else:
                    tag = "IN_PROGRESS"
            elif status == "SKIP":
                tag = "SKIP"
            elif status == "FAILED":
                tag = "FAILED"
            else:
                tag = "PENDING"
            stage_parts.append(f"{name}[{tag}]")
        lines.append("Pipeline: " + " → ".join(stage_parts))

    # 2. 当前 Phase 进度（仅 implement 阶段）
    current_stage_name = state.get("current_stage", "")
    if current_stage_name == "implement":
        stage_obj = next((s for s in pipeline if s["name"] == "implement"), None)
        if stage_obj:
            phases = stage_obj.get("phases", [])
            if phases:
                phase_details = []
                for p in phases:
                    pname = p.get("name", "?")
                    pstatus = p.get("status", "PENDING")
                    gates = p.get("gates", {})
                    # v4.0 Gate Feedback Loop：DONE 显示全部 gate；IN_PROGRESS 仅强调失败的 gate
                    # 失败的 gate 是 agent 当前最需要的 ground truth
                    if gates:
                        if pstatus == "DONE":
                            gate_str = " ".join(f"{k}={'pass' if v else 'FAIL'}" for k, v in gates.items())
                            phase_details.append(f"{pname}: {pstatus} (gates: {gate_str})")
                        else:
                            failed = [k for k, v in gates.items() if not v]
                            if failed:
                                phase_details.append(f"{pname}: {pstatus} (FAIL: {', '.join(failed)})")
                            else:
                                phase_details.append(f"{pname}: {pstatus}")
                    else:
                        phase_details.append(f"{pname}: {pstatus}")
                lines.append("Phases: " + " | ".join(phase_details))

    # 3. 累计错误
    error_count = state.get("metrics", {}).get("total_errors", 0)
    if error_count > 0:
        lines.append(f"累计错误: {error_count}")

    # B 阶段：续跑前把最近踩坑作为 ground truth 注入下一轮 prompt
    try:
        pitfall_ctx = build_pitfall_context(project_root, max_recent=5)
    except Exception:
        pitfall_ctx = ""

    if not lines and not pitfall_ctx:
        return ""
    result = ""
    if lines:
        result = "\n\n当前状态:\n" + "\n".join("- " + l for l in lines)
    if pitfall_ctx:
        result += pitfall_ctx

    # v3.4.4 MEDIUM-2 fix：总长度上限。phases 多/pitfall 累计时 reason 可能 ~3000+ 字符，
    # 每次续跑都吃 Claude 几千 tokens 上下文预算，无谓加速上下文膨胀。
    # 2000 字符约 500-800 tokens（中英文混合），是续跑摘要的合理上限。
    MAX_REASON_CTX = 2000
    if len(result) > MAX_REASON_CTX:
        result = result[:MAX_REASON_CTX].rstrip() + \
                 "\n…(摘要截断，完整状态见 .claude/harness-state.json 与 .claude/pitfall-journal.jsonl)"
    return result

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

# is_context_limit_stop() 与 is_user_abort() 已删除（v4.5）：
# 二者读取的 stop_reason / end_turn_reason / user_requested 等字段均不在 CC / Codex
# 两平台 Stop payload schema 内（2026-07 官方文档核验），恒返回 False → 恒不放行，
# 是字段名臆测出的死代码。上下文满/用户中断改由平台原生行为处理（auto-compact / Ctrl+C），
# 删除后控制流与现状完全等价。

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

    # 上下文满/用户中断的放行分支已删除（v4.5）：所依赖字段不在两平台 Stop schema 内，
    # 恒不触发。上下文管理下沉给平台 auto-compact，用户中断由平台原生 Ctrl+C 处理。

    # ==================== 读取 harness 状态 ====================
    if hook_cwd:
        project_root = Path(hook_cwd)
    else:
        project_root = find_project_root()

    # hook 超时追踪：检测上次残留 + 记录本次开始
    stale = check_stale_hooks(project_root)
    if stale:
        log_stale_hooks(project_root, stale)
    _hook_start("stop-hook", project_root)

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
        save_state(state, state_file)

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
    # P2-9: state 有 session_id 但 hook 缺时，默认不匹配（防绕过）
    if state_session and (not hook_session or hook_session != state_session):
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

    max_retries = state.get("limits", {}).get("max_retries",
                   state.get("metrics", {}).get("max_retries", 3))
    lim = _get_limits(state)

    # ==================== 防线优先级 ====================
    # 优先级: rate_limit > 超时/频率
    # 原防线①（上下文使用率）已删除（v4.5）：读取的 context_window 字段两平台 Stop payload
    # 均无（2026-07 官方文档核验），ctx_pct 恒为 0 → 分支恒不触发，是死代码。上下文管理下沉
    # 给平台 auto-compact；需要溢出后动作应改挂 PreCompact 事件，而非在 Stop payload 里猜字段。

    # ==================== 防线 2: Rate Limit 检测 ====================
    # Codex 侧 last_assistant_message 可为 null；.get(k, "") 对 null 返回 None，
    # 会让 RATE_LIMIT_RE.search(None) 抛 TypeError → hook 崩溃。用 `or ""` 兜底。
    last_msg = hook_input.get("last_assistant_message") or ""
    if RATE_LIMIT_RE.search(last_msg):
        state["paused"] = True
        state["pause_reason"] = "rate_limit"
        state["resume_at"] = (now_utc() + timedelta(minutes=lim["rate_limit_pause_min"])).isoformat()
        save_state(state, state_file)
        log_eval(project_root, state, "rate_limit_pause",
                 f"暂停 {lim['rate_limit_pause_min']}min，恢复时间: {state['resume_at']}")
        sys.exit(0)

    # ==================== Nudge: 软提醒分级（v3.4.2 起）====================
    # 防线 3/4/5 首次触发 → advisory + 续跑（让 Claude 自纠偏）；
    # 同一防线在同一 stage 内再次触发 → 原有 hard stop 逻辑。
    # 切换 stage 时计数器自动重置（确保新阶段是干净的）。
    nudge = state.setdefault("nudge_state", {})
    if nudge.get("stage") != current:
        nudge["stage"] = current
        nudge["counts"] = {}
    nudge_counts = nudge["counts"]

    def _soft_or_hard(defense_name, advisory_msg, hard_log_msg):
        """第一次触发某防线：advisory + 续跑；第二次（同 stage 内）：硬停。
        返回 "soft" 表示已注入 advisory 并准备续跑（调用方应 return），
        返回 "hard" 表示该执行原硬停逻辑（调用方应 sys.exit(0)）。"""
        if nudge_counts.get(defense_name, 0) == 0:
            nudge_counts[defense_name] = 1
            save_state(state, state_file)
            log_eval(project_root, state, f"{defense_name}_advisory",
                     f"软提醒 1/2 · {hard_log_msg}")
            output_block(advisory_msg, state, project_root)
            return "soft"
        log_eval(project_root, state, defense_name,
                 f"hard stop (after 1 advisory) · {hard_log_msg}")
        return "hard"

    # ==================== 防线 3: 单阶段超时 ====================
    if stage.get("started_at"):
        stage_elapsed = elapsed_seconds(stage["started_at"])
        if stage_elapsed > lim["stage_timeout"]:
            result = _soft_or_hard(
                "stage_timeout",
                f"[Dev Harness 软提醒 1/2] 当前阶段 `{current}` 已运行 {stage_elapsed:.0f}s，"
                f"超过单阶段建议时长 {lim['stage_timeout']}s。\n"
                f"请尽快产出阶段结果；如果卡住了，建议拆分子任务或转入 remember。\n"
                f"再次触发同一防线将硬停止本会话。",
                f"{current} 运行 {stage_elapsed:.0f}s > {lim['stage_timeout']}s",
            )
            if result == "soft":
                return
            sys.exit(0)

    # ==================== 防线 4: 总运行时长 ====================
    task_started = state.get("task", {}).get("started_at", "")
    if task_started:
        total_elapsed = elapsed_seconds(task_started)
        if total_elapsed > lim["max_duration"]:
            result = _soft_or_hard(
                "total_timeout",
                f"[Dev Harness 软提醒 1/2] 任务总运行时长 {total_elapsed:.0f}s，"
                f"超过上限 {lim['max_duration']}s。\n"
                f"建议立即触发 /remember 保存进度，由用户决定是否新会话续跑。\n"
                f"再次触发同一防线将硬停止本会话。",
                f"总时长 {total_elapsed:.0f}s > {lim['max_duration']}s",
            )
            if result == "soft":
                return
            sys.exit(0)

    # ==================== 防线 5: 滑动窗口频率限制 ====================
    recent_count = count_recent_events(eval_log, minutes=lim["window_minutes"])
    if recent_count > lim["max_events"]:
        result = _soft_or_hard(
            "frequency_limit",
            f"[Dev Harness 软提醒 1/2] 最近 {lim['window_minutes']}min 内已续跑 {recent_count} 次，"
            f"超过窗口上限 {lim['max_events']}。\n"
            f"这通常意味着死循环。请审视当前 phase 是否真的在推进，必要时停下来报告用户。\n"
            f"再次触发同一防线将硬停止本会话。",
            f"{lim['window_minutes']}min 内 {recent_count} 次续跑 > {lim['max_events']}",
        )
        if result == "soft":
            return
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

    def has_valid_reports(pattern, min_size=500):
        """H2: 检查报告文件存在、>=500 字节、且有至少 2 个 ## 标题"""
        reports_dir = project_root / ".claude" / "reports"
        if not reports_dir.exists():
            return False
        for f in reports_dir.glob(pattern):
            if f.stat().st_size < min_size:
                continue
            try:
                text = f.read_text(encoding="utf-8")
                if text.count("\n## ") + (1 if text.startswith("## ") else 0) >= 2:
                    return True
            except OSError:
                continue
        return False

    # audit 阶段标记 DONE 但缺少审计报告 → 打回重做
    if current == "audit" and stage.get("status") == "DONE":
        if not has_valid_reports("audit-*.md"):
            stage["status"] = "IN_PROGRESS"
            # B 阶段：失败入 pitfall journal，下次续跑会作为 ground truth 注入
            try:
                capture_failure(
                    project_root,
                    category="review",
                    phase="audit",
                    summary="audit 标记 DONE 但缺少有效审计报告",
                    root_cause="reports/audit-*.md 不存在或不满足最低产出（>=500 字节 + ≥2 个 ## 标题）",
                    resolution="按 generic-audit skill 重新生成 .claude/reports/audit-{module}-{date}.md",
                )
            except Exception:
                pass  # B 阶段最高准则：不能让 pitfall 写入失败导致 stop-hook 崩溃
            save_state(state, state_file)
            reason = (
                "audit 阶段缺少有效审计报告。请按 generic-audit skill 执行代码审计，"
                "输出报告到 .claude/reports/audit-{module}-{date}.md（不少于 500 字节），再标记 audit DONE。"
            )
            output_block(reason, state, project_root)
            return

    # review 阶段标记 DONE 但缺少审查报告 → 打回重做
    if current == "review" and stage.get("status") == "DONE":
        has_review = has_valid_reports("review-*.md")
        has_final = has_valid_reports("final-review*")
        if not has_review and not has_final:
            stage["status"] = "IN_PROGRESS"
            # B 阶段：同样捕获到 pitfall journal
            try:
                capture_failure(
                    project_root,
                    category="review",
                    phase="review",
                    summary="review 标记 DONE 但缺少审查报告",
                    root_cause="reports/review-*.md 与 final-review.md 都不存在或不满足最低产出要求",
                    resolution="按 generic-review skill 三路并行审查后汇总到 final-review.md",
                )
            except Exception:
                pass
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
                    if elapsed_seconds(ps["started_at"]) > lim["stage_timeout"]:
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
            _finalize_session_in_index(state.get("session_id", ""))
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
                _finalize_session_in_index(state.get("session_id", ""))
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
            _finalize_session_in_index(state.get("session_id", ""))
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
    """找到下一组可执行阶段（委托给 lib.pipeline）"""
    return _lib_find_next(pipeline, current_name)

def output_block(reason, state, project_root):
    ctx = _build_context_summary(state, project_root)
    if ctx:
        reason = reason + ctx
    decision = {"decision": "block", "reason": reason}
    print(json.dumps(decision, ensure_ascii=False))
    log_eval(project_root, state, "auto_continue", reason)

def save_state(state, path):
    """原子化写入 state — 委托给 lib.state"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _lib_save_state(path, state)


def _finalize_session_in_index(session_id):
    """兜底清理：stop-hook 触发终结类防线时标记 session 为 finished。
    避免异常退出的 session 残留在中央索引占位。

    v3.4.4 MEDIUM-F fix：原先重复 save_session_index 逻辑，且 POSIX 上没设 0o600，
    导致权限可能从 600 漂回 644。改用 lib.state.load_and_update_session_index，
    自动复用文件权限保护 + 减少代码重复。"""
    if not session_id:
        return
    try:
        from lib.state import load_and_update_session_index
        def _update(index):
            if session_id in index and not index[session_id].get("finished_at"):
                index[session_id]["finished_at"] = now_iso()
        load_and_update_session_index(_update)
    except Exception:
        pass

if __name__ == "__main__":
    try:
        main()
    finally:
        # 正常退出时清理 breadcrumb；被超时杀掉时 breadcrumb 残留供下次检测
        try:
            _hook_end("stop-hook", _lib_find_project_root(scan_fallback=True))
        except Exception:
            pass
