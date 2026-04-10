#!/usr/bin/env python3
"""SessionStart Hook: 检测 venv 是否就绪, 未就绪时引导用户运行 setup.sh

v3.3.0+: 从 bash 脚本 (session-init.sh) 迁移到 python, 避免 Windows 下
Cursor/WSL bash 处理 Windows 路径的反斜杠/路径格式问题。

优先级: CLAUDE_PLUGIN_ROOT > CURSOR_PLUGIN_ROOT > 脚本自定位
"""
import os
import sys
from pathlib import Path


def resolve_plugin_root() -> Path:
    for var in ("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT"):
        val = os.environ.get(var)
        if val:
            return Path(val)
    return Path(__file__).resolve().parent.parent


def venv_ready(plugin_root: Path) -> bool:
    """检查插件自带 venv 是否就绪 (Windows 或 POSIX 任一路径存在即可)"""
    return (
        (plugin_root / ".venv" / "Scripts" / "python.exe").exists()
        or (plugin_root / ".venv" / "bin" / "python").exists()
    )


def main():
    plugin_root = resolve_plugin_root()
    if venv_ready(plugin_root):
        # venv 就绪, 静默通过
        sys.exit(0)

    # venv 不存在, 输出引导信息 (注入到 Claude/Cursor 上下文)
    print(
        "[Dev Harness] 插件环境未初始化。请运行以下命令完成安装：\n"
        "\n"
        "```bash\n"
        'bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup.sh"\n'
        "```\n"
        "\n"
        "这会创建插件内置 venv 并安装依赖（不影响你的全局 Python 环境）。\n"
        "初始化完成后, 输入 /dev 即可开始使用。"
    )


if __name__ == "__main__":
    main()
