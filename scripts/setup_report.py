#!/usr/bin/env python3
"""setup_report.py — dev-harness 插件级安装体检 + 修复（doctor / fix 双模式）

设计目标（对齐 codex-companion 的 buildSetupReport 范式）：
  - 结构化输出 {ready, host, checks[], actionsTaken[], nextSteps[]}
  - 默认纯只读 doctor；--fix 才执行安装动作；幂等（重复跑无副作用）
  - 收编四个孤儿脚本：setup.sh（venv/依赖/文件完整性）、fix-hook-path.sh
    （旧 Stop hook 路径修复 → 现代做法是移除）、find-dh-home.sh（PLUGIN_ROOT
    兜底自举）、session-init.py 的 venv 检测口径

用法：
  python setup_report.py            # 只读体检，人类可读三段式
  python setup_report.py --json     # 只读体检，机器可读 JSON
  python setup_report.py --fix      # 执行修复动作后再体检
  python setup_report.py --fix --json

只用标准库，不引入新三方依赖。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Windows cmd 默认 GBK 编码，强制 stdout/stderr 走 UTF-8 避免中文/特殊字符报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass  # Python < 3.7 或不支持 reconfigure 的环境，让 print 自己应付

# /goal 功能的 Claude Code 版本门槛
MIN_CLAUDE_VERSION = (2, 1, 139)

# 9 个必需文件（清单从 setup.sh 抄，作为「安装器是否裁剪组件」的探针）
REQUIRED_FILES = [
    "hooks/stop-hook.py",
    "hooks/hooks.json",
    "hooks/plan-watcher.py",
    "scripts/harness.py",
    "scripts/skill-resolver.py",
    "scripts/detect-stack.sh",
    "scripts/dh-python.sh",
    "skills/dev/SKILL.md",
    ".claude-plugin/plugin.json",
]

# ready 布尔只由这几项裁决：任一 fail 即 not ready。venv 缺失可被系统 python 兜底、
# filelock 只影响并行模式（串行不需要它）——两者都不入此列，否则无 venv 用户 ready 会
# 恒为 False，被反复劝修一个其实不影响串行使用的可选依赖。
CRITICAL_IDS = {"python_exec", "required_files", "plugin_root"}


# ==================== 通用子进程封装 ====================

def run(cmd, timeout=20):
    """跑一条命令，返回 (returncode, stdout, stderr)，异常统一收敛为 rc=-1。

    强制 utf-8 + errors=replace 解码：不用 text=True（会走 Windows GBK 本地编码，
    子命令输出非 GBK 字节，如 UTF-16 BOM 0xff，会让 subprocess 读取线程崩溃）。
    """
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except (subprocess.TimeoutExpired, OSError) as e:
        return -1, "", str(e)


def run_py(py, code, timeout=15):
    """用指定 python 跑一段内联代码。"""
    return run([str(py), "-c", code], timeout=timeout)


# ==================== 环境解析 ====================

def detect_host():
    """识别当前运行的 harness。强信号优先，env 无标识时退回 unknown。

    注意：CODEX_COMPANION_* 是 codex-companion 插件在 Claude Code 内注入的伪信号，
    不代表运行在 Codex harness 上，故 codex 判定排除 COMPANION 前缀。
    裸终端直跑（无任何 env）→ unknown，host 专属检测项自行降级为 skip。
    """
    if os.environ.get("CURSOR_PLUGIN_ROOT"):
        return "cursor"
    if any(os.environ.get(k) for k in
           ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PLUGIN_ROOT")):
        return "claude-code"
    if any(k.startswith("CODEX_") and not k.startswith("CODEX_COMPANION") for k in os.environ):
        return "codex"
    return "unknown"


def find_dh_home():
    """find-dh-home.sh 的 Python 移植：env 全空时按已知安装路径搜索自举。"""
    home = Path.home()
    bases = [
        home / ".claude" / "plugins" / "cache" / "dev-harness-marketplace" / "dev-harness",
        home / ".claude" / "plugins" / "cache" / "dev-harness-local" / "dev-harness",
        home / ".claude" / "plugins" / "dev-harness",
    ]
    for base in bases:
        if base.is_dir():
            for sub in sorted(base.iterdir()):
                if (sub / "scripts" / "harness.py").exists():
                    return sub
    # 递归兜底：扫 plugins/cache 找 dev-harness 下的 harness.py
    cache = home / ".claude" / "plugins" / "cache"
    if cache.is_dir():
        for p in cache.rglob("scripts/harness.py"):
            if "dev-harness" in str(p):
                return p.parent.parent
    return None


def resolve_plugin_root():
    """解析插件根目录，返回 (Path, source)。

    优先级：CLAUDE_PLUGIN_ROOT → CURSOR_PLUGIN_ROOT → PLUGIN_ROOT（任一非空且含
    scripts/harness.py）→ 脚本自定位（最可靠的自举）→ find-dh-home 搜索。
    """
    for var in ("CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT", "PLUGIN_ROOT"):
        val = os.environ.get(var)
        if val and (Path(val) / "scripts" / "harness.py").exists():
            return Path(val), var
    self_root = Path(__file__).resolve().parent.parent
    if (self_root / "scripts" / "harness.py").exists():
        return self_root, "self"
    found = find_dh_home()
    if found:
        return found, "search"
    return self_root, "self-unverified"


def claude_dir():
    return Path.home() / ".claude"


def codex_config_path():
    p = Path.home() / ".codex" / "config.toml"
    if not p.exists():
        up = os.environ.get("USERPROFILE")
        if up:
            alt = Path(up) / ".codex" / "config.toml"
            if alt.exists():
                return alt
    return p


# ==================== 上下文 ====================

class Ctx:
    """一次体检的共享状态。system_py / venv_py 供后续检测项复用，避免重复探测。"""

    def __init__(self, plugin_root, root_source, host, fix):
        self.plugin_root = plugin_root
        self.root_source = root_source
        self.host = host
        self.fix = fix
        self.actions = []          # actionsTaken：仅 --fix 下填充
        self.data_dir = os.environ.get("CLAUDE_PLUGIN_DATA")
        self.system_py = None      # 可执行的系统 python（check_python_exec 填充）
        self.venv_py = None        # 可用的 venv python（check_venv 填充）

    def candidate_venvs(self):
        """venv 候选目录，顺序同 dh-python.sh：DATA 优先，其次 ROOT。"""
        dirs = []
        if self.data_dir:
            dirs.append(Path(self.data_dir) / ".venv")
        dirs.append(self.plugin_root / ".venv")
        return dirs

    def fix_target_venv(self):
        """--fix 创建 venv 的目标目录：优先 CLAUDE_PLUGIN_DATA。"""
        if self.data_dir:
            return Path(self.data_dir) / ".venv", True
        return self.plugin_root / ".venv", False


def venv_python(venv_dir: Path):
    """返回 venv 里的 python 可执行路径（存在才返回），跨平台。"""
    if os.name == "nt":
        p = venv_dir / "Scripts" / "python.exe"
        return p if p.exists() else None
    for name in ("python", "python3"):
        p = venv_dir / "bin" / name
        if p.exists():
            return p
    return None


def find_venv_python(ctx: Ctx):
    """在候选目录里找第一个存在的 venv python。"""
    for d in ctx.candidate_venvs():
        py = venv_python(d)
        if py:
            return py, d
    return None, None


def system_python():
    """找到并验证一个真能执行的系统 python（不只 which，跑一次 print(1)）。"""
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if not exe:
            continue
        rc, out, _ = run_py(exe, "print(1)")
        if rc == 0 and out == "1":
            return exe
    return None


def _check(cid, label, status, detail="", fix_hint=""):
    return {"id": cid, "label": label, "status": status, "detail": detail, "fix_hint": fix_hint}


# ==================== 检测项：通用 ====================

def check_python_exec(ctx: Ctx):
    """python 可执行性——复用 build_report 已跑过的 system_python()（同一套执行验证逻辑，
    不用 which 判断，Windows 商店存根 exit 49 坑），不再对同一批候选二次 which+run。"""
    if ctx.system_py:
        _, ver, _ = run_py(ctx.system_py, "import sys;print('.'.join(map(str,sys.version_info[:3])))")
        name = Path(ctx.system_py).stem
        return _check("python_exec", "Python 可执行", "ok",
                      f"{name} → {ctx.system_py}（Python {ver or '?'}）")
    candidates = [n for n in ("python", "python3") if shutil.which(n)]
    if not candidates:
        return _check("python_exec", "Python 可执行", "fail",
                      "PATH 上未找到 python/python3",
                      "安装 Python 3.8+：https://www.python.org/downloads/")
    # which 命中但 system_python() 验证执行失败 → 典型 Windows 商店存根
    return _check("python_exec", "Python 可执行", "fail",
                  f"找到 {candidates} 但执行失败（疑似 Windows 商店存根，exit 49）",
                  "从 python.org 安装真实 Python，或在 设置>应用>应用执行别名 关闭 python 存根")


def check_venv(ctx: Ctx):
    """venv 产物二次校验：目录存在 ≠ python 能跑。缺失记 warn（dh-python.sh 有系统兜底）。"""
    py, vdir = find_venv_python(ctx)
    if not py:
        return _check("venv", "插件 venv", "warn",
                      "未找到 venv python（当前退回系统 python 运行）",
                      "运行 /dev-harness:setup --fix 创建 venv 并装依赖")
    rc, out, _ = run_py(py, "import sys;print('.'.join(map(str,sys.version_info[:3])))")
    if rc == 0 and out:
        ctx.venv_py = py
        return _check("venv", "插件 venv", "ok", f"venv python {out} @ {vdir}")
    return _check("venv", "插件 venv", "warn",
                  f"venv 目录存在但 python 无法执行 @ {vdir}",
                  "运行 /dev-harness:setup --fix 重建 venv")


def check_filelock(ctx: Ctx):
    """filelock 真实可导入（并行模式硬依赖），不是『pip 装了』而是『import 得动』。"""
    py = ctx.venv_py or ctx.system_py
    if not py:
        return _check("filelock", "filelock 可用", "skip", "无可用 python，跳过")
    rc, out, _ = run_py(py, "import filelock;print(getattr(filelock,'__version__','?'))")
    if rc == 0:
        return _check("filelock", "filelock 可用", "ok", f"filelock {out}")
    return _check("filelock", "filelock 可用", "warn",
                  "filelock 不可导入（多 Agent 并行将被 require_filelock 阻断）",
                  "运行 /dev-harness:setup --fix 安装 filelock")


def check_required_files(ctx: Ctx):
    """9 个必需文件完整性——探测安装器是否裁剪了未声明组件。"""
    missing = [f for f in REQUIRED_FILES if not (ctx.plugin_root / f).exists()]
    if not missing:
        return _check("required_files", "必需文件完整性", "ok",
                      f"{len(REQUIRED_FILES)}/{len(REQUIRED_FILES)} 齐全")
    return _check("required_files", "必需文件完整性", "fail",
                  f"缺失 {len(missing)} 个：{', '.join(missing)}",
                  "插件可能被安装器裁剪，重装插件或重新 clone")


def check_plugin_root(ctx: Ctx):
    """PLUGIN_ROOT 解析——非空且指向含 harness.py 的目录。"""
    if (ctx.plugin_root / "scripts" / "harness.py").exists():
        status = "warn" if ctx.root_source == "self-unverified" else "ok"
        detail = f"{ctx.plugin_root}（来源: {ctx.root_source}）"
        return _check("plugin_root", "PLUGIN_ROOT 解析", status, detail)
    return _check("plugin_root", "PLUGIN_ROOT 解析", "fail",
                  f"解析到 {ctx.plugin_root} 但无 scripts/harness.py",
                  "设置 CLAUDE_PLUGIN_ROOT 指向插件目录")


def check_codex_cli(ctx: Ctx):
    """codex cli 探测——复用 detect-codex.sh，只读退出码不重写。未就绪非失败（可选特性）。"""
    script = ctx.plugin_root / "scripts" / "detect-codex.sh"
    if not script.exists():
        return _check("codex_cli", "codex cli（跨厂商审查）", "skip", "detect-codex.sh 缺失")
    bash = shutil.which("bash")
    if not bash:
        return _check("codex_cli", "codex cli（跨厂商审查）", "skip", "无 bash，无法运行 detect-codex.sh")
    rc, _, _ = run(["bash", str(script)], timeout=5)
    if rc == 0:
        return _check("codex_cli", "codex cli（跨厂商审查）", "ok", "codex cli 就绪，可启用 Layer 2 对抗审查")
    return _check("codex_cli", "codex cli（跨厂商审查）", "skip",
                  "codex cli 未就绪（跨厂商审查将跳过，非必需）",
                  "如需 Layer 2：npm install -g @openai/codex 并配置 ~/.codex/config.toml")


# ==================== 检测项：Claude Code ====================

def _parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in m.groups()) if m else None


def check_claude_version(ctx: Ctx):
    """claude --version ≥ 2.1.139（/goal 门槛）。非 Claude Code 平台无此 CLI → skip。"""
    claude = shutil.which("claude")
    if not claude:
        return _check("claude_version", "Claude Code 版本", "skip", "未找到 claude CLI（非 Claude Code 平台可忽略）")
    rc, out, err = run([claude, "--version"])
    ver = _parse_version(out or err)
    if not ver:
        return _check("claude_version", "Claude Code 版本", "warn", f"无法解析版本：{out or err}")
    want = ".".join(map(str, MIN_CLAUDE_VERSION))
    if ver >= MIN_CLAUDE_VERSION:
        return _check("claude_version", "Claude Code 版本", "ok", f"{'.'.join(map(str,ver))} ≥ {want}")
    return _check("claude_version", "Claude Code 版本", "warn",
                  f"{'.'.join(map(str,ver))} < {want}，/goal 不可用",
                  f"升级 Claude Code 至 ≥ {want}")


def check_claude_hooks_enabled(ctx: Ctx):
    """settings.json / settings.local.json 无 disableAllHooks（/goal 与自研 stop-hook 共享前提）。"""
    if not shutil.which("claude"):
        return _check("claude_hooks", "Hook 未被全局禁用", "skip", "非 Claude Code 平台可忽略")
    offenders = []
    seen = False
    for name in ("settings.json", "settings.local.json"):
        p = claude_dir() / name
        if not p.exists():
            continue
        seen = True
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("disableAllHooks"):
            offenders.append(name)
    if not seen:
        return _check("claude_hooks", "Hook 未被全局禁用", "skip", "无 settings.json（全新环境）")
    if offenders:
        return _check("claude_hooks", "Hook 未被全局禁用", "warn",
                      f"disableAllHooks=true 于 {', '.join(offenders)}，/goal 与续跑防线将失效",
                      "从对应 settings 文件移除 disableAllHooks 字段")
    return _check("claude_hooks", "Hook 未被全局禁用", "ok", "未设置 disableAllHooks")


# ==================== 检测项：Codex ====================

def check_codex_goals(ctx: Ctx):
    """codex features 里 goals 状态。无 codex CLI → skip。

    `codex features list` 输出是「name stage effective」三列，只信最后一列 == "true"
    才算启用——裸子串匹配 "enabled"/"stable"/"true" 会把 "disabled"（含 "enabled" 子串）、
    "stable false"（含 "stable" 但实际未启用）误判为已启用，是假阳性。
    """
    codex = shutil.which("codex")
    if not codex:
        return _check("codex_goals", "Codex goals 特性", "skip", "未找到 codex CLI（非 Codex 平台可忽略）")
    rc, out, err = run([codex, "features", "list"], timeout=5)
    blob = out + "\n" + err
    if rc != 0 and not blob.strip():
        return _check("codex_goals", "Codex goals 特性", "skip", "codex features list 无输出（旧版可能无此子命令）")
    line = next((ln for ln in blob.splitlines() if "goal" in ln.lower()), "")
    if not line:
        return _check("codex_goals", "Codex goals 特性", "warn", "features 输出未见 goals 条目",
                      "确认 Codex 版本支持 goals 特性")
    cols = line.split()
    effective = cols[-1].lower() if cols else ""
    if effective == "true":
        return _check("codex_goals", "Codex goals 特性", "ok", line.strip())
    return _check("codex_goals", "Codex goals 特性", "warn", line.strip() or "goals 未启用",
                  "升级 Codex（goals v0.133.0+ 默认开）或在 config 开启")


def check_codex_hook_trust(ctx: Ctx):
    """~/.codex/config.toml [hooks.state] 是否有 dev-harness 条目。无则续跑防线在 Codex 静默失效。"""
    cfg = codex_config_path()
    if not cfg.exists():
        return _check("codex_hook_trust", "Codex hook 信任", "skip", "无 ~/.codex/config.toml（非 Codex 平台可忽略）")
    try:
        text = cfg.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return _check("codex_hook_trust", "Codex hook 信任", "warn", f"读取 config.toml 失败：{e}")
    # 信任键形如 [hooks.state."dev-harness@<marketplace>:hooks/hooks.json:stop:0:0"]；
    # 必须精确解析条目键——config.toml 的 [plugins] 段同样含 "dev-harness" 字样，裸子串匹配会假阳性
    trust_keys = re.findall(r'\[hooks\.state\.[\'"]([^\'"]+)[\'"]\]', text)
    trusted = [k for k in trust_keys if "dev-harness" in k]
    if trusted:
        return _check("codex_hook_trust", "Codex hook 信任", "ok",
                      f"[hooks.state] 含 {len(trusted)} 条 dev-harness 信任记录（如 {trusted[0]}）")
    guide = ("交互模式：运行 /hooks 批准 dev-harness Stop hook；"
             "headless：加 --run-hooks-without-persisted-trust（仅用于你已审核过 hook 来源的自动化场景）")
    return _check("codex_hook_trust", "Codex hook 信任", "warn",
                  "未在 [hooks.state] 注册 dev-harness → Codex 上 Stop 续跑防线静默失效",
                  guide)


def check_codex_manifest(ctx: Ctx):
    """.codex-plugin/plugin.json 存在性（Codex 斜杠命令前提，B2 负责生成）。"""
    p = ctx.plugin_root / ".codex-plugin" / "plugin.json"
    if p.exists():
        return _check("codex_manifest", "Codex 插件清单", "ok", ".codex-plugin/plugin.json 存在")
    if ctx.host == "codex":
        return _check("codex_manifest", "Codex 插件清单", "warn",
                      "缺 .codex-plugin/plugin.json → /dev 在 Codex 上不是斜杠命令",
                      "等待 B2 生成 .codex-plugin/plugin.json")
    return _check("codex_manifest", "Codex 插件清单", "skip",
                  "未找到 .codex-plugin/plugin.json（Codex 斜杠命令需要，当前非 Codex 平台）")


# ==================== 检测项：Cursor ====================

def check_cursor_plugin_root(ctx: Ctx):
    """CURSOR_PLUGIN_ROOT 注入检测。非 Cursor 平台标 skip（需真机验证）。"""
    val = os.environ.get("CURSOR_PLUGIN_ROOT")
    if ctx.host == "cursor":
        if val:
            return _check("cursor_plugin_root", "Cursor 环境注入", "ok", f"CURSOR_PLUGIN_ROOT={val}")
        return _check("cursor_plugin_root", "Cursor 环境注入", "fail",
                      "Cursor 平台但 CURSOR_PLUGIN_ROOT 未注入",
                      "确认 Cursor 插件安装完整")
    return _check("cursor_plugin_root", "Cursor 环境注入", "skip",
                  "非 Cursor 平台，需 Cursor 真机验证")


# ==================== 检测项：旧遗留清理（吸收 setup.sh L116-146 + fix-hook-path.sh） ====================

def _scan_legacy():
    """扫描 v3.2 前遗留的 Stop hook 注册与遗留脚本文件，返回 (settings_path, blocks, legacy_file, issues)。"""
    settings = claude_dir() / "settings.json"
    legacy_file = claude_dir() / "hooks" / "dev-harness-stop.py"
    issues = []
    data = None
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
            for block in data.get("hooks", {}).get("Stop", []):
                for h in block.get("hooks", []):
                    if "dev-harness-stop" in h.get("command", ""):
                        issues.append("settings.json 残留旧 Stop 注册")
                        break
        except (json.JSONDecodeError, OSError):
            pass
    if legacy_file.exists():
        issues.append("遗留脚本 dev-harness-stop.py")
    return settings, data, legacy_file, issues


def check_legacy_hook(ctx: Ctx):
    """旧 Stop hook 遗留检测。现代做法是移除（插件 hooks.json 已自动接管），--fix 执行清理。

    do_fix() 在所有检测项之前跑完（见 build_report），本函数开头的 _scan_legacy() 天然
    已是 --fix 后的状态，不需要再按 ctx.fix 分支重新扫描一次——两次扫描间文件系统不会变化，
    那是结构性死代码。
    """
    settings, data, legacy_file, issues = _scan_legacy()
    if not issues:
        detail = "已清理旧遗留注册" if ctx.fix else "插件 hooks/hooks.json 自动接管，无用户级残留"
        return _check("legacy_hook", "无旧 hook 遗留", "ok", detail)
    if ctx.fix:
        return _check("legacy_hook", "无旧 hook 遗留", "warn", f"清理后仍残留：{', '.join(issues)}")
    return _check("legacy_hook", "无旧 hook 遗留", "warn",
                  "、".join(issues) + "（Windows bash 路径导致 Cursor 无法识别）",
                  "运行 /dev-harness:setup --fix 清理旧注册")


# ==================== --fix 动作 ====================

def do_fix(ctx: Ctx):
    """执行修复动作，逐项记入 ctx.actions。幂等：已满足的项跳过。"""
    _fix_venv(ctx)
    _fix_legacy(ctx)


def _fix_venv(ctx: Ctx):
    """创建 venv + 装 filelock/rich。已存在且 filelock 可用则跳过。"""
    py, vdir = find_venv_python(ctx)
    if py:
        rc, _, _ = run_py(py, "import filelock")
        if rc == 0:
            return  # 幂等：已就绪
        _pip_install(ctx, py)
        return
    # 需要创建 venv
    system = ctx.system_py or system_python()
    if not system:
        ctx.actions.append("跳过 venv 创建：无可执行的系统 python")
        return
    target, in_data = ctx.fix_target_venv()
    rc, _, err = run([str(system), "-m", "venv", str(target)], timeout=120)
    if rc != 0:
        ctx.actions.append(f"venv 创建失败 @ {target}：{err[:120]}")
        return
    ctx.actions.append(f"创建 venv @ {target}")
    if not in_data:
        ctx.actions.append("警告：CLAUDE_PLUGIN_DATA 未设置，venv 建在版本化目录，插件升级后需重建")
    new_py = venv_python(target)
    if new_py:
        _pip_install(ctx, new_py)


def _pip_install(ctx: Ctx, py):
    rc, _, err = run([str(py), "-m", "pip", "install", "filelock", "rich", "-q"], timeout=180)
    if rc == 0:
        ctx.actions.append("pip 安装 filelock + rich")
    else:
        ctx.actions.append(f"pip 安装 filelock/rich 失败：{err[:120]}")


def _fix_legacy(ctx: Ctx):
    """移除 settings.json 旧 Stop 注册 + 删除遗留脚本文件（取代 fix-hook-path.sh 的路径改写）。"""
    settings, data, legacy_file, issues = _scan_legacy()
    if not issues:
        return
    if data is not None:
        hooks = data.get("hooks", {})
        stop = hooks.get("Stop", [])
        removed = 0
        cleaned = []
        for block in stop:
            kept = [h for h in block.get("hooks", []) if "dev-harness-stop" not in h.get("command", "")]
            removed += len(block.get("hooks", [])) - len(kept)
            if kept:
                block["hooks"] = kept
                cleaned.append(block)
        if removed:
            if cleaned:
                hooks["Stop"] = cleaned
            else:
                hooks.pop("Stop", None)
            try:
                settings.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                ctx.actions.append(f"移除 settings.json 中 {removed} 个旧 Stop 注册")
            except OSError as e:
                ctx.actions.append(f"清理 settings.json 失败：{e}")
    if legacy_file.exists():
        try:
            legacy_file.unlink()
            ctx.actions.append(f"删除遗留脚本 {legacy_file}")
        except OSError as e:
            ctx.actions.append(f"删除遗留脚本失败：{e}")


# ==================== 组装 ====================

CHECK_FUNCS = [
    check_python_exec,
    check_venv,
    check_filelock,
    check_required_files,
    check_plugin_root,
    check_codex_cli,
    check_claude_version,
    check_claude_hooks_enabled,
    check_codex_goals,
    check_codex_hook_trust,
    check_codex_manifest,
    check_cursor_plugin_root,
    check_legacy_hook,
]


def compute_ready(checks):
    by_id = {c["id"]: c for c in checks}
    for cid in CRITICAL_IDS:
        c = by_id.get(cid)
        if c is None or c["status"] in ("fail", "warn"):
            return False
    return True


def build_next_steps(checks, ctx, ready):
    steps = []
    if not ready and not ctx.fix:
        steps.append("运行 `/dev-harness:setup --fix` 自动修复可修项")
    for c in checks:
        if c["status"] in ("fail", "warn") and c["fix_hint"]:
            steps.append(f"[{c['id']}] {c['fix_hint']}")
    if ready:
        steps.append("验收：干净会话发一句「继续开发」，dev 技能应自动触发并输出启动声明")
    return steps


def build_report(fix: bool):
    plugin_root, root_source = resolve_plugin_root()
    host = detect_host()
    ctx = Ctx(plugin_root, root_source, host, fix)

    # fix 需要先知道系统 python（venv 创建靠它），先探一次填 ctx.system_py
    ctx.system_py = system_python()
    if fix:
        do_fix(ctx)
    # 正式跑全套检测（此时 venv/依赖可能已被 fix 改变）
    checks = [func(ctx) for func in CHECK_FUNCS]

    ready = compute_ready(checks)
    return {
        "ready": ready,
        "host": host,
        "checks": checks,
        "actionsTaken": ctx.actions,
        "nextSteps": build_next_steps(checks, ctx, ready),
    }


# ==================== 渲染 ====================

_TAG = {"ok": "[OK]  ", "warn": "[WARN]", "fail": "[FAIL]", "skip": "[SKIP]"}


def render_human(report):
    lines = [f"Dev Harness Setup Doctor  —  host={report['host']}  ready={report['ready']}", ""]
    lines.append("Checks:")
    for c in report["checks"]:
        tag = _TAG.get(c["status"], "[????]")
        lines.append(f"  {tag} {c['label']}: {c['detail']}")
    if report["actionsTaken"]:
        lines.append("")
        lines.append("Actions taken:")
        for a in report["actionsTaken"]:
            lines.append(f"  - {a}")
    if report["nextSteps"]:
        lines.append("")
        lines.append("Next steps:")
        for s in report["nextSteps"]:
            lines.append(f"  - {s}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="dev-harness 插件级安装体检 + 修复")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--fix", action="store_true", help="执行修复动作（默认只读 doctor）")
    args = ap.parse_args()

    report = build_report(fix=args.fix)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))
    # ready 布尔映射退出码，供上层脚本判断（0=就绪，1=未就绪）
    sys.exit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
