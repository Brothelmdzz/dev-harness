"""
项目根发现 — 统一 find_project_root（6→1）

优先级链: override 参数 > DH_PROJECT 环境变量 > .git 向上查找 > harness-state 向上查找 > 扫描常见目录 > cwd
"""
import os
from pathlib import Path

def find_project_root(override=None, cwd_hint=None, scan_fallback=False):
    """
    定位项目根目录。

    Args:
        override: 直接指定的路径（最高优先级）
        cwd_hint: hook 环境下传入的 cwd（替代 Path.cwd()）
        scan_fallback: 是否在找不到时扫描常见目录（仅 stop-hook 场景需要）
    """
    # 优先级 1: 显式指定
    if override:
        return Path(override).resolve()

    # 优先级 2: 环境变量
    env = os.environ.get("DH_PROJECT")
    if env:
        return Path(env).resolve()

    # 优先级 3: 从 cwd（或 cwd_hint）向上查找 .git
    base = Path(cwd_hint).resolve() if cwd_hint else Path.cwd()
    p = base
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent

    # 优先级 4: 从 cwd 向上查找 harness-state.json（非 git 项目）
    p = base
    while p != p.parent:
        if (p / ".claude" / "harness-state.json").exists():
            return p
        p = p.parent

    # 优先级 5: 扫描常见目录（stop-hook 专用，限制扫描量）
    if scan_fallback:
        found = _scan_common_dirs()
        if found:
            return found

    return base

def _scan_common_dirs():
    """扫描常见开发目录，返回最近活跃的项目路径"""
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
    return best

__all__ = ["find_project_root"]
