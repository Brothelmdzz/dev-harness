#!/usr/bin/env python
"""dev-harness stop-hook 的稳定入口。

部署到 ~/.claude/hooks/dev-harness-stop.py，从 installed_plugins.json
动态查找实际安装路径，避免版本升级后 settings.json 里的路径失效。

由 scripts/setup.sh 自动部署。
"""
import json, os, subprocess, sys

PLUGINS_FILE = os.path.join(
    os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json"
)
PLUGIN_KEY = "dev-harness@dev-harness-marketplace"


def main():
    try:
        with open(PLUGINS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get("plugins", {}).get(PLUGIN_KEY, [])
        if not entries:
            sys.exit(0)
        install_path = entries[0]["installPath"]
        hook_script = os.path.join(install_path, "hooks", "stop-hook.py")
        if not os.path.isfile(hook_script):
            sys.exit(0)
    except Exception:
        sys.exit(0)

    # 透传 stdin 和参数
    result = subprocess.run(
        [sys.executable, hook_script] + sys.argv[1:],
        input=sys.stdin.buffer.read() if not sys.stdin.isatty() else None,
        capture_output=False,
    )
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
