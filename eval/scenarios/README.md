# Eval Scenarios

> 5 条真实任务场景，作为 dev-harness 改动（特别是 ABC 三件事）的**回归基线**。
> 跑前后的 pass_rate / token / time 对比，能客观回答"改动是变好还是变差"。

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

**为什么用 dev-harness 自身的任务**：
- 我们最了解领域，能精准评判产出质量
- 改完直接验证（不需要外部环境）
- 任务难度递增，能 cover 5 条路线中 3 条

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
