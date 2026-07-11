"""dev-harness lint — 红线机械化校验工具

把 docs/design-philosophy.md「红线表」从口头承诺变成可执行检查。
CI 或 pre-commit 都能调，违反 = 非零退出。

用法：
    bash scripts/dh-python.sh scripts/dh-lint.py            # 跑全部
    bash scripts/dh-python.sh scripts/dh-lint.py --check=red-line-8
    bash scripts/dh-python.sh scripts/dh-lint.py --list     # 列已注册的检查
    bash scripts/dh-python.sh scripts/dh-lint.py --verbose  # 全量违反清单

实现策略：
- 简单可靠优先，复杂规则（红线 1/2/6/7/9 全量）标 TODO 渐进补
- 当前覆盖：红线 4（SKILL ≤ 200 行）/ 红线 5（hook 超时）/ 红线 8（logical stages ≤ 7）
  + 新红线 model-context（原则 8 落地）+ 模型分级一致性
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

# Windows cmd.exe 默认 GBK 编码，✓/✗ 输出会崩 — 与 pitfall-analyze.py 同款修法
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

# ==================== 配置 ====================

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIMIT_VIOLATIONS = 15  # 单条检查最多显示几个违反

# --check=skill-edit-evidence 用的对比基准，由 main() 按 --base 参数写入
_BASE_REF = "master"

# ==================== Frontmatter 工具 ====================

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict | None:
    """极简 frontmatter 解析（与 scripts/lib/config.py 风格一致）"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    result: dict = {}
    for line in m.group(1).splitlines():
        if line.startswith(" ") or not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def iter_skills() -> list[Path]:
    """所有 SKILL.md（含 plugin 自带的 generic-* 和短名）"""
    return sorted((ROOT / "skills").rglob("SKILL.md"))


def iter_agents() -> list[Path]:
    """所有 agent 定义"""
    return sorted((ROOT / "agents").glob("*.md"))


# ==================== 红线检查 ====================

def check_red_line_4() -> list[tuple]:
    """红线 4: SKILL.md 不超过 200 行"""
    violations = []
    for skill in iter_skills():
        n = len(skill.read_text(encoding="utf-8").splitlines())
        if n > 200:
            violations.append((skill.relative_to(ROOT), f"{n} lines > 200"))
    return violations


def check_red_line_5() -> list[tuple]:
    """红线 5: 每个 hook 必须有超时（timeout）或降级（fallback）路径

    检测 hooks/hooks.json 与 hooks/*.py 内是否含 timeout 关键字 / try-except / sys.exit(0)。
    宽松规则：含其中之一即视为有 fail-safe。
    """
    violations = []
    hooks_dir = ROOT / "hooks"
    if not hooks_dir.exists():
        return [(Path("hooks/"), "directory missing")]
    safe_kws = ("timeout", "TimeoutError", "except", "fallback", "sys.exit(0)")
    for hook in hooks_dir.glob("*.py"):
        text = hook.read_text(encoding="utf-8", errors="replace")
        if not any(kw in text for kw in safe_kws):
            violations.append((hook.relative_to(ROOT), "no timeout / except / fallback / sys.exit(0)"))
    return violations


def check_red_line_8() -> list[tuple]:
    """红线 8: pipeline 逻辑 stage 数 ≤ 7（parallel_group 视为单一）"""
    pipeline = ROOT / "defaults" / "pipeline.yml"
    if not pipeline.exists():
        return [(pipeline.relative_to(ROOT), "file missing")]
    stages: list[dict] = []
    in_stages = False
    for line in pipeline.read_text(encoding="utf-8").splitlines():
        if line.startswith("stages:"):
            in_stages = True
            continue
        if in_stages:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if line and not line.startswith(" "):
                in_stages = False
                continue
            m = re.match(r"\s*-\s*name:\s*(\S+)", line)
            if m:
                stages.append({"name": m.group(1), "parallel_group": None})
                continue
            m = re.match(r"\s*parallel_group:\s*(\S+)", line)
            if m and stages:
                stages[-1]["parallel_group"] = m.group(1)
    # 计算逻辑 stage 数：同一 parallel_group 内的多个物理 stage 视为 1
    seen_groups: set[str] = set()
    logical_count = 0
    for s in stages:
        pg = s["parallel_group"]
        if pg:
            if pg not in seen_groups:
                seen_groups.add(pg)
                logical_count += 1
        else:
            logical_count += 1
    if logical_count > 7:
        names = ", ".join(s["name"] for s in stages)
        return [(pipeline.relative_to(ROOT), f"{logical_count} logical stages > 7 (physical: {names})")]
    return []


