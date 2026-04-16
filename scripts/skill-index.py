"""
Dev Harness — Skill 可视化索引
用法: python skill-index.py [--project-dir .]

扫描 L1/L2/L3 所有 Skill，输出可读索引。
"""
import os, sys, argparse
from pathlib import Path

from lib.project import find_project_root

def scan_skills(base_dir, label):
    """扫描目录下的 Skill，返回 {name: description}"""
    result = {}
    skills_dir = Path(base_dir) / "skills"
    if not skills_dir.exists():
        # 兼容旧结构 commands/
        commands_dir = Path(base_dir) / "commands"
        if commands_dir.exists():
            for f in commands_dir.glob("*.md"):
                result[f.stem] = "(command)"
        return result

    for d in skills_dir.iterdir():
        if d.is_dir():
            skill_file = d / "SKILL.md"
            if skill_file.exists():
                desc = extract_description(skill_file)
                result[d.name] = desc
    return result

def extract_description(path):
    """从 SKILL.md frontmatter 提取 description"""
    try:
        content = path.read_text(encoding="utf-8")
        in_front = False
        for line in content.split("\n"):
            if line.strip() == "---":
                in_front = not in_front
                continue
            if in_front and line.startswith("description:"):
                return line.split(":", 1)[1].strip()[:60]
    except:
        pass
    return ""

def main():
    parser = argparse.ArgumentParser(description="Skill Index")
    parser.add_argument("--project-dir", default=None)
    args = parser.parse_args()

    project_dir = args.project_dir or find_project_root()
    user_home = Path.home()
    plugin_dir = Path(__file__).parent.parent

    print("Dev Harness Skill 索引")
    print("=" * 60)

    # L1: 项目层
    l1 = scan_skills(Path(project_dir) / ".claude", "project")
    print(f"\nL1 项目层 (.claude/skills/) — {len(l1)} 个")
    if l1:
        for name, desc in sorted(l1.items()):
            print(f"  {name:<25} {desc}")
    else:
        print("  (无)")

    # L2: 用户层
    l2 = scan_skills(user_home / ".claude", "user")
    print(f"\nL2 用户层 (~/.claude/skills/) — {len(l2)} 个")
    if l2:
        for name, desc in sorted(l2.items()):
            print(f"  {name:<25} {desc}")
    else:
        print("  (无)")

    # L3: 内置层
    l3 = scan_skills(plugin_dir, "builtin")
    print(f"\nL3 内置层 (dev-harness/skills/) — {len(l3)} 个")
    if l3:
        for name, desc in sorted(l3.items()):
            print(f"  {name:<25} {desc}")
    else:
        print("  (无)")

    # 总结
    total = len(l1) + len(l2) + len(l3)
    print(f"\n总计: {total} 个 Skill (L1:{len(l1)} L2:{len(l2)} L3:{len(l3)})")
    print(f"\n自定义方式:")
    print(f"  项目层: .claude/skills/{{name}}/SKILL.md")
    print(f"  用户层: ~/.claude/skills/{{name}}/SKILL.md")
    print(f"  脚手架: bash \"${{CLAUDE_PLUGIN_ROOT}}/scripts/scaffold.sh\" <name>")

if __name__ == "__main__":
    main()
