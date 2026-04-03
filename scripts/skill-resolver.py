"""
三层 Skill 解析器
用法: python skill-resolver.py <stage_name> [--project-dir .] [--verbose]

解析优先级:
  L1: 项目层  .claude/skills/{name}/ 或 .claude/commands/{name}.md
  L2: 用户层  ~/.claude/skills/{name}/ 或 ~/.claude/commands/{name}.md
  L3: 内置层  dev-harness/skills/generic-{name}/
"""
import os, sys, json, argparse
from pathlib import Path

# ==================== 别名映射 ====================

# stage name → 可能的 Skill 文件名（按优先级排列）
SKILL_ALIASES = {
    "research":  ["research_codebase", "research", "generic-research"],
    "prd":       ["create_prd", "prd", "generic-prd"],
    "plan":      ["create_plan", "plan", "generic-plan"],
    "implement": ["implement_plan", "implement", "generic-implement"],
    "validate":  ["validate_plan", "validate", "generic-validate"],
    "audit":     ["audit-logic", "audit", "generic-audit"],
    "test":      ["test-apis", "test", "generic-test"],
    "docs":      ["update-api-docs", "docs", "generic-docs"],
    "review":    ["generic-review", "review"],
    "wiki":      ["generic-wiki", "wiki"],
    "remember":  ["remember", "generic-remember"],
}

# ==================== 解析逻辑 ====================

def resolve(stage_name, project_dir=None, user_home=None, plugin_dir=None):
    """
    三层解析返回:
    {
      "level": "L1" | "L2" | "L3",
      "source": "project" | "user" | "builtin",
      "name": "audit-logic",
      "path": "/path/to/SKILL.md or command.md",
      "invoke": "/audit-logic" or "内置 generic-audit"
    }
    """
    if project_dir is None:
        project_dir = find_project_root()
    if user_home is None:
        user_home = Path.home()
    if plugin_dir is None:
        plugin_dir = Path(__file__).parent.parent

    aliases = SKILL_ALIASES.get(stage_name, [stage_name, f"generic-{stage_name}"])

    for alias in aliases:
        # ==================== L1: 项目层 ====================
        # .claude/skills/{alias}/SKILL.md
        p = Path(project_dir) / ".claude" / "skills" / alias / "SKILL.md"
        if p.exists():
            return {
                "level": "L1", "source": "project", "name": alias,
                "path": str(p), "invoke": f"/{alias}",
            }

        # .claude/commands/{alias}.md（兼容旧结构）
        p = Path(project_dir) / ".claude" / "commands" / f"{alias}.md"
        if p.exists():
            return {
                "level": "L1", "source": "project", "name": alias,
                "path": str(p), "invoke": f"/{alias}",
            }

    for alias in aliases:
        # ==================== L2: 用户层 ====================
        # ~/.claude/skills/{alias}/SKILL.md
        p = Path(user_home) / ".claude" / "skills" / alias / "SKILL.md"
        if p.exists():
            return {
                "level": "L2", "source": "user", "name": alias,
                "path": str(p), "invoke": f"/{alias}",
            }

        # ~/.claude/commands/{alias}.md
        p = Path(user_home) / ".claude" / "commands" / f"{alias}.md"
        if p.exists():
            return {
                "level": "L2", "source": "user", "name": alias,
                "path": str(p), "invoke": f"/{alias}",
            }

    # ==================== L3: 内置层 ====================
    for alias in aliases:
        if alias.startswith("generic-"):
            p = plugin_dir / "skills" / alias / "SKILL.md"
            if p.exists():
                return {
                    "level": "L3", "source": "builtin", "name": alias,
                    "path": str(p), "invoke": f"dev-harness:{alias}",
                }

    # 兜底: 返回内置 generic
    generic_name = f"generic-{stage_name}"
    return {
        "level": "L3", "source": "builtin", "name": generic_name,
        "path": str(plugin_dir / "skills" / generic_name / "SKILL.md"),
        "invoke": f"dev-harness:{generic_name}",
    }

def resolve_all(project_dir=None, user_home=None, plugin_dir=None):
    """解析全部 stage，返回完整映射"""
    result = {}
    for stage in SKILL_ALIASES:
        result[stage] = resolve(stage, project_dir, user_home, plugin_dir)
    return result

def find_project_root():
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()

# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Skill Resolver")
    parser.add_argument("stage", nargs="?", help="Stage name to resolve")
    parser.add_argument("--all", action="store_true", help="Resolve all stages")
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.all:
        result = resolve_all(args.project_dir)
        for stage, info in result.items():
            level = info["level"]
            name = info["name"]
            source = info["source"]
            exists = "OK" if os.path.exists(info["path"]) else "MISSING"
            print(f"  {stage:<12} -> {level} {name:<20} ({source}) [{exists}]")
    elif args.stage:
        info = resolve(args.stage, args.project_dir)
        if args.verbose:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"{info['level']}:{info['name']} -> {info['invoke']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