def check_model_context_present() -> list[tuple]:
    """新红线（原则 8 落地）: SKILL/Agent frontmatter 必须有 model_context 字段"""
    violations = []
    for f in iter_skills() + iter_agents():
        fm = parse_frontmatter(f.read_text(encoding="utf-8"))
        if fm is None:
            violations.append((f.relative_to(ROOT), "no frontmatter"))
        elif "model_context" not in fm:
            violations.append((f.relative_to(ROOT), "missing 'model_context' field"))
    return violations


def check_model_tier_consistency() -> list[tuple]:
    """新增检查（原则 7 + research §Agent 模型配置）：
    agent 模型必须与 design-philosophy 第 §五 状态评估一致。
    当前规则：只读类 agent（gate-checker / explore / wiki-syncer / code-reviewer /
              security-reviewer / skill-router）应使用 sonnet 或更轻；
              核心推理类（architect / planner / executor / debugger / qa-tester /
              auto-loop）应保留 opus。
    """
    # research 报告 §"Agent 模型配置" 的规则表
    expected = {
        # 仅 sonnet 或更轻
        "gate-checker": {"sonnet", "haiku"},
        "explore": {"sonnet", "haiku"},
        "wiki-syncer": {"sonnet", "haiku"},
        "code-reviewer": {"sonnet", "haiku"},
        "security-reviewer": {"sonnet", "haiku"},
        # 保留 opus（critical reasoning）
        "skill-router": {"opus"},
        "architect": {"opus"},
        "planner": {"opus"},
        "executor": {"opus"},
        "debugger": {"opus"},
        "qa-tester": {"opus"},
        "auto-loop": {"opus"},
    }
    violations = []
    for agent in iter_agents():
        fm = parse_frontmatter(agent.read_text(encoding="utf-8"))
        if fm is None:
            continue
        name = fm.get("name") or agent.stem
        actual = fm.get("model", "opus")
        if name in expected and actual not in expected[name]:
            rule = "|".join(sorted(expected[name]))
            violations.append((agent.relative_to(ROOT), f"agent={name} model={actual}, expected ∈ {{{rule}}}"))
    return violations


# ==================== v4.5: skill 编辑证据门禁 ====================

