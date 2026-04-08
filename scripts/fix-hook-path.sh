#!/bin/bash
# 修复 settings.json 中的 stop-hook 硬编码路径
# 仅在用户主动运行时执行，不在 setup.sh 中自动执行

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"

CLAUDE_DIR="$HOME/.claude"
if [[ "$OS" == "Windows_NT" || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    CLAUDE_DIR="$(cygpath -u "$USERPROFILE")/.claude"
fi
SETTINGS="$CLAUDE_DIR/settings.json"
HOOKS_DIR="$CLAUDE_DIR/hooks"
WRAPPER_SRC="$PLUGIN_DIR/hooks/stop-hook-wrapper.py"
WRAPPER_DST="$HOOKS_DIR/dev-harness-stop.py"

if [ ! -f "$SETTINGS" ]; then
    echo "未找到 $SETTINGS"
    exit 1
fi

# 1. 部署 wrapper
mkdir -p "$HOOKS_DIR"
if [ -f "$WRAPPER_SRC" ]; then
    cp "$WRAPPER_SRC" "$WRAPPER_DST"
    echo "[OK] wrapper 已部署到 $WRAPPER_DST"
else
    echo "[ERROR] 未找到 $WRAPPER_SRC"
    exit 1
fi

# 2. 用 JSON 层面精确修改 settings.json（不用正则替换文本）
python -c "
import json, sys

settings_path = sys.argv[1]
wrapper_path = sys.argv[2]

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

hooks = settings.get('hooks', {})
stop_hooks = hooks.get('Stop', [])

changed = False
for entry in stop_hooks:
    for h in entry.get('hooks', []):
        cmd = h.get('command', '')
        if 'dev-harness' in cmd and 'stop-hook' in cmd:
            new_cmd = f'python {wrapper_path}'
            if cmd != new_cmd:
                h['command'] = new_cmd
                changed = True

if changed:
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    print('[OK] settings.json hook 路径已更新为 wrapper')
else:
    print('[OK] settings.json hook 路径无需更新')
" "$SETTINGS" "$WRAPPER_DST"
