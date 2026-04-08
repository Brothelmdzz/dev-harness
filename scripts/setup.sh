#!/bin/bash
# Dev Harness 安装验证 + venv 环境初始化
# 所有依赖安装到插件内置 .venv，不污染用户全局环境

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$PLUGIN_DIR/.venv"

# 检测系统 python
PYTHON_CMD=""
if command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "[ERROR] 需要 Python 3.8+"
    echo "  安装: https://www.python.org/downloads/"
    exit 1
fi

# 从 plugin.json 动态读取版本号
VERSION=$($PYTHON_CMD -c "import json,sys; print(json.load(open(sys.argv[1]))['version'])" "$PLUGIN_DIR/.claude-plugin/plugin.json" 2>/dev/null || echo "unknown")

echo "=========================="
echo "  Dev Harness v${VERSION} Setup"
echo "=========================="
echo ""
echo "[OK] Python $($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)"

# ==================== 1. 创建插件内置 venv ====================

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" -o -f "$VENV_DIR/Scripts/python.exe" ]; then
    echo "[OK] venv 已存在: $VENV_DIR"
else
    echo "[INFO] 创建插件 venv..."
    $PYTHON_CMD -m venv "$VENV_DIR" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "[OK] venv 创建成功"
    else
        echo "[WARN] venv 创建失败，将使用系统 Python（fallback 模式）"
    fi
fi

# 找到 venv 的 pip
VENV_PIP=""
if [ -f "$VENV_DIR/bin/pip" ]; then
    VENV_PIP="$VENV_DIR/bin/pip"
elif [ -f "$VENV_DIR/Scripts/pip.exe" ]; then
    VENV_PIP="$VENV_DIR/Scripts/pip.exe"
fi

# ==================== 2. 安装依赖到 venv ====================

if [ -n "$VENV_PIP" ]; then
    echo "[INFO] 安装依赖到 venv..."
    "$VENV_PIP" install filelock rich -q 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "[OK] filelock + rich 已安装到 venv"
    else
        echo "[WARN] 部分依赖安装失败"
    fi
else
    echo "[WARN] 无法找到 venv pip，跳过依赖安装"
fi

# ==================== 3. 验证 venv python 可用 ====================

DH_PYTHON="$PLUGIN_DIR/scripts/dh-python.sh"
echo ""
VENV_PYTHON_VER=$(bash "$DH_PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>/dev/null)
if [ -n "$VENV_PYTHON_VER" ]; then
    echo "[OK] dh-python → Python $VENV_PYTHON_VER"
else
    echo "[WARN] dh-python 验证失败，将 fallback 到系统 Python"
fi

# 验证核心依赖
bash "$DH_PYTHON" -c "import filelock; print('[OK] filelock 可用')" 2>/dev/null || echo "[WARN] filelock 不可用（多 Agent 并行将降级）"
bash "$DH_PYTHON" -c "import rich; print('[OK] rich 可用')" 2>/dev/null || echo "[INFO] rich 不可用（终端 HUD 将使用基础版）"

# ==================== 4. 文件完整性 ====================

echo ""
REQUIRED_FILES=(
    "hooks/stop-hook.py"
    "hooks/hooks.json"
    "hooks/plan-watcher.py"
    "scripts/harness.py"
    "scripts/skill-resolver.py"
    "scripts/detect-stack.sh"
    "scripts/dh-python.sh"
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

# ==================== 5. Hook 注册状态（只读检查） ====================

echo ""
CLAUDE_DIR="$HOME/.claude"
if [[ "$OS" == "Windows_NT" || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    CLAUDE_DIR="$(cygpath -u "$USERPROFILE")/.claude"
fi
SETTINGS="$CLAUDE_DIR/settings.json"

if [ -f "$SETTINGS" ]; then
    if grep -q "stop-hook\|dev-harness-stop" "$SETTINGS" 2>/dev/null; then
        echo "[OK] Stop Hook 已注册"
    else
        echo "[INFO] Stop Hook 将在新会话启动时自动注册（通过 hooks/hooks.json）"
    fi
fi

# ==================== 6. 评测（可选） ====================

if [[ "$1" == "--with-eval" ]]; then
    echo ""
    echo "运行评测..."
    bash "$DH_PYTHON" "$PLUGIN_DIR/eval/eval-runner.py" run-all 2>/dev/null
fi

# ==================== 结果 ====================

echo ""
echo "=========================="
if [ $MISSING -eq 0 ]; then
    echo "  安装成功!"
else
    echo "  安装完成（$MISSING 个文件缺失）"
fi
echo "=========================="
echo ""
echo "环境: $VENV_DIR"
echo "Python: $(bash "$DH_PYTHON" --version 2>&1)"
echo ""
echo "使用方式:"
echo "  1. 在任何项目中输入 /dev 开始开发"
echo "  2. Web HUD: bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh\" \"\${CLAUDE_PLUGIN_ROOT}/scripts/harness.py\" web-hud"
echo "  3. 运行评测: bash \"\${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh\" --with-eval"
echo ""