def _git(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """跑一条 git 命令，返回 (returncode, stdout, stderr)，异常统一收敛为 rc=-1。"""
    try:
        r = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


# 命中任一即视为"触碰了行为契约"：description 字段本身、或 dev-pipeline /
# generic-implement 里的连续执行红线段、启动声明、完成契约结构化槽
SKILL_EDIT_TRIGGER_KEYWORDS = ("连续执行（违纪红线）", "启动声明", "完成契约")


def _diff_touches_trigger(diff_text: str) -> bool:
    """只看新增/删除行（+/- 前缀），跳过 diff 文件头 +++/---。"""
    for line in diff_text.splitlines():
        if not line or line[0] not in "+-" or line.startswith(("+++", "---")):
            continue
        content = line[1:]
        if re.match(r"^\s*description:", content):
            return True
        if any(kw in content for kw in SKILL_EDIT_TRIGGER_KEYWORDS):
            return True
    return False


def _skill_slug(skill_md: Path) -> str:
    """优先用 frontmatter 的 name 字段（技能真实身份），没有则退回目录名。"""
    fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    if fm and fm.get("name"):
        return fm["name"]
    return skill_md.parent.name


def check_skill_edit_evidence() -> list[tuple]:
    """v4.5: SKILL.md 编辑证据门禁（Iron Law 对 EDIT 同样适用，不只 NEW）。

    diff 命中 skills/**/SKILL.md 的 description 行、或连续执行红线/启动声明/
    完成契约段时，要求 eval/results/ 下存在本次改动对应的 RED+GREEN 压力测试
    证据文件（命名约定 <date>-<skill>-pressure.md，只检查存在性 + 非空）。

    对比基准由 --base 指定（默认 master）。只在显式
    --check=skill-edit-evidence 时运行，不进 run-all 默认集合——
    改行为话术是低频动作，不该拖慢日常 lint。
    """
    rc, out, err = _git(["diff", f"{_BASE_REF}...HEAD", "--name-only"])
    if rc != 0:
        return [(Path("(git)"), f"git diff --name-only 失败（base={_BASE_REF}）: {err.strip()[:200]}")]

    skill_files = [ln for ln in out.splitlines() if re.match(r"^skills/.+/SKILL\.md$", ln)]
    if not skill_files:
        return []

    results_dir = ROOT / "eval" / "results"
    violations = []
    for rel in skill_files:
        f = ROOT / rel
        if not f.exists():
            continue  # 本次改动删掉了这个 skill，不需要证据
        rc2, diff_text, _ = _git(["diff", f"{_BASE_REF}...HEAD", "--", rel])
        if rc2 != 0 or not _diff_touches_trigger(diff_text):
            continue
        slug = _skill_slug(f)
        has_evidence = results_dir.exists() and any(
            p.is_file() and p.stat().st_size > 0
            for p in results_dir.glob(f"*-{slug}-pressure.md")
        )
        if not has_evidence:
            violations.append((
                Path(rel),
                f"description/连续执行/完成契约改动缺 RED+GREEN 证据 — "
                f"先跑改动前 baseline ≥5 次逐字记录失败(RED)，再跑改动后 ≥5 次确认合规(GREEN)，"
                f"存到 eval/results/<date>-{slug}-pressure.md",
            ))
    return violations


# ==================== TODO（渐进补） ====================

def check_red_line_1_todo() -> list[tuple]:
    """红线 1: PR 必须有"补偿什么缺口"段落。
    依赖 PR 描述/模板，不在仓库内 lint 范围；CI 中通过 .github/PULL_REQUEST_TEMPLATE.md 强制。"""
    template = ROOT / ".github" / "pull_request_template.md"
    if template.exists():
        return []
    return [(Path(".github/pull_request_template.md"), "missing — required by red line 1")]


def check_red_line_9_inline_urls() -> list[tuple]:
    """红线 9: SKILL/Agent prompt 中禁止依赖外部 URL（除非缓存到仓库）。
    简化规则：扫描非 frontmatter 部分的 http(s) URL，允许 markdown 链接形式（认为是引证）。
    TODO: 区分"prompt 内运行时依赖"vs"文档引证"，当前实现可能有 false positive，
          可在 dev-config.yml 增加 allowlist 后再开启严格模式。
    """
    violations = []
    url_in_code_re = re.compile(r"(?<!\[)https?://[^\s\)]+", re.MULTILINE)
    for f in iter_skills() + iter_agents():
        text = f.read_text(encoding="utf-8")
        # 跳过 frontmatter
        m = FRONTMATTER_RE.match(text)
        body = text[m.end():] if m else text
        # 跳过 markdown 链接形式 [text](url) 和参考段落
        skip_section = False
        for i, line in enumerate(body.splitlines(), 1):
            ls = line.lstrip()
            # 引证/参考段落（## References / ## 引证）跳过
            if re.match(r"^#+\s*(references|引证|see also|reference)", ls.lower()):
                skip_section = True
                continue
            if ls.startswith("#"):
                skip_section = False
            if skip_section:
                continue
            # 已是 markdown link 跳过
            line_no_links = re.sub(r"\[([^\]]+)\]\([^)]+\)", "", line)
            if url_in_code_re.search(line_no_links):
                snippet = line.strip()[:60]
                violations.append((f.relative_to(ROOT), f":{i} {snippet}..."))
                if len(violations) > 50:  # cap 避免炸
                    return violations
    return violations


# ==================== 注册表 ====================

Check = Callable[[], list[tuple]]
CHECKS: dict[str, tuple[str, Check]] = {
    "red-line-4":        ("SKILL.md ≤ 200 lines",                       check_red_line_4),
    "red-line-5":        ("hooks have timeout / fallback",               check_red_line_5),
    "red-line-8":        ("pipeline logical stages ≤ 7",                 check_red_line_8),
    "model-context":     ("SKILL/Agent has model_context frontmatter",   check_model_context_present),
    "model-tier":        ("agent model tier matches research §config",   check_model_tier_consistency),
    "red-line-1-todo":   ("PR template exists (red line 1)",             check_red_line_1_todo),
    "red-line-9-urls":   ("no inline external URLs in prompts (loose)",  check_red_line_9_inline_urls),
    "skill-edit-evidence": ("SKILL.md 行为改动需 RED+GREEN 压力测试证据 (CI/PR opt-in)", check_skill_edit_evidence),
}

# 默认运行的检查：红线 9 因 false positive 风险默认不跑（需 --check=red-line-9-urls 显式启用），
# skill-edit-evidence 需要 git 对比基准、只在 CI/PR 场景显式调用，同样不进 run-all
_OPT_IN_ONLY = ("red-line-9-urls", "skill-edit-evidence")
DEFAULT_CHECKS = [k for k in CHECKS if k not in _OPT_IN_ONLY]


# ==================== CLI ====================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="dev-harness red-line lint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check", default="default",
        help=f"Which check to run. 'all' / 'default' / one of: {','.join(CHECKS.keys())}",
    )
    parser.add_argument("--list", action="store_true", help="list all registered checks and exit")
    parser.add_argument("--verbose", action="store_true", help="show all violations (no cap)")
    parser.add_argument("--exit-zero", action="store_true", help="always exit 0 even if violations found")
    parser.add_argument(
        "--base", default="master",
        help="git ref to diff against for --check=skill-edit-evidence (default: master)",
    )
    args = parser.parse_args()

    global _BASE_REF
    _BASE_REF = args.base

    if args.list:
        for name, (title, _) in CHECKS.items():
            tag = " [default]" if name in DEFAULT_CHECKS else " [opt-in]"
            print(f"  {name:20s} {title}{tag}")
        return 0

    if args.check == "all":
        names = list(CHECKS.keys())
    elif args.check == "default":
        names = DEFAULT_CHECKS
    elif args.check in CHECKS:
        names = [args.check]
    else:
        print(f"Unknown check: {args.check}. Use --list to see options.", file=sys.stderr)
        return 2

    total_fails = 0
    for name in names:
        title, fn = CHECKS[name]
        try:
            violations = fn()
        except Exception as e:
            print(f"⚠ {name}: check raised {type(e).__name__}: {e}", file=sys.stderr)
            total_fails += 1
            continue
        if violations:
            print(f"✗ {name}: {title} — {len(violations)} violation(s)")
            cap = len(violations) if args.verbose else DEFAULT_LIMIT_VIOLATIONS
            for v in violations[:cap]:
                if isinstance(v, tuple):
                    print(f"    {' | '.join(str(x) for x in v)}")
                else:
                    print(f"    {v}")
            if len(violations) > cap:
                print(f"    ... and {len(violations) - cap} more (--verbose to expand)")
            total_fails += len(violations)
        else:
            print(f"✓ {name}: {title}")

    if args.exit_zero:
        return 0
    return 1 if total_fails > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
