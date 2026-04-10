#!/usr/bin/env python3
"""Dev Harness Hook Runner — 跨平台 hook 启动器

解决 Windows/WSL 路径反斜杠转义问题: hooks.json 的 command 字符串里直接
写 `bash "${CLAUDE_PLUGIN_ROOT}/..."`  在 Cursor WSL 环境下会吃掉反斜杠,
导致 `C:\\Users\\...` 被处理成 `C:Users...` 找不到文件。

本脚本通过环境变量直接读 CLAUDE_PLUGIN_ROOT (不经 shell 字符串),
用 pathlib 规范化为 POSIX 风格路径, 再用 subprocess 的 list form 启动真正的
hook 脚本 (subprocess list form 绕过 shell 解析)。

用法:
    python hook-runner.py <hook_relative_path> [extra args...]

示例:
    python hook-runner.py hooks/session-init.sh
    python hook-runner.py hooks/stop-hook.py
    python hook-runner.py hooks/plan-watcher.py
"""
import os
import sys
import subprocess
from pathlib import Path


def resolve_plugin_root():
    """按优先级查找插件根目录"""
    # 1. 环境变量 (Claude Code / Cursor 均支持)
    for var in ("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT"):
        value = os.environ.get(var)
        if value:
            return Path(value)
    # 2. 脚本自定位 (scripts/hook-runner.py → 上层即插件根)
    return Path(__file__).resolve().parent.parent


def main():
    if len(sys.argv) < 2:
        # 没传 hook 路径, 静默退出 (不阻塞 Cursor/Claude Code 会话)
        sys.exit(0)

    plugin_root = resolve_plugin_root()
    hook_rel = sys.argv[1]
    hook_path = plugin_root / hook_rel

    if not hook_path.exists():
        # hook 文件不存在, 静默退出
        sys.exit(0)

    # 把路径转成 POSIX 风格, bash 在所有平台都能识别
    posix_path = hook_path.as_posix()
    extra_args = sys.argv[2:]

    # 透传 stdin (hook 可能通过 stdin 接收数据, 如 stop-hook)
    try:
        stdin_data = sys.stdin.buffer.read() if not sys.stdin.isatty() else None
    except (OSError, ValueError):
        stdin_data = None

    suffix = hook_path.suffix.lower()
    if suffix == ".sh":
        cmd = ["bash", posix_path] + extra_args
    elif suffix == ".py":
        # 优先用插件自带 venv python, fallback 当前 python
        venv_py = plugin_root / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        python_exe = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [python_exe, str(hook_path)] + extra_args
    else:
        # 未知后缀, 用 bash 尝试
        cmd = ["bash", posix_path] + extra_args

    try:
        result = subprocess.run(cmd, input=stdin_data, check=False)
        sys.exit(result.returncode)
    except FileNotFoundError:
        # bash 不可用等, 静默退出不阻塞会话
        sys.exit(0)
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
