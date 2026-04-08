#!/bin/bash
# Dev Harness 安装验证
# 只做检测和报告，不修改用户全局环境

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# 从 plugin.json 动态读取版本号
VERSION=$(python -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$PLUGIN_DIR/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")

echo "=========================="
echo "  Dev Harness v${VERSION} Setup"
echo "=========================="
echo ""

# ==================== 1. 依赖检查（只检测，不自动安装） ====================

PYTHON_CMD=""
if python --version >/dev/null 2>&1; then
    PYTHON_CMD="python"
    echo "[OK] Python $(python --version 2>&1 | cut -d' ' -f2)"
elif python3 --version >/dev/null 2>&1; then
    PYTHON_CMD="python3"
    echo "[OK] Python3 $(python3 --version 2>&1 | cut -d' ' -f2)"
else
    echo "[ERROR] 需要 Python 3.8+"
    echo "  安装: https://www.python.org/downloads/"
    exit 1
fi

# filelock（可选，多 Agent 并行推荐）
if $PYTHON_CMD -c "import filelock" 2>/dev/null; then
    echo "[OK] filelock 已安装"
else
    echo "[INFO] filelock 未安装（可选，多 Agent 并行时推荐）"
    echo "  安装: pip install filelock（建议在 venv 中安装）"
fi

# Rich（可选，终端 HUD 增强版）
if $PYTHON_CMD -c "import rich" 2>/dev/null; then
    echo "[OK] Rich 已安装"
else
    echo "[INFO] Rich 未安装（可选，终端 HUD 增强版需要）"
    echo "  安装: pip install rich"
fi

# ==================== 2. 文件完整性 ====================

echo ""
REQUIRED_FILES=(
    "hooks/stop-hook.py"
    "hooks/hooks.json"
    "hooks/plan-watcher.py"
    "scripts/harness.py"
    "scripts/skill-resolver.py"
    "scripts/detect-stack.sh"
    "skills/dev/SKILL.md"
    ".claude-plugin/plugin.json"
)

MISSING=0
for f in "${REQUIRED_FILES[@]}"; do
    if [ -f "$PLUGIN_DIR/$f" ]; then
        echo "[OK] $f"
    else
        echo "[MISS] $f"
        MISSING=$((MISSING + 1))
    fi
done

# ==================== 3. Hook 注册状态检测（只读检查） ====================

echo ""
CLAUDE_DIR="$HOME/.claude"
if [[ "$OS" == "Windows_NT" || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    CLAUDE_DIR="$(cygpath -u "$USERPROFILE")/.claude"
fi
SETTINGS="$CLAUDE_DIR/settings.json"

if [ -f "$SETTINGS" ]; then
    # 检查 Stop hook 是否已注册
    if grep -q "stop-hook\|dev-harness-stop" "$SETTINGS" 2>/dev/null; then
        echo "[OK] Stop Hook 已注册"
    else
        echo "[WARN] Stop Hook 未在 settings.json 中注册"
        echo "  插件的 hooks/hooks.json 会在新会话启动时自动注册"
        echo "  如果不生效，重启 Claude Code 会话"
    fi

    # 检查是否有旧版硬编码路径
    if grep -q "dev-harness-marketplace/dev-harness/[0-9].*stop-hook\.py" "$SETTINGS" 2>/dev/null; then
        echo "[WARN] settings.json 中有旧版硬编码路径（含版本号）"
        echo "  建议运行: bash \"${PLUGIN_DIR}/scripts/fix-hook-path.sh\""
        echo "  或手动将 settings.json 中的 stop-hook 路径改为:"
        echo "    python \"$CLAUDE_DIR/hooks/dev-harness-stop.py\""
    fi
else
    echo "[INFO] 未找到 settings.json（$SETTINGS）"
fi

# ==================== 4. 评测（可选） ====================

if [[ "$1" == "--with-eval" ]]; then
    echo ""
    echo "运行安装验证评测..."
    $PYTHON_CMD "$PLUGIN_DIR/eval/eval-runner.py" run-all 2>/dev/null
    EVAL_EXIT=$?
else
    EVAL_EXIT=0
fi

# ==================== 结果 ====================

echo ""
echo "=========================="
if [ $MISSING -eq 0 ] && [ $EVAL_EXIT -eq 0 ]; then
    echo "  检查通过!"
else
    echo "  检查完成（$MISSING 个文件缺失）"
fi
echo "=========================="
echo ""
echo "使用方式:"
echo "  1. 在任何项目中输入 /dev 开始开发"
echo "  2. Web HUD: python \"\${CLAUDE_PLUGIN_ROOT}/scripts/harness.py\" web-hud"
echo "  3. 运行评测: bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh\" --with-eval"
echo ""
echo "注意: Stop Hook 通过 hooks/hooks.json 自动注册，无需手动配置。"
echo "      如遇版本升级后路径失效，运行 fix-hook-path.sh 修复。"
echo ""
