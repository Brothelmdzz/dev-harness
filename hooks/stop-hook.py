#!/usr/bin/env python3
"""
Dev Harness Stop Hook — 阻止 Claude 在 Pipeline 未完成时停下

机制（Claude Code 官方）:
  - Stop hook 通过 stdin 接收 JSON: {session_id, stop_hook_active, last_assistant_message}
  - 输出 {"decision": "block", "reason": "..."} → Claude 自动续跑
  - 输出空/exit 0 → Claude 正常停止
  - stop_hook_active=true → 已经续跑过一轮，需检查是否应该停止（防无限循环）
"""
import json, sys, os
from pathlib import Path
from datetime import datetime, timezone

def find_project_root():
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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

    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        sys.exit(0)  # 没有 harness 会话，不干预

    if state.get("paused"):
        sys.exit(0)

    current = state.get("current_stage")
    if not current:
        sys.exit(0)

    pipeline = state.get("pipeline", [])
    stage = next((s for s in pipeline if s["name"] == current), None)
    if not stage:
        sys.exit(0)

    max_retries = state.get("metrics", {}).get("max_retries", 3)

    # ==================== 防无限循环 ====================
    # stop_hook_active=true 表示上一轮已经续跑过
    # 此时只在 implement 阶段的 Phase 间续跑，其他阶段让 Claude 自行判断
    if stop_hook_active:
        # 仅 implement 阶段 Phase 间自动续跑（最核心的痛点）
        if current == "implement" and stage.get("status") == "IN_PROGRESS":
            phases = stage.get("phases", [])
            for p in phases:
                if p.get("error_count", 0) >= max_retries:
                    sys.exit(0)  # 死循环
            pending = [p for p in phases if p.get("status") == "PENDING"]
            if pending:
                reason = f"继续实现下一个 Phase: {pending[0].get('name', '?')}。读取 plan 文件确认内容后执行。完成后更新 harness-state.json。"
                output_block(reason, state, project_root)
                return
        # 其他场景，stop_hook_active 时不再续跑（避免死循环）
        sys.exit(0)

    # ==================== 首次触发（stop_hook_active=false） ====================

    # implement 阶段: 检查 Phase 进度
    if current == "implement" and stage.get("status") == "IN_PROGRESS":
        phases = stage.get("phases", [])

        # 死循环检测
        for p in phases:
            if p.get("error_count", 0) >= max_retries:
                sys.exit(0)

        pending = [p for p in phases if p.get("status") == "PENDING"]
        if pending:
            reason = f"继续实现下一个 Phase: {pending[0].get('name', '?')}。读取 plan 文件确认该 Phase 内容，然后执行。完成后更新 harness-state.json。"
            output_block(reason, state, project_root)
            return

        # 所有 Phase 完成 → 标记 implement DONE
        stage["status"] = "DONE"
        stage["completed_at"] = now_iso()
        state["metrics"]["stages_completed"] = state["metrics"].get("stages_completed", 0) + 1
        save_state(state, state_file)

    # 当前阶段已完成 → 推进
    if stage.get("status") == "DONE":
        next_names = find_next(pipeline, current)
        if not next_names:
            sys.exit(0)  # 全部完成

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

    # 其他状态不干预
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
    """输出 block decision JSON → Claude 自动续跑"""
    decision = {
        "decision": "block",
        "reason": reason,
    }
    print(json.dumps(decision, ensure_ascii=False))
    log_eval(project_root, state, "auto_continue", reason)

def save_state(state, path):
    state["updated_at"] = now_iso()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
