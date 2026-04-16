"""
Plan 解析 — 统一 parse_phases_from_plan（3→1）
"""
import re
from pathlib import Path

# Phase 标题正则：## Phase N / ### Task N / ## 阶段 N（支持中英文冒号和各种分隔符）
_PHASE_PATTERN = re.compile(
    r'^#{2,3}\s+(?:Phase|PHASE|Task|TASK|阶段|第)\s*(\d+)\s*(?:阶段)?\s*[：:.\-—]?\s*(.*?)$',
    re.MULTILINE | re.IGNORECASE,
)

def parse_phases(plan_text):
    """
    从 plan 文本解析 Phase 列表。

    Args:
        plan_text: plan 文件的完整文本内容

    Returns:
        list[dict]: [{"name": "Phase N: xxx", "status": "PENDING", "error_count": 0}, ...]
    """
    phases = []
    for m in _PHASE_PATTERN.finditer(plan_text):
        num = int(m.group(1))
        name = m.group(2).strip() or f"Phase {num}"
        phases.append({
            "name": f"Phase {num}: {name}" if name != f"Phase {num}" else name,
            "status": "PENDING",
            "error_count": 0,
        })
    return phases

def parse_phases_from_plan_dir(project_root):
    """
    从项目的最新 plan 文件解析 Phase 列表。

    Args:
        project_root: 项目根目录 Path

    Returns:
        list[dict]: Phase 列表（空 list 表示无 plan 或无 Phase）
    """
    plans_dir = Path(project_root) / ".claude" / "plans"
    if not plans_dir.exists():
        return []
    plan_files = sorted(plans_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not plan_files:
        return []
    text = plan_files[0].read_text(encoding="utf-8")
    return parse_phases(text)

__all__ = ["parse_phases", "parse_phases_from_plan_dir"]
