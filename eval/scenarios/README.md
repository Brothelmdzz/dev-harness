# Eval Scenarios

> **10 条真实任务场景**（目标 20），作为 dev-harness 改动（特别是 ABC 三件事）的**回归基线**。
> 跑前后的 pass_rate / token / time 对比，能客观回答"改动是变好还是变差"。
> 006-010 直接从 v3.4.x CHANGELOG 已修复 issue 反向沉淀，剩余 10 个见末尾 TODO。

## 与 trace-schema 的关系

- `eval/trace-schema.json` 是**结果** schema（`eval/results/*.json` 必须满足）
- `eval/scenarios/*.json` 是**输入**定义（本目录的文件）
- `eval/eval-runner.py` 读 scenario → 跑 dev-harness pipeline → 输出 trace

## Scenario JSON 字段

```jsonc
{
  "task_id": "scenario-NNN-slug",        // 唯一标识，与文件名对齐
  "task_source": "real-task",            // 与 trace-schema 一致
  "title": "短标题（中文 OK）",
  "description": "完整需求文字 — agent 收到的就是这个",
  "complexity": "small | medium | large",
  "expected_route": "B | A | C | C-lite | D",  // 期望走的 dev-harness 路线
  "expected_skills": ["..."],            // 期望命中的 skill 列表
  "expected_files_changed": ["..."],     // 改动文件路径（glob 也行）

  "reference_impl": {                    // 哲学原则 4 + 得物 Harness 思维
    "similar_files": ["..."],            // 仓库中相似已实现，AI 应模仿
    "related_rules": ["..."]             // 相关 rules/*.md 文件
  },

  "verification": {
    "command": "shell command",          // 跑通 = 通过
    "success_criteria": "human-readable" // exit 0 之外的额外要求
  },

  "rubric": {                            // LLM-as-Judge 评分用
    "must_pass": ["..."],                // 不达成 = 不通过
    "should_pass": ["..."],              // 达成加分
    "nice_to_have": ["..."]              // 锦上添花
  }
}
```

## 选择本批 5 条的理由

| ID | 任务 | 复杂度 | 测什么 |
|----|------|-------|-------|
| 001 | 给 `.claude/rules/` 新增一条规则 | small | C-lite 路线 + generic-implement 走通 |
| 002 | 给 `pitfall-analyze.py` 加 `--since` 参数 | medium | C 路线 + 完整 pipeline + B 阶段产物 |
| 003 | 写一条 SKILL.md ≤ 200 行的校验脚本 | medium | architect 视角（哲学红线） + generic-test |
| 004 | 修 Windows 下中文输出 GBK 编码问题 | small-medium | code-reviewer 视角 + cross-vendor 是否能找出 |
| 005 | 实现 `scripts/scaffold.sh --skeleton` 命令 | large | 完整 pipeline + C 阶段产物（project-skeleton 骨架） |
| 006 | 把 stop-hook RATE_LIMIT_KEYWORDS 换成严格 regex | small | C-lite + 误报修复（v3.4.4 HIGH-A） |
| 007 | web_hud.py SSE 加 1h 超时 + 15s 心跳 | medium | C + 资源泄漏修复（v3.4.4 MEDIUM-A） |
| 008 | pitfall `_next_id_for_date` 全文→tail 64KB 扫描 | small | C-lite + 性能 5000 条 ≤ 10ms（v3.4.4 MEDIUM-B） |
| 009 | v4.0 Gate Feedback Loop 闭环 | medium | C + 跨 3 文件 + 闭环验证（v3.4.3） |
| 010 | /dev 启动声明强制（防摆烂） | small | C-lite + SKILL.md 改写（v3.4.2） |

**为什么用 dev-harness 自身的任务**：
- 我们最了解领域，能精准评判产出质量
- 改完直接验证（不需要外部环境）
- 任务难度递增，能 cover 5 条路线中 4 条（B/A/C/C-lite）
- **006-010 直接从 v3.4.x CHANGELOG 已修复 issue 反向沉淀**——"做过的事自然成 baseline"

## TODO — 通往 20 scenario（剩 10）

按 [external-references-2026-05.md §四](../../docs/external-references-2026-05.md) P1.1 目标 "5 → 20"，已补 006-010。下批候选（按优先级，全部源自 CHANGELOG 真实修复）：

| 候选 ID | 任务 | 来源 |
|--------|------|------|
| 011 | TOCTOU race 修复（worker_status 单锁内 read+check+write） | v3.4.4 HIGH-C |
| 012 | RETRY 语义重置 phase.error_count + gates（防 RETRY 假性失败） | v3.4.4 HIGH-B |
| 013 | activity-watcher SENSITIVE_PATTERN 扩 10 敏感词（GitHub PAT/sk-/jwt 等） | v3.4.4 MEDIUM-E |
| 014 | hook_trace breadcrumb 加 PID 防并发覆盖 | v3.4.4 MEDIUM-C |
| 015 | Plan fallback 二态实现（wait/auto-approve/skip） | v3.4.2 |
| 016 | Stop-hook 软提醒分级（advisory → hard，stage 切换重置） | v3.4.2 |
| 017 | cross-vendor review — detect-codex 自动 enable + 投票汇总 | v3.4.1 |
| 018 | Pitfall candidate → rule 人工 promote 流程 | v3.4.1 |
| 019 | depends_on DAG 拓扑校验 + 环检测 | v3.4.0 |
| 020 | filelock 缺失检测（Orchestrator 启动前 fail-fast） | v3.4.0 |

## 跑回归

```bash
# 跑全部（默认 config: full）
python eval/eval-runner.py --scenarios eval/scenarios/ --config full

# 跑单条 + bare 对比（无 dev-harness）
python eval/eval-runner.py --scenarios scenario-001-add-rule.json \
  --config full --compare-bare

# 输出到 eval/results/<timestamp>/
```

## 维护原则

1. **真实任务 > 合成任务**：尽量用仓库已知待办，不要造假需求
2. **每个 scenario 跑过至少 1 次** 才入库（避免模板生硬）
3. **新增 scenario 必须包含 reference_impl** （哲学原则 4 + 得物 Harness 思维）
4. **不在此放敏感数据**：scenarios 公开，不含真实业务/客户信息
