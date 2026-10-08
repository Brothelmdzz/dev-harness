# Dev Harness 团队版

让不同开发者及其多个 Agent 依据项目当前有效的约定接手、推进和交接工作，减少对原作者私人会话的依赖。任务和责任仍在 GitLab/Multica 等现有平台，代码和候选在 Git，验证在 CI/制品/部署系统，Session 生命周期由宿主负责。

## 四个入口

| Skill | 使用时机 |
|---|---|
| [dev-harness-init](skills/dev-harness-init/SKILL.md) | 初始化项目地图，或只读核对接入缺项 |
| [dev-harness-work](skills/dev-harness-work/SKILL.md) | 接手任务、处理反馈、继续未完成工作 |
| [dev-harness-change](skills/dev-harness-change/SKILL.md) | 作者准备 MR，或独立审查指定候选 |
| [dev-harness-handoff](skills/dev-harness-handoff/SKILL.md) | 交给另一位开发者、Session、测试或运维 |

普通问答和不涉及协作的局部工作不需要完整流程。初始化只在用户请求时进行；这不是固定四阶段流水线。

已有任务/MR 足以接续时直接引用，只补变化与缺项。收到新决定后核对它替代了什么、影响哪些在途工作。普通本地接续无需导出快照；只有跨环境传递或固定未提交评审范围时，才按项目需要准备可取得的候选。交接材料备妥与接收者已实际接续分别报告。

跨环境需要结构化绑定时，可使用[薄回执模板](templates/continuation-receipt.md)连接现有任务、责任来源、写入范围、有效决定版本、候选、证据和下一动作。它不另建任务库，不要求每轮填表；关键事实未知时保留文字交接，不能用假值凑成通过。公开模板只含合成数据，真实项目回执留在私有环境。

v1 校验器 `scripts/team_receipt.py` 与同目录 `team_receipt.schema.json` 仅随源码仓库分发，不包含在 plugin / repository-skills 安装包内。项目按需取得这一工具，不要求普通接手安装。它只检查所给 receipt、context 和 peer 快照的一致性；exit 0 的 `consistent` 不证明来源真实/最新、证据命令通过、原子认领或接收者已接续。用法与限制见模板。

## 本地构建与仓库分发

在本仓库根运行，Python 3.10+，只用标准库：

```sh
python scripts/team_plugin.py check plugins/dev-harness
python -m unittest discover -s tests/team_harness -v
python scripts/team_plugin.py package --output dist/dev-harness
python scripts/team_plugin.py package --format skills --output dist/repository-skills
```

输出目录须不存在，重建时换一个新目录。完整包包含四个 Skill 及全部材料；`repository-skills/.agents/skills/` 可由项目负责人按现有仓库流程纳入项目。它不是新的源码维护源，修改后应从本仓库重建。`provenance.json` 记录包版本、Git 起点、源码内容摘要与实际发布文件摘要；脏源码会明确标记，不能冒充发布提交。

本目录本身也是完整插件源码包。Codex/Claude 的 manifests 分开维护并验证，四个 Skill 正文共用。Codex 团队版通过独立 `dev-harness-team` marketplace 预发布，安装及各版本验证范围见 [GitHub 发布记录](https://github.com/Brothelmdzz/dev-harness/releases)。其他宿主仍须分别验收；结构检查或单次行为小样不证明团队效率收益。

## 项目接入

需要落地入口时，明确调用 `dev-harness-init`：“初始化本项目的 Dev Harness 协作约定”。它读取已有资料，复用现成入口，必要时生成 `.dev-harness/project.md` 并在现有 AGENTS.md/CLAUDE.md 加一条短引用；从宿主入口能找到任务、有效决定与验证资料后，才报告本地入口就绪。[模板](templates/project-map.md)列出所需信息；未知保持未知，后续按工作补全。

只想检查时，使用：“只读核对本项目的 Dev Harness 接入现状，列出缺项，不修改文件”。核对不会被报成初始化完成。普通“使用 Dev Harness 完成任务”复用现有约定，缺少入口时报告缺项并继续可独立完成的工作。

项目工具只登记实际需要的能力和已有用法。GitLab、飞书、Multica、CodeGraph 都是可选来源，未采用本身不是缺口；只有妨碍当前接手时说明影响。普通启动不会安装工具或首次建索引。凭证留在各自环境。插件不实现锁；assignee、标签和本地文件都不能证明跨机器原子认领。

## 源码组织与迁移

`skills/` 是四个入口，`references/` 是共享规则唯一源码，其中 `local-candidate.md` 仅用于未提交候选的传递；`templates/` 是按项目裁剪的地图与可选回执参考。入口使用相对路径。打包器把引用放到每个 Skill 内并改写路径，使单个目录也可移动。

仓库根目录仍是旧版 v4，不要把根目录与本包混装。团队版没有 hooks、agents、固定模型、流水线状态或后台调度。保留原安装，选定新包后再通过宿主管理切换，不同时运行两套默认工作流。
