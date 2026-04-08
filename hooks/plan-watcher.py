#!/usr/bin/env python
"""PostToolUse Hook: 监听 plan 文件写入，自动解析 Phase 列表并注册到 harness-state.json

解决的核心问题：SKILL.md 指引 Claude 注册 phases 是"概率性"的，
Claude 可能跳过注册导致 stop-hook 看到 phases=[] 无法续跑。
此 hook 在代码层面保证：只要 plan 文件写了，phases 就一定注册。
"""
import json, sys, os, re
from pathlib import Path
from datetime import datetime, timezone

def parse_phases_from_plan(plan_path):
    """从 plan 文件解析 Phase 列表"""
    text = Path(plan_path).read_text(encoding="utf-8")
    phases = []
    # 匹配: ## Phase N / ### Task N / ## 阶段 N（支持中英文冒号和各种分隔符）
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

def main():
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    # 只处理 Write 和 Edit 工具
    tool = hook_input.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        sys.exit(0)

    # 获取写入的文件路径
    tool_input = hook_input.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # 只匹配 .claude/plans/*.md
    fp = Path(file_path)
    if not (fp.suffix == ".md" and ".claude" in fp.parts and "plans" in fp.parts):
        sys.exit(0)

    if not fp.exists():
        sys.exit(0)

    # 解析 phases
    phases = parse_phases_from_plan(fp)
    if not phases:
        sys.exit(0)

    # 从文件路径向上找项目根（含 .claude/harness-state.json 的目录）
    project_root = fp.parent
    while project_root != project_root.parent:
        if (project_root / ".claude" / "harness-state.json").exists():
            break
        if (project_root / ".git").exists():
            break
        project_root = project_root.parent

    state_file = project_root / ".claude" / "harness-state.json"
    if not state_file.exists():
        sys.exit(0)

    # 更新 state 中的 implement phases（filelock 保护）
    try:
        from filelock import FileLock
        lock = FileLock(str(state_file) + ".lock", timeout=5)
    except ImportError:
        # filelock 未安装时降级为无锁写入
        lock = open(os.devnull, "w")  # no-op context manager
        lock.__enter__ = lambda: lock
        lock.__exit__ = lambda *a: None

    with lock:
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            sys.exit(0)

        for s in state.get("pipeline", []):
            if s["name"] == "implement":
                existing = s.get("phases", [])
                # 只在 phases 为空或数量不匹配时更新（避免覆盖已有进度）
                if not existing or len(existing) != len(phases):
                    for i, new_p in enumerate(phases):
                        if i < len(existing):
                            new_p["status"] = existing[i].get("status", "PENDING")
                            new_p["error_count"] = existing[i].get("error_count", 0)
                    s["phases"] = phases
                break

        state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
