"""Dev Harness Skill 自进化建议（实验性） — 分析评测历史，找出持续低分维度并输出改进建议"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

# Windows 控制台可能不支持 UTF-8，强制 stdout 使用 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ==================== 配置 ====================

EVAL_RESULTS_DIR = Path(__file__).resolve().parent.parent / "eval" / "results"
LOW_SCORE_THRESHOLD = 80  # 百分比
CONSECUTIVE_THRESHOLD = 3  # 连续几次低分触发告警


# ==================== 数据加载 ====================

def find_eval_files():
    """按时间排序发现所有 eval-*.json 文件"""
    if not EVAL_RESULTS_DIR.is_dir():
        return []
    files = sorted(EVAL_RESULTS_DIR.glob("eval-*.json"))
    return files


def load_eval(filepath):
    """加载单个评测结果文件"""
    try:
        return json.loads(filepath.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        # fallback: 尝试系统默认编码
        try:
            return json.loads(filepath.read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            return None
    except (json.JSONDecodeError, OSError):
        return None


def calc_metric_score(metric_result):
    """计算单个维度的得分百分比"""
    tests = metric_result.get("results", [])
    if not tests:
        # 有 error 字段说明维度执行失败
        if metric_result.get("error"):
            return None  # 区分"0分"和"执行失败"
        return None

    passed = sum(1 for t in tests if t.get("pass"))
    return round(passed / len(tests) * 100)


# ==================== 分析引擎 ====================

def build_timeline(eval_files):
    """构建每个维度的时间线得分序列

    返回: { metric_name: [(timestamp, score), ...] }
    """
    timeline = {}

    for filepath in eval_files:
        data = load_eval(filepath)
        if not data:
            continue

        timestamp = data.get("timestamp", filepath.stem)

        for result in data.get("results", []):
            metric = result.get("metric", "unknown")
            score = calc_metric_score(result)

            if metric not in timeline:
                timeline[metric] = []
            timeline[metric].append({
                "timestamp": timestamp,
                "score": score,
                "error": result.get("error"),
                "file": filepath.name,
            })

    return timeline


def find_weak_metrics(timeline, threshold=None, consecutive=None):
    """找出连续 N 次低于阈值的维度"""
    threshold = threshold if threshold is not None else LOW_SCORE_THRESHOLD
    consecutive = consecutive if consecutive is not None else CONSECUTIVE_THRESHOLD
    weak = []

    for metric, entries in timeline.items():
        # 只看最近的 N 个有效得分
        valid = [e for e in entries if e["score"] is not None]
        if len(valid) < consecutive:
            continue

        recent = valid[-consecutive:]
        if all(e["score"] < threshold for e in recent):
            avg_score = sum(e["score"] for e in recent) / len(recent)
            weak.append({
                "metric": metric,
                "recent_scores": [e["score"] for e in recent],
                "avg_score": round(avg_score),
                "trend": _calc_trend(valid),
                "last_file": recent[-1]["file"],
            })

    # 找出持续报错（执行失败）的维度
    for metric, entries in timeline.items():
        recent = entries[-consecutive:] if len(entries) >= consecutive else []
        if recent and all(e["score"] is None and e.get("error") for e in recent):
            weak.append({
                "metric": metric,
                "recent_scores": [],
                "avg_score": 0,
                "trend": "broken",
                "error": recent[-1]["error"],
                "last_file": recent[-1]["file"],
            })

    return weak


def _calc_trend(entries):
    """计算得分趋势：improving / declining / flat"""
    if len(entries) < 2:
        return "flat"
    scores = [e["score"] for e in entries if e["score"] is not None]
    if len(scores) < 2:
        return "flat"
    recent_half = scores[len(scores)//2:]
    early_half = scores[:len(scores)//2]
    avg_recent = sum(recent_half) / len(recent_half)
    avg_early = sum(early_half) / len(early_half)
    diff = avg_recent - avg_early
    if diff > 5:
        return "improving"
    if diff < -5:
        return "declining"
    return "flat"


# ==================== 建议生成 ====================

# 维度 → 改进建议映射
IMPROVEMENT_HINTS = {
    "skill_resolution": [
        "检查 defaults/skill-map.yml 别名候选列表是否完整",
        "确认 L1/L2 层的 Skill 目录结构是否符合 skill-resolver.py 的匹配规则",
        "添加更多 alias 条目覆盖边缘 case",
    ],
    "state_management": [
        "审查 harness.py 中 load_and_update_state 的原子性",
        "确认 FileLock 在多 Agent 场景下正常工作",
        "检查 state schema 迁移兼容性",
    ],
    "auto_continue": [
        "检查 stop-hook.py 的 six-defense 逻辑是否漏判",
        "确认 cmd_check_continue 对各阶段的覆盖是否完整",
        "验证 phase 进度检测在 phases 为空时的 fallback 行为",
    ],
    "gate_detection": [
        "检查 detect-stack.sh 对新语言/框架的支持",
        "确认 monorepo 场景下多技术栈检测是否正确",
    ],
    "pipeline_routing": [
        "检查 ROUTE_STAGES 定义是否与 pipeline.yml 一致",
        "确认新增路线的阶段跳过逻辑",
    ],
    "hook_defense": [
        "审查 stop-hook.py 六道防线的阈值配置",
        "检查滑动窗口频率限制的时间窗口是否合理",
        "确认 rate limit 检测逻辑是否跟上 API 变更",
    ],
    "session_isolation": [
        "检查 session_id 匹配逻辑在 stop-hook.py 中的实现",
        "确认多 session 并行场景的隔离测试",
        "验证 session 索引清理策略",
    ],
    "skill_override": [
        "检查三层 Skill 解析的优先级是否正确（L1 > L2 > L3）",
        "确认项目级 Skill 覆盖内置 Skill 的 test case",
    ],
    "parallel_group": [
        "审查并行组推进逻辑（cmd_update 中的 C2）",
        "确认 FAILED 状态对并行组其他 PENDING 阶段的影响",
    ],
    "worker_management": [
        "检查 worker JSON 文件的读写竞态保护",
        "确认 worker-cleanup 在异常退出时的清理逻辑",
    ],
    "plan_watcher": [
        "检查 plan-watcher.py 对 Write/Edit 事件的监听覆盖率",
        "确认 Phase 标题解析正则的鲁棒性",
    ],
    "phases_fallback": [
        "检查 stop-hook.py 中 phases 为空时的 fallback 解析逻辑",
        "确认从 plan 文件解析 phases 的正则匹配",
        "添加更多 plan 格式的 edge case 测试",
    ],
}

DEFAULT_HINTS = [
    "检查评测场景定义是否与最新代码同步",
    "确认该维度的 eval scenario 能正确运行（无 error）",
    "尝试在 eval/scenarios/ 中增加更多边界条件的测试",
]


def generate_suggestions(weak_metrics):
    """为低分维度生成改进建议"""
    suggestions = []

    for wm in weak_metrics:
        metric = wm["metric"]
        hints = IMPROVEMENT_HINTS.get(metric, DEFAULT_HINTS)
        trend_text = {
            "improving": "趋势好转中",
            "declining": "持续恶化",
            "flat": "持平",
            "broken": "执行报错",
        }.get(wm["trend"], "未知")

        suggestion = {
            "metric": metric,
            "severity": "CRITICAL" if wm["avg_score"] < 50 or wm["trend"] == "broken" else "WARNING",
            "avg_score": wm["avg_score"],
            "recent_scores": wm["recent_scores"],
            "trend": trend_text,
            "hints": hints,
        }
        if wm.get("error"):
            suggestion["error"] = wm["error"]

        suggestions.append(suggestion)

    return suggestions


# ==================== 输出格式化 ====================

def format_report(suggestions, timeline, threshold=None, consecutive=None):
    """格式化为可读的文本报告"""
    threshold = threshold if threshold is not None else LOW_SCORE_THRESHOLD
    consecutive = consecutive if consecutive is not None else CONSECUTIVE_THRESHOLD
    lines = []
    lines.append("=" * 60)
    lines.append("  Dev Harness Skill 自进化建议（实验性）")
    lines.append("=" * 60)
    lines.append("")

    eval_count = max((len(entries) for entries in timeline.values()), default=0)
    metric_count = len(timeline)
    lines.append(f"分析范围: {eval_count} 次评测, {metric_count} 个维度")
    lines.append(f"告警阈值: 连续 {consecutive} 次 < {threshold}%")
    lines.append("")

    if not suggestions:
        lines.append("所有维度表现正常，暂无改进建议。")
        lines.append("")
        # 显示维度概览
        lines.append("维度概览:")
        for metric, entries in sorted(timeline.items()):
            valid = [e for e in entries if e["score"] is not None]
            if valid:
                latest = valid[-1]["score"]
                lines.append(f"  {metric}: {latest}%")
            else:
                lines.append(f"  {metric}: N/A (执行失败)")
        return "\n".join(lines)

    lines.append(f"发现 {len(suggestions)} 个需要改进的维度:")
    lines.append("")

    for i, s in enumerate(suggestions, 1):
        lines.append(f"--- [{s['severity']}] {s['metric']} ---")
        if s.get("error"):
            lines.append(f"  错误: {s['error']}")
        else:
            scores_str = " -> ".join(str(x) + "%" for x in s["recent_scores"])
            lines.append(f"  最近得分: {scores_str}")
            lines.append(f"  平均: {s['avg_score']}% | 趋势: {s['trend']}")
        lines.append(f"  改进建议:")
        for hint in s["hints"]:
            lines.append(f"    - {hint}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("注意: 以上建议仅供参考，不会自动修改任何 SKILL.md 文件")
    lines.append("=" * 60)

    return "\n".join(lines)


# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Dev Harness Skill 自进化建议")
    parser.add_argument("--threshold", type=int, default=LOW_SCORE_THRESHOLD,
                        help=f"低分阈值百分比（默认 {LOW_SCORE_THRESHOLD}）")
    parser.add_argument("--consecutive", type=int, default=CONSECUTIVE_THRESHOLD,
                        help=f"连续低分次数（默认 {CONSECUTIVE_THRESHOLD}）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--eval-dir", default=None,
                        help="指定评测结果目录（默认 eval/results/）")
    args = parser.parse_args()

    threshold = args.threshold
    consecutive = args.consecutive
    eval_dir = Path(args.eval_dir) if args.eval_dir else EVAL_RESULTS_DIR

    eval_files = sorted(eval_dir.glob("eval-*.json")) if eval_dir.is_dir() else []
    if not eval_files:
        print("未找到评测结果文件", file=sys.stderr)
        sys.exit(1)

    timeline = build_timeline(eval_files)
    if not timeline:
        print("评测结果为空", file=sys.stderr)
        sys.exit(1)

    weak = find_weak_metrics(timeline, threshold=threshold, consecutive=consecutive)
    suggestions = generate_suggestions(weak)

    if args.json:
        print(json.dumps(suggestions, ensure_ascii=False, indent=2))
    else:
        print(format_report(suggestions, timeline, threshold, consecutive))


if __name__ == "__main__":
    main()
