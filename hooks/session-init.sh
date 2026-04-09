#!/bin/bash
# SessionStart Hook: 检测 venv 是否就绪，未就绪时提示用户运行 setup
# 输出到 stdout 的内容会被注入到 Claude 的上下文中

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
VENV_DIR="$PLUGIN_ROOT/.venv"

# 检查 venv 是否存在
if [ -f "$VENV_DIR/bin/python" ] || [ -f "$VENV_DIR/Scripts/python.exe" ]; then
    # venv 就绪，静默通过
    exit 0
fi

# venv 不存在，输出引导信息（注入到 Claude 上下文）
cat << 'EOF'
[Dev Harness] 插件环境未初始化。请运行以下命令完成安装：

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"
```

这会创建插件内置 venv 并安装依赖（不影响你的全局 Python 环境）。
初始化完成后，输入 /dev 即可开始使用。
EOF
