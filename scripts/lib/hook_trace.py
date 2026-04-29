"""
Hook 超时追踪 — 面包屑机制检测被杀的 hook

每个 hook 启动时写 .hook-{name}.running，结束时删除。
下次 session-init 或 hook 启动时检测残留的 breadcrumb → 说明上次被超时杀掉了。
"""
import json
from pathlib import Path
from .utils import now_iso


def _breadcrumb_dir(project_root):
    d = Path(project_root) / ".claude"
    d.mkdir(parents=True, exist_ok=True)
    return d


def hook_start(hook_name, project_root):
    """hook 入口处调用：写 breadcrumb 文件"""
    bc = _breadcrumb_dir(project_root) / f".hook-{hook_name}.running"
    bc.write_text(json.dumps({"hook": hook_name, "started_at": now_iso()}), encoding="utf-8")


def hook_end(hook_name, project_root):
    """hook 正常退出前调用：删除 breadcrumb"""
    bc = _breadcrumb_dir(project_root) / f".hook-{hook_name}.running"
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
