"""
Pipeline DAG 调度 — 统一 find_next / validate_dag / _has_depends_on（2→1）
"""

def has_depends_on(pipeline):
    """检测 pipeline 中是否有任何 stage 定义了 depends_on"""
    return any(s.get("depends_on") for s in pipeline)

def find_next_by_deps(pipeline, completed_name=None):
    """基于 depends_on 找所有依赖已满足的 PENDING 阶段。
    如果指定了 completed_name，优先返回直接依赖它的阶段（前向推进）。"""
    done_names = {s["name"] for s in pipeline if s["status"] in ("DONE", "SKIP")}
    runnable = [s["name"] for s in pipeline
                if s["status"] == "PENDING"
                and all(d in done_names for d in s.get("depends_on", []))]
    if not runnable:
        return []
    # 优先返回直接依赖刚完成阶段的（前向推进，不回退）
    if completed_name:
        direct = [n for n in runnable
                  if completed_name in next(
                      (s.get("depends_on", []) for s in pipeline if s["name"] == n), []
                  )]
        if direct:
            return direct
    return runnable

def find_next_by_order(pipeline, current_name):
    """旧逻辑：基于数组顺序找下一个 PENDING（兼容无 depends_on 的 pipeline）"""
    found = False
    for s in pipeline:
        if s["name"] == current_name:
            found = True
            continue
        if not found:
            continue
        if s.get("status") != "PENDING":
            continue
        group = s.get("parallel_group")
        if group:
            return [ps["name"] for ps in pipeline
                    if ps.get("parallel_group") == group
                    and ps.get("status") == "PENDING"]
        return [s["name"]]
    return []

def find_next_runnable(pipeline, current_name):
    """找到下一组可执行的阶段——优先用 depends_on DAG，否则走旧的顺序逻辑"""
    if has_depends_on(pipeline):
        return find_next_by_deps(pipeline, completed_name=current_name)
    return find_next_by_order(pipeline, current_name)

def validate_dag(pipeline):
    """校验 depends_on 是否形成合法 DAG（无循环、无悬空引用）"""
    if not has_depends_on(pipeline):
        return  # 旧格式，跳过
    names = {s["name"] for s in pipeline}
    for s in pipeline:
        for dep in s.get("depends_on", []):
            if dep not in names:
                raise ValueError(f"Stage '{s['name']}' depends_on unknown stage '{dep}'")
    # 拓扑排序检测循环
    in_degree = {s["name"]: len(s.get("depends_on", [])) for s in pipeline}
    adj = {}
    for s in pipeline:
        for dep in s.get("depends_on", []):
            adj.setdefault(dep, []).append(s["name"])
    queue = [n for n, d in in_degree.items() if d == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if visited != len(in_degree):
        raise ValueError("Pipeline DAG has cycle")

def pipeline_is_terminal(pipeline):
    """检查 pipeline 是否已结束（无 PENDING/IN_PROGRESS 阶段）"""
    return not any(s.get("status") in ("PENDING", "IN_PROGRESS") for s in pipeline)

__all__ = [
    "has_depends_on", "find_next_by_deps", "find_next_by_order",
    "find_next_runnable", "validate_dag", "pipeline_is_terminal",
]
