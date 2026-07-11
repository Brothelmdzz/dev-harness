#!/bin/bash
# Dev Harness Python 入口 — 统一使用插件内置 venv
# 用法: bash dh-python.sh <script.py> [args...]
#
# 查找顺序（v4.5 起 CLAUDE_PLUGIN_DATA 优先，venv 迁到升级后仍存活的持久目录）:
#   1. ${CLAUDE_PLUGIN_DATA}/.venv   —— 官方持久目录，插件升级不作废（首选）
#   2. ${CLAUDE_PLUGIN_ROOT}/.venv   —— 版本化目录，兼容旧安装（回退）
#   3. fallback 到系统 python（降级）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 兼容 Claude Code / Cursor IDE — 优先 CLAUDE_PLUGIN_ROOT，其次 CURSOR_PLUGIN_ROOT
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-${CURSOR_PLUGIN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}}"

# venv 候选目录：DATA 优先，ROOT 兜底
VENV_CANDIDATES=()
if [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
    VENV_CANDIDATES+=("$CLAUDE_PLUGIN_DATA/.venv")
fi
VENV_CANDIDATES+=("$PLUGIN_ROOT/.venv")

# 按平台在候选目录里找第一个可用的 venv python
for VENV_DIR in "${VENV_CANDIDATES[@]}"; do
    if [ -f "$VENV_DIR/bin/python" ]; then
        exec "$VENV_DIR/bin/python" "$@"
    elif [ -f "$VENV_DIR/Scripts/python.exe" ]; then
        exec "$VENV_DIR/Scripts/python.exe" "$@"
    elif [ -f "$VENV_DIR/bin/python3" ]; then
        exec "$VENV_DIR/bin/python3" "$@"
    fi
done

# fallback: 系统 python
if command -v python >/dev/null 2>&1; then
    exec python "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 "$@"
fi

echo "ERROR: Python not found" >&2
exit 1
