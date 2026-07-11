#!/usr/bin/env python3
"""SessionStart Hook: 体检插件环境, 未就绪时指路 /dev-harness:setup

v3.3.0+: 从 bash 脚本迁到 python, 规避 Windows 下 Cursor/WSL bash 处理
反斜杠路径的问题。
v4.5+: venv 查找优先级与 dh-python.sh 对齐（CLAUDE_PLUGIN_DATA 优先）；检测维度
从「venv 目录存在」升级到「venv python 可执行 + filelock 真能 import」，并在引导
文案里说明具体缺什么，指向 /dev-harness:setup（doctor + fix 统一入口）。

契约：必须 <1 秒、无网络、fail-safe（任何异常都 exit 0，绝不阻断会话启动）。
优先级: CLAUDE_PLUGIN_ROOT > CURSOR_PLUGIN_ROOT > 脚本自定位
"""
import os
import subprocess
import sys
from pathlib import Path

# Windows 默认 GBK 编码，强制 stdout 走 UTF-8：既防中文 UnicodeEncodeError 崩溃，
# 也保证注入 Claude/Cursor 上下文的引导文案不乱码（CLAUDE.md 铁律）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


def resolve_plugin_root() -> Path:
    for var in ("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT"):
        val = os.environ.get(var)
        if val:
            return Path(val)
    return Path(__file__).resolve().parent.parent


def find_venv_python(plugin_root: Path):
    """在 venv 候选目录里找第一个存在的 python，优先级同 dh-python.sh（DATA → ROOT）。"""
    candidates = []
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    if data:
        candidates.append(Path(data) / ".venv")
    candidates.append(plugin_root / ".venv")
    for vdir in candidates:
        for rel in ("Scripts/python.exe", "bin/python", "bin/python3"):
            p = vdir / rel
            if p.exists():
                return p
    return None


def filelock_importable(py: Path) -> bool:
    """真跑一次 import filelock（不是看目录），带超时兜底。venv 存在时才调用，单次开销 <0.5s。"""
    try:
        r = subprocess.run(
            [str(py), "-c", "import filelock"],
            capture_output=True, timeout=5,
        )
        return r.returncode == 0
    except Exception:
        return False


def main():
    plugin_root = resolve_plugin_root()
    py = find_venv_python(plugin_root)

    missing = []
    if py is None:
        missing.append("venv 环境")
    elif not filelock_importable(py):
        missing.append("filelock 依赖")

    if not missing:
        # 环境就绪, 静默通过
        return

    detail = "、".join(missing)
    print(
        f"[Dev Harness] 插件环境未初始化（检测到缺：{detail}）。\n"
        f"\n"
        f"运行 `/dev-harness:setup` 完成体检并自动安装（doctor 只读体检，"
        f"确认后再 --fix 修复），或直接执行：\n"
        f"\n"
        f"```bash\n"
        f'bash "${{CLAUDE_PLUGIN_ROOT}}/scripts/setup.sh"\n'
        f"```\n"
        f"\n"
        f"这会在持久目录创建插件 venv 并装依赖（不影响你的全局 Python）。"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # fail-safe: SessionStart hook 绝不因异常阻断会话启动
        pass
    sys.exit(0)
