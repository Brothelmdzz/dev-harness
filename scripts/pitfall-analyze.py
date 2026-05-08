#!/usr/bin/env python3
"""
pitfall-analyze — 扫描项目的 pitfall-journal.jsonl，提炼候选规则

工作流：
  1. 读取 .claude/pitfall-journal.jsonl
  2. 按 category 聚类未 A/B 验证过的失败
  3. ≥ threshold（默认 3）条同类 → 生成 .claude/rules/auto-{category}-{date}.md.candidate
  4. 用户人工 review 后改名为 .md 才生效（不直接覆盖 rules/）

用法：
  python pitfall-analyze.py                    # 默认项目根 = cwd，threshold=3
  python pitfall-analyze.py --project /path    # 指定项目根
  python pitfall-analyze.py --threshold 5      # 改阈值
  python pitfall-analyze.py --dry-run          # 仅打印不写文件
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows cmd 默认 GBK 编码，强制 stdout/stderr 走 UTF-8 避免中文/特殊字符报错
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass  # Python < 3.7 或不支持 reconfigure 的环境，让 print 自己应付

# 让本脚本能 import scripts/lib/
_plugin_root = Path(__file__).resolve().parent
sys.path.insert(0, str(_plugin_root))

from lib.pitfall import find_promotable, get_pitfall_path  # noqa: E402

CANDIDATE_TEMPLATE = """# 自动提炼的规则候选 — {category}

> ⚠️ 这是 `pitfall-analyze.py` 自动生成的**候选**规则，**不会自动生效**。
> 阅读后觉得有价值 → 编辑+改名为 `.md`（去掉 `.candidate` 后缀）才会被 dev-harness 加载。
> 不需要 → 直接删除本文件。
>
> 来源：{count} 条 `{category}` 类失败汇总，时间范围 {date_range}
> 生成时间：{generated_at}

## 失败模式概览

{summary_table}

## 候选规则（请人工编辑后保留）

> 仅给出脚手架，请按 `rules/README.md` 的反例免疫格式补全。

### 规则 X：[一句话标题 — 你来填]

**补偿的缺口**：[根据下方根因总结，模型在 {category} 阶段倾向 ...]

**❌ 反例**：
```
[把下方某条失败摘要里的反例代码片段贴这里]
```

**✅ 正例**：
```
[把对应的修复方式贴这里]
```

**边界 / 例外**：
- [如果有的话]

---

## 原始失败条目（供编辑时参考）

{raw_entries}

---

## 决策选项

- **保留**：编辑上方"候选规则"段落补全反例/正例 → 重命名为 `.md`
- **丢弃**：直接删除本文件（不会再次自动生成相同规则，因为这些条目会标记为已 A/B 测试）
- **稍后再看**：保留为 `.candidate`，下次 `pitfall-analyze` 不会重复生成
"""

def _format_summary_table(entries):
    rows = ["| 时间 | 摘要 | 根因 |", "|------|------|------|"]
    for e in entries[:20]:  # 最多列 20 条避免太长
        ts = e.get("occurred_at", "")[:19].replace("T", " ")
        summary = e.get("summary", "").replace("|", "\\|")[:60]
        root = e.get("root_cause", "").replace("|", "\\|")[:60]
        rows.append(f"| {ts} | {summary} | {root} |")
    return "\n".join(rows)

def _format_raw_entries(entries):
    blocks = []
    for e in entries:
        blocks.append(f"### {e.get('id', '?')} — {e.get('occurred_at', '')[:19]}\n")
        blocks.append(f"- **summary**: {e.get('summary', '')}")
        if e.get("root_cause"):
            blocks.append(f"- **root_cause**: {e['root_cause']}")
        if e.get("resolution"):
            blocks.append(f"- **resolution**: {e['resolution']}")
        blocks.append(f"- **phase**: {e.get('phase', '?')}")
        blocks.append("")
    return "\n".join(blocks)

def _date_range(entries):
    if not entries:
        return "(空)"
    timestamps = [e.get("occurred_at", "") for e in entries if e.get("occurred_at")]
    if not timestamps:
        return "(无时间戳)"
    return f"{min(timestamps)[:10]} ~ {max(timestamps)[:10]}"

def main():
    parser = argparse.ArgumentParser(description="扫描 pitfall-journal 提炼候选规则")
    parser.add_argument("--project", default=".", help="项目根目录（默认 cwd）")
    parser.add_argument("--threshold", type=int, default=3, help="≥ N 条同类才提炼（默认 3）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印不写文件")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    pitfall_path = get_pitfall_path(project_root)

    print(f"[pitfall-analyze] 项目: {project_root}")
    print(f"[pitfall-analyze] 日志: {pitfall_path}")
    print(f"[pitfall-analyze] 阈值: {args.threshold}")
    print()

    if not pitfall_path.exists():
        print("⚠️ pitfall-journal.jsonl 不存在，跳过。")
        sys.exit(0)

    promotable = find_promotable(project_root, threshold=args.threshold)
    if not promotable:
        print("[OK]当前无满足阈值的同类失败聚类。")
        sys.exit(0)

    rules_dir = project_root / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    generated = []

    for category, entries in promotable.items():
        candidate_path = rules_dir / f"auto-{category}-{today}.md.candidate"
        content = CANDIDATE_TEMPLATE.format(
            category=category,
            count=len(entries),
            date_range=_date_range(entries),
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            summary_table=_format_summary_table(entries),
            raw_entries=_format_raw_entries(entries),
        )
        if args.dry_run:
            print(f"[DRY-RUN] 会生成: {candidate_path} ({len(entries)} 条)")
        else:
            candidate_path.write_text(content, encoding="utf-8")
            generated.append((candidate_path, len(entries)))
            print(f"[OK]生成 {candidate_path.relative_to(project_root)} ({len(entries)} 条)")

    if generated and not args.dry_run:
        print()
        print(f"已生成 {len(generated)} 个候选规则文件。")
        print("人工 review 后保留有价值的，改名（去掉 .candidate 后缀）即可生效。")
        print("丢弃的直接 rm 即可。")

if __name__ == "__main__":
    main()
