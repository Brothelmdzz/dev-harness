"""
Pitfall Journal — 踩坑日志读写 + 续跑前 ground truth 注入

B 阶段引入。来源：
  - 腾讯 LEGO 的 Pitfall Journal 闭环（详见 docs/external-references-2026-05.md 文章 3）
  - Anthropic Effective harnesses 的 "ground truth from environment" 思路
  - SESSION-HANDOFF.md P0.1 的"上下文注入器"设计

JSONL 结构（每行一条）:
  {
    "id": "PIT-YYYYMMDD-NNN",
    "occurred_at": "ISO 8601",
    "category": "build|test|runtime|deploy|review|other",
    "phase": "research|plan|implement|audit|test|review|other",
    "summary": "一句话描述",
    "root_cause": "根因（可选）",
    "resolution": "如何解决（可选）",
    "rule_candidate": false,
    "ab_tested": false
  }
"""
import json
from pathlib import Path
from datetime import datetime, timezone

from .utils import now_iso

PITFALL_FILE_REL = ".claude/pitfall-journal.jsonl"

# ==================== 路径 ====================

def get_pitfall_path(project_root):
    """返回项目下 pitfall-journal.jsonl 的绝对路径"""
    return Path(project_root) / PITFALL_FILE_REL

# ==================== 写入 ====================

def capture_failure(project_root, *, category, summary,
                    root_cause="", resolution="", phase="", extra=None):
    """记录一次失败到 pitfall-journal.jsonl

    Args:
        project_root: 项目根
        category: 'build' | 'test' | 'runtime' | 'deploy' | 'review' | 'other'
        summary: 一句话描述
        root_cause: 根因（可选）
        resolution: 如何解决（可选）
        phase: 当前 pipeline 阶段
        extra: 额外字段 dict（合并到条目）

    Returns:
        生成的条目 ID（PIT-YYYYMMDD-NNN）
    """
    path = get_pitfall_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    next_id = _next_id_for_date(path, today)

    entry = {
        "id": f"PIT-{today}-{next_id:03d}",
        "occurred_at": now_iso(),
        "category": category,
        "phase": phase,
        "summary": summary,
        "root_cause": root_cause,
        "resolution": resolution,
        "rule_candidate": False,
        "ab_tested": False,
    }
    if extra:
        entry.update(extra)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry["id"]

def _next_id_for_date(path, today):
    """统计当日已有 pitfall 条数，返回下一个序号"""
    if not path.exists():
        return 1
    count = 0
    target = f'"PIT-{today}-'
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                # 跳过元数据行（_comment / _schema），它们不会含 PIT- 前缀
                if target in line:
                    count += 1
    except OSError:
        return 1
    return count + 1

# ==================== 读取 ====================

def read_recent(project_root, max_recent=5):
    """读取最近 N 条 pitfall（自动跳过 _comment / _schema 元数据行）"""
    path = get_pitfall_path(project_root)
    if not path.exists():
        return []

    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # 跳过模板的元数据行
                if not isinstance(e, dict):
                    continue
                if "_comment" in e or "_schema" in e:
                    continue
                if "id" not in e:
                    continue
                entries.append(e)
    except OSError:
        return []

    return entries[-max_recent:] if max_recent > 0 else entries

# ==================== 续跑前的 ground truth 注入 ====================

def build_pitfall_context(project_root, max_recent=5):
    """构建注入下一轮 prompt 的 ground truth 字符串。

    返回 markdown 片段（已包含前导 \\n\\n），可直接拼接到 stop-hook 的 block reason 末尾。
    无 pitfall 时返回空串。
    """
    entries = read_recent(project_root, max_recent)
    if not entries:
        return ""

    lines = ["", "", "最近踩坑（避免重复同类错误）:"]
    for e in entries:
        cat = e.get("category", "?")
        summary = e.get("summary", "")
        root = e.get("root_cause", "")
        line = f"- [{cat}] {summary}"
        if root:
            line += f"（根因: {root}）"
        lines.append(line)

    return "\n".join(lines)

# ==================== 聚类（pitfall-analyze 用）====================

def cluster_by_category(project_root, *, include_ab_tested=False):
    """按 category 聚类未 A/B 验证过的失败。

    Args:
        include_ab_tested: 是否包含已经提炼成 rule 并 A/B 验证过的条目。
                           默认 False（只看未沉淀的）。
    """
    # 读全部（max_recent=0 含义切换为不限制）
    path = get_pitfall_path(project_root)
    if not path.exists():
        return {}

    clusters = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(e, dict) or "id" not in e:
                    continue
                if not include_ab_tested and e.get("ab_tested"):
                    continue
                cat = e.get("category", "other")
                clusters.setdefault(cat, []).append(e)
    except OSError:
        return {}

    return clusters

def find_promotable(project_root, threshold=3):
    """返回 {category: [entries...]}，仅含 ≥ threshold 条同类未提炼的失败"""
    clusters = cluster_by_category(project_root, include_ab_tested=False)
    return {cat: items for cat, items in clusters.items() if len(items) >= threshold}

__all__ = [
    "PITFALL_FILE_REL",
    "get_pitfall_path",
    "capture_failure",
    "read_recent",
    "build_pitfall_context",
    "cluster_by_category",
    "find_promotable",
]
