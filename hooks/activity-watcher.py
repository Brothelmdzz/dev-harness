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
import json, sys, re
from pathlib import Path

# 让 hooks 能 import scripts/lib/
_plugin_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_plugin_root / "scripts"))

ACTIVITY_MAX = 30
BASH_TRUNC = 120
# v3.4.4 MEDIUM-E fix：扩展敏感词覆盖——原列表漏了 private_key / client_secret /
# aws_* / ssh_key / GitHub PAT / OpenAI sk- 前缀 / jwt / cookie 等常见类型。
# activity 字段会被 web_hud SSE 推送到客户端，敏感命令暴露风险。
SENSITIVE_PATTERN = re.compile(
    r'password|token|secret|api[-_]?key|apikey|authorization|bearer|'
    r'private[-_]?key|client[-_]?secret|aws[-_]?(?:access|secret)|'
    r'ssh[-_]?key|cookie|jwt|'
    r'ghp_[a-z0-9]{20,}|ghs_[a-z0-9]{20,}|sk-[a-z0-9]{20,}',
    re.IGNORECASE,
)


from lib.utils import now_iso
from lib.project import find_project_root as _lib_find_project_root
from lib.state import load_and_update_state
from lib.hook_trace import hook_start as _hook_start, hook_end as _hook_end


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

    _hook_start("activity-watcher", project_root)

    # 相对路径美化
    if activity.get("full_path"):
        try:
            rel = Path(activity["full_path"]).resolve().relative_to(project_root)
            activity["target"] = str(rel).replace("\\", "/")
        except ValueError:
            pass

    try:
        def _update(state):
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
            if len(buf) > ACTIVITY_MAX:
                buf = buf[-ACTIVITY_MAX:]
            state["activity"] = buf
            state["last_activity_at"] = entry["ts"]

        load_and_update_state(state_file, _update)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    _project = None
    try:
        main()
    finally:
        try:
            _project = _lib_find_project_root()
            if _project:
                _hook_end("activity-watcher", _project)
        except Exception:
            pass
