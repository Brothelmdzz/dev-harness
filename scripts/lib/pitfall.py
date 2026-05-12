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
from .compat import FileLock

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

    # v3.4.4 CRITICAL fix：加 FileLock 防止并发写入导致 jsonl 损坏。
    # v3.4.3 把入口数量翻倍（cmd_update --gate fail + stop-hook 已有 audit/review capture），
    # 抬高并发触发概率（Windows append 无原子保证、POSIX 只在 < PIPE_BUF 4096B 内原子）。
    # next_id 计算和 write 必须在同一把锁内，否则两个并发 capture 会拿到同一个 id。
    lock = FileLock(str(path) + ".lock", timeout=3)
    with lock:
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
    """统计当日已有 pitfall 条数，返回下一个序号。

    v3.4.4 MEDIUM-B fix：原先每次 capture 都全文扫描 jsonl，长期累积 N 条 → O(N²)。
    改为只读末尾 64KB 抓最大 NNN——当日条数 << 64KB / 200 bytes/line = 300 行，远够。
    用正则提取 "PIT-{today}-NNN" 后的数字，取 max + 1。
    解决 LOW-A 同款：原 `target in line` 子串匹配会被 root_cause 里引用历史 PIT-ID 干扰，
    新版用正则精确匹配 id 字段位置（PIT-YYYYMMDD-NNN 后必接非数字）。
    """
    if not path.exists():
        return 1
    import re as _re
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)  # 文件末尾
            size = f.tell()
            read_size = min(size, 64 * 1024)
            f.seek(size - read_size)
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return 1
    nums = _re.findall(rf'"id"\s*:\s*"PIT-{today}-(\d{{3,}})"', tail)
    if not nums:
        return 1
    return max(int(n) for n in nums) + 1

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

    v3.4.4 HIGH-2 fix：按 (category, root_cause/summary) 去重——避免同 gate 反复 fail
    时 5 条同质 pitfall 占满窗口、稀释多样性。最新优先保留，恢复时间顺序后输出。
    """
    # 读全部 pitfall（read_recent 内部 max_recent=0 表示不限制）
    all_entries = read_recent(project_root, max_recent=0)
    if not all_entries:
        return ""

    # 反向遍历（最新优先），按 (category, root_cause/summary 前 200 字) 作 key 去重
    # 取 root_cause 优先，fallback 到 summary，避免根因相同但表面措辞不同被误判为多样性
    seen = set()
    deduped = []
    for e in reversed(all_entries):
        dedup_text = (e.get("root_cause") or e.get("summary", "") or "")[:200]
        key = (e.get("category", ""), dedup_text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
        if len(deduped) >= max_recent:
            break
    entries = list(reversed(deduped))  # 恢复时间顺序（旧→新）

    if not entries:
        return ""

    lines = ["", "", "最近踩坑（避免重复同类错误）:"]
    for e in entries:
        cat = e.get("category", "?")
        summary = (e.get("summary", "") or "").strip()
        root = (e.get("root_cause", "") or "").strip()
        line = f"- [{cat}] {summary}"
        # v3.4.3 去重：summary 经常是 root_cause 的截断前缀（cmd_update 取 detail.split('\n',1)[0][:160] 做 summary、完整 detail 做 root_cause）。
        # 如果两者完全相同或互为前缀，不重复输出"（根因: ...）"，避免稀释信号占 prompt 空间。
        # root_cause 过长时截断到 200 字符——完整 stack trace 应该让 Claude 自己读日志，不是塞进 block reason。
        if root and root != summary and not summary.startswith(root) and not root.startswith(summary):
            truncated = (root[:200].rstrip() + "…") if len(root) > 200 else root
            line += f"（根因: {truncated}）"
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
