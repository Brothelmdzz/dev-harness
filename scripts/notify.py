"""Dev Harness 通知系统 — pipeline 完成/失败时发桌面通知 + 可选飞书 Webhook"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ==================== 配置 ====================

def _find_project_root():
    """向上查找 .git 目录定位项目根"""
    env = os.environ.get("DH_PROJECT")
    if env:
        return Path(env).resolve()
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()


def _load_dev_config():
    """读取 .claude/dev-config.yml（简易解析，不依赖 PyYAML）"""
    config_file = _find_project_root() / ".claude" / "dev-config.yml"
    if not config_file.exists():
        return {}
    try:
        text = config_file.read_text(encoding="utf-8")
        return _parse_simple_yaml(text)
    except Exception:
        return {}


def _parse_simple_yaml(text):
    """极简 YAML 解析器 — 仅支持顶层和一层嵌套的 key: value"""
    result = {}
    current_section = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # 判断缩进层级
        indent = len(line) - len(line.lstrip())
        if indent == 0 and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip().strip('"').strip("'")
            if val:
                result[key.strip()] = val
            else:
                current_section = key.strip()
                result[current_section] = {}
        elif indent > 0 and current_section and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip().strip('"').strip("'")
            result[current_section][key.strip()] = val
    return result


# ==================== 桌面通知 ====================

LEVEL_ICONS = {
    "info": "ℹ️",
    "success": "✅",
    "warning": "⚠️",
    "error": "❌",
}


def send(title, message, level="info"):
    """发送桌面通知，自动检测操作系统"""
    icon = LEVEL_ICONS.get(level, "")
    full_title = f"{icon} {title}" if icon else title

    if sys.platform == "win32":
        _send_windows(full_title, message)
    elif sys.platform == "darwin":
        _send_macos(full_title, message)
    else:
        _send_linux(full_title, message)


def _send_windows(title, message):
    """Windows 桌面通知：优先 BurntToast，fallback 到 balloon tip"""
    # 尝试 BurntToast（需安装 PowerShell 模块）
    ps_burnt = (
        f'try {{ Import-Module BurntToast -ErrorAction Stop; '
        f'New-BurntToastNotification -Text "{_ps_escape(title)}", "{_ps_escape(message)}" }} '
        f'catch {{ exit 1 }}'
    )
    ret = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_burnt],
        capture_output=True, timeout=10,
    )
    if ret.returncode == 0:
        return

    # Fallback: 使用 .NET balloon tip（无需额外模块）
    ps_balloon = (
        f'Add-Type -AssemblyName System.Windows.Forms; '
        f'$n = New-Object System.Windows.Forms.NotifyIcon; '
        f'$n.Icon = [System.Drawing.SystemIcons]::Information; '
        f'$n.BalloonTipTitle = "{_ps_escape(title)}"; '
        f'$n.BalloonTipText = "{_ps_escape(message)}"; '
        f'$n.Visible = $true; '
        f'$n.ShowBalloonTip(5000); '
        f'Start-Sleep -Seconds 6; '
        f'$n.Dispose()'
    )
    subprocess.Popen(
        ["powershell", "-NoProfile", "-Command", ps_balloon],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _ps_escape(s):
    """转义 PowerShell 双引号字符串中的危险字符"""
    return (s.replace('`', '``').replace('"', '`"').replace('$', '`$')
             .replace('\n', ' ').replace('\r', ' ').replace('\0', ''))


def _applescript_escape(s):
    """转义 AppleScript 字符串中的反斜杠和双引号"""
    return s.replace('\\', '\\\\').replace('"', '\\"')

def _send_macos(title, message):
    """macOS 桌面通知"""
    safe_title = _applescript_escape(title)
    safe_message = _applescript_escape(message)
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)


def _send_linux(title, message):
    """Linux 桌面通知"""
    subprocess.run(["notify-send", "--", title, message], capture_output=True, timeout=10)


# ==================== 飞书 Webhook ====================

def send_lark(webhook_url, title, message):
    """发送飞书 Bot Webhook 通知（富文本卡片）"""
    if not webhook_url:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": message,
                }
            ],
        },
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result.get("StatusCode") == 0 or result.get("code") == 0
    except (URLError, OSError, json.JSONDecodeError) as e:
        print(f"飞书通知失败: {e}", file=sys.stderr)
        return False


def send_lark_from_config(title, message):
    """从项目配置读取 webhook URL 并发送飞书通知"""
    config = _load_dev_config()
    notify_cfg = config.get("notify", {})
    webhook_url = notify_cfg.get("lark_webhook", "") if isinstance(notify_cfg, dict) else ""
    if webhook_url:
        return send_lark(webhook_url, title, message)
    return False


# ==================== Pipeline 集成 ====================

def notify_pipeline_result(state):
    """根据 pipeline 状态发送完成/失败通知 — 供 harness.py 调用"""
    if not state:
        return

    task = state.get("task", {})
    task_name = task.get("name", "未知任务")
    pipeline = state.get("pipeline", [])
    metrics = state.get("metrics", {})

    done = [s for s in pipeline if s["status"] == "DONE"]
    failed = [s for s in pipeline if s["status"] == "FAILED"]
    total = [s for s in pipeline if s["status"] != "SKIP"]

    # 判定整体状态
    if failed:
        level = "error"
        title = f"Pipeline 失败 — {task_name}"
        failed_names = ", ".join(s["name"] for s in failed)
        message = (
            f"失败阶段: {failed_names}\n"
            f"进度: {len(done)}/{len(total)}\n"
            f"错误计数: {metrics.get('total_errors', 0)}"
        )
    else:
        all_done = all(s["status"] in ("DONE", "SKIP") for s in pipeline)
        if not all_done:
            return  # 还在运行中，不发通知

        level = "success"
        title = f"Pipeline 完成 — {task_name}"
        message = (
            f"全部 {len(done)} 个阶段完成\n"
            f"自动修复: {metrics.get('auto_fixed', 0)} 次\n"
            f"自动续跑: {metrics.get('auto_continues', 0)} 次"
        )

    send(title, message, level)
    send_lark_from_config(title, message)


# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Dev Harness 通知系统")
    parser.add_argument("--title", required=True, help="通知标题")
    parser.add_argument("--message", required=True, help="通知内容")
    parser.add_argument("--level", default="info", choices=["info", "success", "warning", "error"],
                        help="通知级别（默认 info）")
    parser.add_argument("--lark", action="store_true", help="同时发送飞书通知")
    args = parser.parse_args()

    send(args.title, args.message, args.level)

    if args.lark:
        ok = send_lark_from_config(args.title, args.message)
        if not ok:
            print("飞书通知未发送（未配置 webhook 或发送失败）", file=sys.stderr)


if __name__ == "__main__":
    main()
