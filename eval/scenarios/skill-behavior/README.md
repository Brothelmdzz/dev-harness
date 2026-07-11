# Skill Behavior Scenarios

> 技能**行为**回归，不是任务回归。与上级目录 `../*.json`（任务级 scenario）分工不同：
> 任务级 scenario 问的是"pipeline 能不能把一个真实任务跑完"（结果导向）；
> 本目录问的是"改一条 `description` 或防摆烂话术之后，agent 在压力下的行为
> 是否真的按预期变了"（行为导向，drill 式）。

## 为什么需要单独一层

`skills/**/SKILL.md` 的 `description`、启动声明、连续执行红线、完成契约这些话术，
本质是"给 agent 的行为指令"，不是"给 agent 的功能代码"——功能代码有单元测试，
这类指令过去完全没有回归手段：改一句话术，凭感觉觉得"应该会更好"，
从未验证过它在压力下（长任务、模糊指令、"要不要问一下用户"的诱惑）是否真的生效，
也从未验证过原来的话术是否真的存在被绕过的问题。

`scripts/dh-lint.py --check=skill-edit-evidence` 把这件事机械化：只要 diff 命中
`skills/**/SKILL.md` 的 `description` 行或连续执行/完成契约段，就要求本目录下
存在对应的 RED+GREEN 证据文件，否则 CI/PR 门禁 exit 1。

## 三个字段的角色分工（drill 结构）

| 字段 | 角色 |
|------|------|
| `system` | 被测 skill 的真实正文（通常是整份 `SKILL.md` 内容，不是摘要）|
| `user` | 诱发任务——刻意设计成容易让 agent 想走捷径/摆烂的场景 |
| `judge` | 一个独立的 LLM 裁判，对照 skill 声明的红线判断这次运行是否合规 |

## RED-GREEN-REFACTOR 流程

1. **RED（先证明问题真实存在）**：**不带**本次改动，跑 baseline ≥ 5 次，逐字
   记录每次的 rationalization / 失败模式。**如果 baseline 一次都没失败，说明
   这次改动要解决的是伪问题，应该驳回话术改动，而不是硬加更多话术**——
   这是 Iron Law（"NO SKILL WITHOUT A FAILING TEST FIRST"）对 EDIT 场景的
   落地，不只是对 NEW skill 适用。
2. **GREEN（证明改动真的起作用）**：应用改动后，同一 scenario 再跑 ≥ 5 次，
   确认全部合规。
3. **REFACTOR（堵住新漏洞）**：跑的过程中出现新的 rationalization 话术（agent
   换了个借口继续摆烂）→ 在 skill 正文补一条针对性反例 → 复跑直到稳定合规。
4. **落盘证据**：把 RED（≥5 条失败记录）和 GREEN（≥5 条合规记录）整理进
   `eval/results/<date>-<skill>-pressure.md`（`<skill>` 用 SKILL.md 的
   frontmatter `name` 字段，如 `dev-pipeline`）。`dh-lint.py` 只检查这个文件
   存在且非空，不做内容格式校验——记录格式自由，但必须是逐字/逐条的真实
   运行记录，不是复述结论。

对纯 wording 改动（没有新增结构化字段的场景），可以先跑更便宜的
**micro-test**：单次 fresh-context 运行 + no-guidance control 组 5 次，
人工逐条读每次命中——防止"模型只是复述了 prompt 里的反例模板"这种伪阳性。
方差收敛后再进入完整 RED-GREEN-REFACTOR。

## Scenario YAML 字段

```yaml
scenario_id: sb-NNN-slug          # 唯一标识，与文件名对齐
skill: <SKILL.md 的 frontmatter name>   # 被测技能，决定证据文件名里的 <skill>
title: 一句话说清诱发的是什么失败模式

system_file: skills/dev/SKILL.md  # 指向被测 SKILL.md 的仓库相对路径，
                                   # eval-runner 运行时读取其当前正文作为 system
                                   # prompt——不要把正文复制粘贴进本文件，
                                   # 那样 SKILL.md 一改这里就悄悄过期失真

user: |
  <诱发任务 prompt——刻意包含容易让 agent 想违反红线的措辞>

judge:
  must_not:                       # 出现任一条即判 fail
    - "..."
  must:                           # 全部出现才判 pass
    - "..."

baseline_runs: 5                  # RED 阶段跑几次
notes: 可选，记录这个 scenario 对应 skill 正文里的哪一段红线
```

## 维护原则

1. 每个 scenario 必须先跑出至少一次真实 RED 失败记录才能入库（同上级目录
   `../README.md` 原则 2 的精神，但这里验的是行为不是产出）
2. 一个 scenario 只诱发一种失败模式，不要图省事把多条红线塞进同一个 user prompt
3. `judge` 的 `must_not` / `must` 写成可由裁判从 transcript 直接判定的具体行为
   （如"输出了'是否继续'式提问"），不要写"表现得不专业"这类无法机械判定的标准
