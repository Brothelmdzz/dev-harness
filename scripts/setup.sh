#!/bin/bash
# Dev Harness 安装后配置脚本

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SETTINGS_FILE="$HOME/.claude/settings.json"

echo "=========================="
echo "  Dev Harness v2.0 Setup"
echo "=========================="
echo ""

# 1. Python 检查
if ! python --version >/dev/null 2>&1; then
    echo "[ERROR] 需要 Python 3.8+"
    exit 1
fi
echo "[OK] Python $(python --version 2>&1 | cut -d' ' -f2)"

# 2. Rich 库（可选，HUD 增强版需要）
if python -c "import rich" 2>/dev/null; then
    echo "[OK] Rich 库已安装"
else
    echo "[INFO] 安装 Rich 库（HUD 增强版需要）..."
    pip install rich -q 2>/dev/null && echo "[OK] Rich 库安装成功" || echo "[WARN] Rich 安装失败，HUD 将使用基础版"
fi

# 3. 注册 Stop Hook
if [ -f "$SETTINGS_FILE" ]; then
    python -c "
import json, sys
try:
    with open('$SETTINGS_FILE', encoding='utf-8') as f:
        s = json.load(f)
except:
    print('[WARN] 无法读取 settings.json')
    sys.exit(0)

hooks = s.setdefault('hooks', {})
stop = hooks.setdefault('Stop', [])
exists = any('dev-harness' in json.dumps(h) for h in stop)
if not exists:
    stop.append({
        'matcher': '',
        'hooks': [{
            'type': 'command',
            'command': 'python $PLUGIN_DIR/hooks/stop-hook.py',
            'timeout': 5000
        }]
    })
    with open('$SETTINGS_FILE', 'w', encoding='utf-8') as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    print('[OK] Stop Hook 已注册')
else:
    print('[OK] Stop Hook 已存在')
" 2>/dev/null
else
    echo "[WARN] settings.json 不存在，跳过 Hook 注册"
fi

# 4. 运行评测
echo ""
echo "运行安装验证..."
python "$PLUGIN_DIR/eval/eval-runner.py" run-all 2>/dev/null
EVAL_EXIT=$?

echo ""
echo "=========================="
if [ $EVAL_EXIT -eq 0 ]; then
    echo "  安装成功!"
else
    echo "  安装完成（部分测试可能未通过）"
fi
echo "=========================="
echo ""
echo "使用方式:"
echo "  1. 在任何项目中输入 /dev 开始开发"
echo "  2. 自动循环模式: /dev --auto-loop"
echo "  3. 查看 HUD: python $PLUGIN_DIR/scripts/harness.py hud --watch --rich"
echo "  4. 项目配置（可选）: 创建 .claude/dev-config.yml"
echo ""
