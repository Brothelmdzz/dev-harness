"""
Hook 超时追踪 — 面包屑机制检测被杀的 hook

每个 hook 启动时写 .hook-{name}-{pid}.running，结束时删除。
下次 session-init 或 hook 启动时检测残留的 breadcrumb → 说明上次被超时杀掉了。

v3.4.4 MEDIUM-C fix：breadcrumb 文件名加 PID，避免并发同名 hook 互相覆盖/误清。
例如用户连续 Write 两个 plan 文件 → plan-watcher hook 触发两次，第一个 hook_end
不应该清掉第二个的 breadcrumb。
"""
import json
import os
from pathlib import Path
from .utils import now_iso


def _breadcrumb_dir(project_root):
    d = Path(project_root) / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _breadcrumb_path(project_root, hook_name):
    return _breadcrumb_dir(project_root) / f".hook-{hook_name}-{os.getpid()}.running"


def hook_start(hook_name, project_root):
    """hook 入口处调用：写 breadcrumb 文件（含 PID）"""
    bc = _breadcrumb_path(project_root, hook_name)
    bc.write_text(json.dumps({"hook": hook_name, "pid": os.getpid(), "started_at": now_iso()}),
                  encoding="utf-8")


def hook_end(hook_name, project_root):
    """hook 正常退出前调用：删除本进程自己的 breadcrumb"""
    bc = _breadcrumb_path(project_root, hook_name)
    try:
        bc.unlink(missing_ok=True)
    except (OSError, TypeError):
        try:
            bc.unlink()
        except OSError:
            pass


def check_stale_hooks(project_root):
    """检测残留 breadcrumb（上次 hook 被超时杀掉的证据），返回并清理"""
    d = _breadcrumb_dir(project_root)
    stale = []
    for bc in d.glob(".hook-*.running"):
        try:
            info = json.loads(bc.read_text(encoding="utf-8"))
            stale.append(info)
            bc.unlink()
        except (OSError, json.JSONDecodeError):
            try:
                bc.unlink()
            except OSError:
                pass
    return stale


def log_stale_hooks(project_root, stale_hooks):
    """将检测到的 hook 超时事件追加到 harness-eval.jsonl"""
    if not stale_hooks:
        return
    log_file = Path(project_root) / ".claude" / "harness-eval.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        for info in stale_hooks:
            entry = {
                "timestamp": now_iso(),
                "project": "",
                "task": "",
                "event": "hook_timeout",
                "detail": f"hook '{info.get('hook', '?')}' 上次运行被超时杀掉 (started_at={info.get('started_at', '?')})",
                "stage": "",
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


__all__ = ["hook_start", "hook_end", "check_stale_hooks", "log_stale_hooks"]
