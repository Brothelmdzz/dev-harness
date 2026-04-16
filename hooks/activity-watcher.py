#!/usr/bin/env python
"""PostToolUse Hook: 捕获 Write/Edit/Bash/Task 工具调用，写入 harness-state.json 的 activity 环形缓冲。

设计目标：让 Web HUD 能显示"AI 现在在干什么"（比如"刚写完 AuthService.java 正在跑 mvn test"），
而不是只看到 stage 级别的 IN_PROGRESS。

触发条件：
  - tool_name ∈ {Write, Edit, Bash, Task}
  - 项目下存在 .claude/harness-state.json（否则放行，不干预非 harness 项目）

写入规则：
  - 环形缓冲最多 30 条，旧条目自动淘汰
  - Bash 命令截到 120 字符，敏感关键字 (password/token/secret/key/apikey) 整行替换为 [REDACTED]
  - Write/Edit 记录相对项目根的文件路径
  - Task 记录 subagent_type + 简短 description
"""
import json, sys, os, re
from pathlib import Path
from datetime import datetime, timezone

# 让 hooks 能 import scripts/lib/
_plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_plugin_root / "scripts"))

ACTIVITY_MAX = 30
BASH_TRUNC = 120
SENSITIVE_PATTERN = re.compile(r'(password|token|secret|apikey|api_key|authorization|bearer)', re.IGNORECASE)


from lib.utils import now_iso
from lib.project import find_project_root as _lib_find_project_root
from lib.compat import FileLock


def extract_activity(tool_name, tool_input):
    """从 hook 输入提取 (target, summary) — target 简短展示，summary 是完整描述
    返回 None 表示跳过此次记录"""
    ti = tool_input or {}
    if tool_name in ("Write", "Edit"):
        fp = ti.get("file_path", "")
        if not fp:
            return None
        return {"target": Path(fp).name, "full_path": fp, "summary": ""}
    if tool_name == "Bash":
        cmd = ti.get("command", "")
        if not cmd:
            return None
        # 脱敏：任一行包含敏感词 → 整行替换
        if SENSITIVE_PATTERN.search(cmd):
            cmd = "[REDACTED]"
        else:
            cmd = cmd.replace("\n", " ").strip()
            if len(cmd) > BASH_TRUNC:
                cmd = cmd[:BASH_TRUNC] + "…"
        desc = ti.get("description", "")
        return {"target": cmd, "full_path": "", "summary": desc}
    if tool_name == "Task":
        subagent = ti.get("subagent_type", "") or ti.get("agent_type", "")
        desc = ti.get("description", "")
        if not subagent and not desc:
            return None
        return {"target": subagent or desc[:60], "full_path": "", "summary": desc}
    return None


def find_project_root_for(cwd_hint):
    """优先用 hook 输入的 cwd（委托给 lib.project）"""
    return _lib_find_project_root(cwd_hint=cwd_hint)


def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in ("Write", "Edit", "Bash", "Task"):
        sys.exit(0)

    activity = extract_activity(tool_name, hook_input.get("tool_input", {}))
    if not activity:
        sys.exit(0)

    project_root = find_project_root_for(hook_input.get("cwd") or hook_input.get("directory"))
    if not project_root:
        sys.exit(0)

    state_file = project_root / ".claude" / "harness-state.json"
    if not state_file.exists():
        sys.exit(0)

    # 相对路径美化
    if activity.get("full_path"):
        try:
            rel = Path(activity["full_path"]).resolve().relative_to(project_root)
            activity["target"] = str(rel).replace("\\", "/")
        except ValueError:
            pass

    lock = FileLock(str(state_file) + ".lock", timeout=3)

    try:
        with lock:
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, FileNotFoundError):
                sys.exit(0)

            buf = state.get("activity", [])
            if not isinstance(buf, list):
                buf = []

            entry = {
                "ts": now_iso(),
                "tool": tool_name,
                "target": activity["target"],
                "stage": state.get("current_stage", ""),
            }
            if activity.get("summary"):
                entry["summary"] = activity["summary"][:200]

            buf.append(entry)
            # 环形缓冲：超限截断最旧
            if len(buf) > ACTIVITY_MAX:
                buf = buf[-ACTIVITY_MAX:]
            state["activity"] = buf
            state["last_activity_at"] = entry["ts"]
            state["updated_at"] = entry["ts"]

            state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
    except Exception:
        # 任何异常都静默退出 —— 不能因为 hook 失败阻断用户工具调用
        sys.exit(0)


if __name__ == "__main__":
    main()
