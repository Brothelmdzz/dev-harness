"""
三层 Skill 解析器 (v3.0)
用法:
  python skill-resolver.py <stage_name> [--project-dir .] [--verbose] [--profile frontend]
  python skill-resolver.py --all [--profile backend]

解析优先级:
  L1: 项目层  .claude/skills/{name}/ 或 .claude/commands/{name}.md
  L2: 用户层  ~/.claude/skills/{name}/ 或 ~/.claude/commands/{name}.md
  L3: 内置层  dev-harness/skills/generic-{name}/

v3.0 新增:
  --profile: 角色 profile (backend/frontend/product/qa/fullstack)
  Profile 影响别名查找: 先尝试 profile 专用别名，再 fallback 到通用
"""
import os, sys, json, argparse
from pathlib import Path

# ==================== 别名映射 ====================

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

# 角色 Profile → 额外别名前缀
PROFILE_ALIASES = {
    "frontend": {
        "research":  ["frontend-research", "frontend_research"],
        "implement": ["frontend-implement", "frontend_implement"],
        "test":      ["frontend-test", "frontend_test"],
        "audit":     ["frontend-audit", "frontend_audit"],
    },
    "product": {
        "prd":    ["product-prd", "product_prd"],
        "review": ["product-review", "product_review"],
    },
    "qa": {
        "test":      ["qa-e2e", "qa-test", "qa_test"],
        "audit":     ["qa-regression", "qa_regression"],
    },
    "fullstack": {},
    "backend": {},
}

# ==================== 解析逻辑 ====================

def resolve(stage_name, project_dir=None, user_home=None, plugin_dir=None, profile=None):
    if project_dir is None:
        project_dir = find_project_root()
    if user_home is None:
        user_home = Path.home()
    if plugin_dir is None:
        plugin_dir = Path(__file__).parent.parent
    if profile is None:
        profile = "backend"

    base_aliases = SKILL_ALIASES.get(stage_name, [stage_name, f"generic-{stage_name}"])
    profile_extra = PROFILE_ALIASES.get(profile, {}).get(stage_name, [])
    aliases = profile_extra + base_aliases

    for alias in aliases:
        # L1: 项目层
        p = Path(project_dir) / ".claude" / "skills" / alias / "SKILL.md"
        if p.exists():
            return {"level": "L1", "source": "project", "name": alias,
                    "path": str(p), "invoke": f"/{alias}", "profile": profile}
        p = Path(project_dir) / ".claude" / "commands" / f"{alias}.md"
        if p.exists():
            return {"level": "L1", "source": "project", "name": alias,
                    "path": str(p), "invoke": f"/{alias}", "profile": profile}

    for alias in aliases:
        # L2: 用户层
        p = Path(user_home) / ".claude" / "skills" / alias / "SKILL.md"
        if p.exists():
            return {"level": "L2", "source": "user", "name": alias,
                    "path": str(p), "invoke": f"/{alias}", "profile": profile}
        p = Path(user_home) / ".claude" / "commands" / f"{alias}.md"
        if p.exists():
            return {"level": "L2", "source": "user", "name": alias,
                    "path": str(p), "invoke": f"/{alias}", "profile": profile}

    # L3: 内置层
    for alias in aliases:
        if alias.startswith("generic-"):
            p = plugin_dir / "skills" / alias / "SKILL.md"
            if p.exists():
                return {"level": "L3", "source": "builtin", "name": alias,
                        "path": str(p), "invoke": f"dev-harness:{alias}", "profile": profile}

    generic_name = f"generic-{stage_name}"
    return {"level": "L3", "source": "builtin", "name": generic_name,
            "path": str(plugin_dir / "skills" / generic_name / "SKILL.md"),
            "invoke": f"dev-harness:{generic_name}", "profile": profile}

def resolve_all(project_dir=None, user_home=None, plugin_dir=None, profile=None):
    result = {}
    for stage in SKILL_ALIASES:
        result[stage] = resolve(stage, project_dir, user_home, plugin_dir, profile)
    return result

from lib.project import find_project_root

# ==================== CLI ====================

def main():
    parser = argparse.ArgumentParser(description="Skill Resolver (v3.0)")
    parser.add_argument("stage", nargs="?", help="Stage name to resolve")
    parser.add_argument("--all", action="store_true", help="Resolve all stages")
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--profile", default="backend",
                        choices=["backend", "frontend", "product", "qa", "fullstack"],
                        help="角色 profile (默认: backend)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.all:
        result = resolve_all(args.project_dir, profile=args.profile)
        if args.profile != "backend":
            print(f"  Profile: {args.profile}")
        for stage, info in result.items():
            level = info["level"]
            name = info["name"]
            source = info["source"]
            exists = "OK" if os.path.exists(info["path"]) else "MISSING"
            print(f"  {stage:<12} -> {level} {name:<20} ({source}) [{exists}]")
    elif args.stage:
        info = resolve(args.stage, args.project_dir, profile=args.profile)
        if args.verbose:
            print(json.dumps(info, ensure_ascii=False, indent=2))
        else:
            print(f"{info['level']}:{info['name']} -> {info['invoke']}")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
