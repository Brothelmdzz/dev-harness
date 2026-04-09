"""Dev Harness 团队看板 — 汇总所有活跃项目的 pipeline 状态"""
import argparse
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Windows 控制台可能不支持 UTF-8，强制 stdout 使用 UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ==================== 数据源 ====================

SESSION_INDEX = Path.home() / ".claude" / "dev-harness-sessions.json"


def load_session_index():
    """读取中央 session 索引"""
    if SESSION_INDEX.exists():
        try:
            return json.loads(SESSION_INDEX.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_state(project_path):
    """读取指定项目的 harness-state.json"""
    state_file = Path(project_path) / ".claude" / "harness-state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def discover_projects():
    """从中央索引 + fallback 扫描发现所有有 harness 状态的项目"""
    projects = {}  # path_str -> state

    # 1. 从中央 session 索引读取
    index = load_session_index()
    for sid, info in index.items():
        proj_path = info.get("project", "")
        if proj_path and proj_path not in projects:
            state = load_state(proj_path)
            if state:
                projects[proj_path] = state

    # 2. Fallback: 扫描常见目录
    scan_roots = []
    home = Path.home()
    if os.name == "nt":
        scan_roots.append(Path("C:/work"))
    scan_roots.extend([home / "work", home / "projects", home / "dev"])

    for root in scan_roots:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if not d.is_dir():
                continue
            path_str = str(d)
            if path_str not in projects:
                state = load_state(path_str)
                if state:
                    projects[path_str] = state

    return projects


# ==================== 分析逻辑 ====================

def calc_progress(pipeline):
    """计算 pipeline 进度百分比"""
    active = [s for s in pipeline if s.get("status") != "SKIP"]
    if not active:
        return 0
    done = sum(1 for s in active if s.get("status") == "DONE")
    return round(done / len(active) * 100)


def calc_elapsed(started_at):
    """计算从 started_at 到现在的耗时"""
    if not started_at:
        return "N/A"
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - start
        total_min = int(delta.total_seconds() / 60)
        if total_min < 60:
            return f"{total_min}min"
        hours = total_min // 60
        mins = total_min % 60
        return f"{hours}h{mins}min" if mins else f"{hours}h"
    except (ValueError, TypeError):
        return "N/A"


def get_status_indicator(state):
    """根据 pipeline 状态返回状态指示符和文字"""
    pipeline = state.get("pipeline", [])
    paused = state.get("paused", False)

    if paused:
        return "\u26a0\ufe0f", "暂停"  # warning sign

    failed = any(s.get("status") == "FAILED" for s in pipeline)
    if failed:
        return "\u274c", "失败"  # red X

    all_done = all(s.get("status") in ("DONE", "SKIP") for s in pipeline)
    if all_done:
        return "\u2705", "完成"  # green check

    in_progress = any(s.get("status") == "IN_PROGRESS" for s in pipeline)
    if in_progress:
        return "\U0001f7e2", "运行中"  # green circle

    return "\u23f3", "等待中"  # hourglass


def get_stage_progress(state):
    """获取当前阶段的进度描述（如 implement 3/5）"""
    current = state.get("current_stage", "")
    if not current:
        return "已结束"

    pipeline = state.get("pipeline", [])
    stage = next((s for s in pipeline if s["name"] == current), None)
    if not stage:
        return current

    # implement 阶段显示 phase 进度
    phases = stage.get("phases", [])
    if phases:
        done_count = sum(1 for p in phases if p.get("status") == "DONE")
        return f"{current} ({done_count}/{len(phases)})"

    return current


def classify_projects(projects):
    """将项目分为活跃和已完成两组"""
    active = []
    completed = []

    for path_str, state in projects.items():
        pipeline = state.get("pipeline", [])
        all_done = all(s.get("status") in ("DONE", "SKIP") for s in pipeline)
        has_failed = any(s.get("status") == "FAILED" for s in pipeline)

        entry = {
            "path": path_str,
            "name": Path(path_str).name,
            "state": state,
        }

        if all_done or has_failed:
            completed.append(entry)
        else:
            active.append(entry)

    return active, completed


# ==================== Markdown 生成 ====================

def generate_report(projects):
    """生成 Markdown 格式团队看板"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Dev Harness 团队看板",
        f"> 生成时间: {now}",
        "",
    ]

    if not projects:
        lines.append("_未发现任何 harness 项目_")
        return "\n".join(lines)

    active, completed = classify_projects(projects)

    # ==================== 活跃项目 ====================
    lines.append("## 活跃项目")
    lines.append("")

    if active:
        lines.append("| 项目 | 任务 | 当前阶段 | 进度 | 运行时长 | 状态 |")
        lines.append("|------|------|---------|------|---------|------|")

        for entry in active:
            state = entry["state"]
            task = state.get("task", {})
            pipeline = state.get("pipeline", [])
            metrics = state.get("metrics", {})

            name = entry["name"]
            task_name = task.get("name", "-")
            stage_progress = get_stage_progress(state)
            pct = calc_progress(pipeline)
            elapsed = calc_elapsed(task.get("started_at", ""))
            icon, status_text = get_status_indicator(state)

            lines.append(
                f"| {name} | {task_name} | {stage_progress} | {pct}% | {elapsed} | {icon} {status_text} |"
            )
        lines.append("")
    else:
        lines.append("_当前无活跃项目_")
        lines.append("")

    # ==================== 最近完成 ====================
    lines.append("## 最近完成")
    lines.append("")

    if completed:
        lines.append("| 项目 | 任务 | 完成时间 | 总耗时 | 自动续跑 | 状态 |")
        lines.append("|------|------|---------|--------|---------|------|")

        for entry in completed:
            state = entry["state"]
            task = state.get("task", {})
            pipeline = state.get("pipeline", [])
            metrics = state.get("metrics", {})

            name = entry["name"]
            task_name = task.get("name", "-")
            auto_continues = metrics.get("auto_continues", 0)
            icon, status_text = get_status_indicator(state)

            # 找最后完成的阶段的时间
            completed_times = [
                s.get("completed_at", "")
                for s in pipeline if s.get("completed_at")
            ]
            last_done = max(completed_times) if completed_times else ""
            done_display = last_done.replace("T", " ").replace("Z", "") if last_done else "-"

            elapsed = calc_elapsed(task.get("started_at", ""))

            lines.append(
                f"| {name} | {task_name} | {done_display} | {elapsed} | {auto_continues} 次 | {icon} {status_text} |"
            )
        lines.append("")
    else:
        lines.append("_暂无已完成项目_")
        lines.append("")

    # ==================== 汇总统计 ====================
    lines.append("## 汇总")
    lines.append("")
    total_errors = sum(
        p["state"].get("metrics", {}).get("total_errors", 0)
        for p in active + completed
    )
    total_auto_fixed = sum(
        p["state"].get("metrics", {}).get("auto_fixed", 0)
        for p in active + completed
    )
    lines.append(f"- 总项目数: {len(projects)}")
    lines.append(f"- 活跃: {len(active)} | 已完成: {len(completed)}")
    lines.append(f"- 累计错误: {total_errors} | 自动修复: {total_auto_fixed}")
    lines.append("")

    return "\n".join(lines)


# ==================== CLI 入口 ====================

def main():
    parser = argparse.ArgumentParser(description="Dev Harness 团队看板")
    parser.add_argument("--output", "-o", default=None, help="输出到文件（默认 stdout）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式而非 Markdown")
    args = parser.parse_args()

    projects = discover_projects()

    if args.json:
        # JSON 格式输出（供程序化消费）
        data = []
        for path_str, state in projects.items():
            task = state.get("task", {})
            pipeline = state.get("pipeline", [])
            metrics = state.get("metrics", {})
            icon, status_text = get_status_indicator(state)
            data.append({
                "project": Path(path_str).name,
                "path": path_str,
                "task": task.get("name", ""),
                "current_stage": get_stage_progress(state),
                "progress": calc_progress(pipeline),
                "elapsed": calc_elapsed(task.get("started_at", "")),
                "status": status_text,
                "metrics": metrics,
            })
        report = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        report = generate_report(projects)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"报告已保存到: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
