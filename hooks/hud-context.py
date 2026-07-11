#!/usr/bin/env python3
"""
Dev Harness HUD Context Hook — PostToolUse 兜底注入通道

背景（r2-goal 缺口 3）:
  prompt 类型的 Stop 完成裁判只能读 transcript，看不见文件里的 pipeline 状态。
  主通道是 dev/SKILL.md 每个 stage 收尾主动跑 `harness.py hud`（stdout 落 transcript）。
  本 hook 是兜底：即使模型漏跑 hud，也在 `harness.py update` 之后强制把状态摘要注入。

机制:
  - PostToolUse 的 stdout 不进上下文，唯一进上下文的是 hookSpecificOutput.additionalContext
    （会被包成 system reminder 贴在 tool result 旁）。所以必须走 additionalContext 字段。
  - 只在 Bash 工具且命令含 "harness.py update" 时工作，避免污染普通 Bash 调用。

铁律: 全程 fail-safe，任何异常静默 exit 0，绝不阻塞工具调用；不 import harness.py（要快）。
"""
import json, sys
from pathlib import Path

# Windows GBK 控制台防御：摘要走 additionalContext（JSON 内 ensure_ascii=True，
# 本身 ASCII 安全），但 stderr/异常路径可能带非 ASCII，统一强制 UTF-8 兜底。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def find_state(start):
    """从 cwd 向上最多 6 层查找 .claude/harness-state.json"""
    try:
        p = Path(start).resolve()
    except Exception:
        return None
    for d in [p, *list(p.parents)][:6]:
        f = d / ".claude" / "harness-state.json"
        if f.exists():
            return f
    return None


def summarize(state):
    """生成紧凑 hud 摘要：一行一个 stage（纯 ASCII 箭头），附 gate 结果与 error_count"""
    lines = ["[dev-harness hud]"]
    for s in state.get("pipeline", []):
        name = s.get("name", "?")
        status = s.get("status", "PENDING")
        parts = [f"{name} -> {status}"]
        gate_bits = []
        # stage 级 gates
        for k, v in (s.get("gates") or {}).items():
            gate_bits.append(f"{k}={'pass' if v else 'FAIL'}")
        # phase 级 gates（implement 阶段 gate 挂在 phase 上，只强调失败项）
        phases = s.get("phases") or []
        if phases:
            done = sum(1 for p in phases if p.get("status") == "DONE")
            parts.append(f"({done}/{len(phases)} phases)")
            for p in phases:
                for k, v in (p.get("gates") or {}).items():
                    if not v:
                        gate_bits.append(f"{p.get('name', '?')}:{k}=FAIL")
        if gate_bits:
            parts.append("[" + " ".join(gate_bits) + "]")
        lines.append(" ".join(parts))
    error_count = state.get("metrics", {}).get("total_errors", 0)
    lines.append(f"error_count={error_count}")
    cur = state.get("current_stage", "")
    if cur:
        lines.append(f"current_stage={cur}")
    return "\n".join(lines)


def main():
    # ---- 读取 PostToolUse 输入 ----
    try:
        hook_input = json.loads(sys.stdin.read())
    except Exception:
        return

    # ---- 仅命中 Bash + "harness.py update" 才工作，否则静默放行 ----
    if hook_input.get("tool_name") != "Bash":
        return
    command = (hook_input.get("tool_input") or {}).get("command") or ""
    if "harness.py update" not in command:
        return

    # ---- 定位并读取 state ----
    state_file = find_state(hook_input.get("cwd") or ".")
    if not state_file:
        return
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        return

    # ---- 生成摘要并走 additionalContext 注入 ----
    try:
        summary = summarize(state)
    except Exception:
        return
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": summary,
        }
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 最外层兜底：任何未预期异常都不得阻塞工具调用
        pass
    sys.exit(0)
