#!/usr/bin/env python3
"""团队版包检查与复制工具；不安装、不联网、不覆盖已有目录。"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "plugins" / "dev-harness"
NAMES = {f"dev-harness-{name}" for name in ("init", "work", "change", "handoff")}
LINK = re.compile(r"\]\(([^)]+)\)")


def fail(message):
    raise ValueError(message)


def is_link(path):
    try:
        # Python 3.10 尚无 Path.is_junction；用 Windows reparse 属性保护相同边界。
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return path.is_symlink() or bool(attributes & 0x400)
    except FileNotFoundError:
        return False


def check_paths(root):
    """发布目录不携带外部符号链接或 Windows junction。"""
    for path in [root, *root.rglob("*")]:
        if is_link(path):
            fail(f"不接受链接目录或文件：{path}")


def check_links(root):
    root = root.resolve()
    for path in root.rglob("*.md"):
        for link in LINK.findall(path.read_text(encoding="utf-8")):
            if link.startswith(("https://", "http://", "#")):
                continue
            target = (path.parent / link.split("#", 1)[0]).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                fail(f"引用缺失或越界：{path.relative_to(root)} -> {link}")


def check_skills(directory):
    if {p.name for p in directory.iterdir() if p.is_dir()} != NAMES:
        fail("必须且只能包含四个团队版 Skill")
    for name in sorted(NAMES):
        content = (directory / name / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"\A---\nname: ([\w-]+)\ndescription: ([^\n]+)\n---\n", content)
        if not match or match[1] != name:
            fail(f"Skill 声明不匹配：{name}")


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file() and p != root / "provenance.json"}


def check(root):
    root = Path(root).absolute()
    check_paths(root)
    codex = json.loads((root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    claude = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    if codex.get("name") != "dev-harness" or codex.get("skills") != "./skills/":
        fail("Codex 包身份或 Skills 入口不正确")
    for key in ("name", "version", "description", "license"):
        if not codex.get(key) or codex[key] != claude.get(key):
            fail(f"宿主元数据不一致：{key}")
    for host in (codex, claude):
        if any(key in host for key in ("hooks", "agents", "mcpServers", "apps")):
            fail("首版不声明 Hooks、Agent 或外部服务")
    if any((root / name).exists() for name in ("hooks", "agents", "commands", ".mcp.json", ".app.json")):
        fail("发现旧版或范围外默认入口")
    if not (root / "LICENSE").is_file():
        fail("缺少许可证")
    check_skills(root / "skills")
    check_links(root)
    receipt = root / "provenance.json"
    if receipt.exists() and json.loads(receipt.read_text(encoding="utf-8"))["files"] != hashes(root):
        fail("发布文件与来源清单不匹配")
    return codex


def git_value(*args):
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def package(output, kind="plugin", source=SOURCE):
    source = Path(source).absolute()
    manifest = check(source)
    output = Path(output).absolute()
    for parent in [output, *output.parents]:
        if is_link(parent):
            fail(f"输出经过链接路径：{parent}")
    if output.exists() or output.resolve().is_relative_to(source.resolve()):
        fail("输出必须是源码目录以外的新目录；保留已有文件")
    source_files = hashes(source)
    output.mkdir(parents=True, exist_ok=False)
    if kind == "plugin":
        shutil.copytree(source, output, dirs_exist_ok=True)
        skills = output / "skills"
    else:
        skills = output / ".agents/skills"
        shutil.copytree(source / "skills", skills)
        shutil.copyfile(source / "LICENSE", output / "LICENSE")
    for name in sorted(NAMES):
        skill = skills / name
        entry = skill / "SKILL.md"
        text = entry.read_text(encoding="utf-8")
        for link in LINK.findall(text):
            if link.startswith(("../../references/", "../../templates/")):
                relative = link.removeprefix("../../")
                target = skill / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / relative, target)
                text = text.replace(f"]({link})", f"]({relative})")
        entry.write_text(text, encoding="utf-8", newline="\n")
        check_links(skill)
    check_skills(skills)
    if kind == "plugin":
        check(output)
    dirty = git_value("status", "--porcelain")
    receipt = {
        "format": kind, "version": manifest["version"],
        "source_revision": git_value("rev-parse", "HEAD"),
        "source_dirty": bool(dirty) if dirty is not None else None,
        "source_files": source_files, "files": hashes(output),
    }
    (output / "provenance.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check_command = commands.add_parser("check")
    check_command.add_argument("path", nargs="?", default=str(SOURCE))
    build = commands.add_parser("package")
    build.add_argument("--output", required=True)
    build.add_argument("--format", choices=("plugin", "skills"), default="plugin")
    args = parser.parse_args()
    try:
        result = check(args.path) if args.command == "check" else package(args.output, args.format)
        print(json.dumps({"status": "passed", "version": result["version"], "command": args.command}))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"失败：{error}\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
