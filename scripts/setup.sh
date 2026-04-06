#!/bin/bash
# Dev Harness 安装验证脚本
# 插件 hook 已通过 hooks/hooks.json 自动注册，无需手动配置 settings.json

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

# 4. 运行评测
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
echo "注意: Stop Hook 已通过 hooks/hooks.json 自动注册，无需手动配置。"
echo ""
