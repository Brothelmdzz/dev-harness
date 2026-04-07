#!/bin/bash
# Dev Harness 安装验证 + hook wrapper 部署
# 1. 检查依赖  2. 验证文件完整性  3. 部署 stop-hook wrapper  4. 运行评测

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=========================="
echo "  Dev Harness v3.1 Setup"
echo "=========================="
echo ""

# 1. Python 检查
if python --version >/dev/null 2>&1; then
    echo "[OK] Python $(python --version 2>&1 | cut -d' ' -f2)"
elif python3 --version >/dev/null 2>&1; then
    echo "[OK] Python3 $(python3 --version 2>&1 | cut -d' ' -f2)"
else
    echo "[ERROR] 需要 Python 3.8+"
    echo "  安装: https://www.python.org/downloads/"
    exit 1
fi

# 2. Rich 库（可选，Rich HUD 需要）
if python -c "import rich" 2>/dev/null || python3 -c "import rich" 2>/dev/null; then
    echo "[OK] Rich 库已安装"
else
    echo "[INFO] 安装 Rich 库（HUD 增强版需要）..."
    pip install rich -q 2>/dev/null && echo "[OK] Rich 安装成功" || echo "[WARN] Rich 安装失败，HUD 将使用基础版"
fi

# 2b. filelock（多 Agent 并行状态保护）
if python -c "import filelock" 2>/dev/null; then
    echo "[OK] filelock 已安装"
else
    echo "[INFO] 安装 filelock（多 Agent 并行需要）..."
    pip install filelock -q 2>/dev/null && echo "[OK] filelock 安装成功" || echo "[ERROR] filelock 安装失败，多 Agent 并行将无法工作"
fi

# 3. 验证插件文件完整性
REQUIRED_FILES=(
    "hooks/stop-hook.py"
    "hooks/hooks.json"
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

# 4. 部署 stop-hook wrapper（解决版本升级后路径失效）
CLAUDE_DIR="$HOME/.claude"
HOOKS_DIR="$CLAUDE_DIR/hooks"
WRAPPER_SRC="$PLUGIN_DIR/hooks/stop-hook-wrapper.py"
WRAPPER_DST="$HOOKS_DIR/dev-harness-stop.py"
SETTINGS="$CLAUDE_DIR/settings.json"

# Windows 路径兼容 (Git Bash/MSYS/Cygwin)
if [[ "$OS" == "Windows_NT" || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
    CLAUDE_DIR="$(cygpath -u "$USERPROFILE")/.claude"
    HOOKS_DIR="$CLAUDE_DIR/hooks"
    WRAPPER_DST="$HOOKS_DIR/dev-harness-stop.py"
    SETTINGS="$CLAUDE_DIR/settings.json"
fi

mkdir -p "$HOOKS_DIR"

if [ -f "$WRAPPER_SRC" ]; then
    cp "$WRAPPER_SRC" "$WRAPPER_DST"
    echo "[OK] stop-hook wrapper → $WRAPPER_DST"

    # 更新 settings.json：将硬编码版本路径替换为 wrapper 路径
    if [ -f "$SETTINGS" ]; then
        # 检查是否存在旧的硬编码路径（含版本号的 stop-hook.py）
        if grep -q "dev-harness-marketplace/dev-harness/[0-9].*stop-hook.py" "$SETTINGS" 2>/dev/null; then
            # 构建平台对应的 wrapper 路径
            if [[ "$OS" == "Windows_NT" || "$OSTYPE" == msys* || "$OSTYPE" == cygwin* ]]; then
                WRAPPER_PATH_ESCAPED="$(cygpath -w "$WRAPPER_DST" | sed 's/\\/\\\\/g')"
            else
                WRAPPER_PATH_ESCAPED="$WRAPPER_DST"
            fi
            python -c "
import json, re, sys
with open('$SETTINGS', 'r', encoding='utf-8') as f:
    text = f.read()
# 替换含版本号的硬编码路径为 wrapper 路径
text = re.sub(
    r'python\s+[^\"]*/dev-harness-marketplace/dev-harness/[^\"]*stop-hook\.py',
    'python $WRAPPER_PATH_ESCAPED',
    text
)
with open('$SETTINGS', 'w', encoding='utf-8') as f:
    f.write(text)
" 2>/dev/null && echo "[OK] settings.json hook 路径已更新" || echo "[WARN] settings.json 自动更新失败，请手动检查"
        else
            echo "[OK] settings.json hook 路径无需更新"
        fi
    fi
else
    echo "[WARN] stop-hook-wrapper.py 未找到，跳过 wrapper 部署"
fi

# 5. 运行评测
echo ""
echo "运行安装验证..."
python "$PLUGIN_DIR/eval/eval-runner.py" run-all 2>/dev/null
EVAL_EXIT=$?

echo ""
echo "=========================="
if [ $MISSING -eq 0 ] && [ $EVAL_EXIT -eq 0 ]; then
    echo "  安装成功!"
else
    echo "  安装完成（$MISSING 个文件缺失，eval exit=$EVAL_EXIT）"
fi
echo "=========================="
echo ""
echo "使用方式:"
echo "  1. 在任何项目中输入 /dev 开始开发"
echo "  2. 自动循环模式: /dev --auto-loop"
echo "  3. Web HUD: python \"\${CLAUDE_PLUGIN_ROOT}/scripts/harness.py\" web-hud"
echo "  4. 项目配置（可选）: 创建 .claude/dev-config.yml"
echo ""
echo "注意: Stop Hook 通过 wrapper 部署，版本升级后自动追踪，无需手动配置。"
echo ""
