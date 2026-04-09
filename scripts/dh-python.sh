#!/bin/bash
# Dev Harness Python 入口 — 统一使用插件内置 venv
# 用法: bash dh-python.sh <script.py> [args...]
#
# 查找顺序:
#   1. ${CLAUDE_PLUGIN_ROOT}/.venv 中的 python
#   2. 脚本同级目录的 ../.venv 中的 python
#   3. fallback 到系统 python（降级）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 兼容 Claude Code / Cursor IDE — 优先 CLAUDE_PLUGIN_ROOT，其次 CURSOR_PLUGIN_ROOT
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}}"
VENV_DIR="$PLUGIN_ROOT/.venv"

# 按平台查找 venv python
if [ -f "$VENV_DIR/bin/python" ]; then
    exec "$VENV_DIR/bin/python" "$@"
elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    exec "$VENV_DIR/Scripts/python.exe" "$@"
elif [ -f "$VENV_DIR/bin/python3" ]; then
    exec "$VENV_DIR/bin/python3" "$@"
fi

# fallback: 系统 python
if command -v python >/dev/null 2>&1; then
    exec python "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 "$@"
fi

echo "ERROR: Python not found" >&2
exit 1
