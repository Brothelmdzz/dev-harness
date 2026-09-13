# Dev Harness 团队版

给各自使用 Codex、Claude Code 等工具的开发者一套共享协作约定。任务和责任仍在 GitLab/Multica 等现有平台，代码和候选在 Git，验证在 CI/制品/部署系统，Session 生命周期由宿主负责。

## 四个入口

| Skill | 使用时机 |
|---|---|
| [dev-harness-init](skills/dev-harness-init/SKILL.md) | 初始化项目地图，或只读核对接入缺项 |
| [dev-harness-work](skills/dev-harness-work/SKILL.md) | 接手任务、处理反馈、继续未完成工作 |
| [dev-harness-change](skills/dev-harness-change/SKILL.md) | 作者准备 MR，或独立审查指定候选 |
| [dev-harness-handoff](skills/dev-harness-handoff/SKILL.md) | 交给另一位开发者、Session、测试或运维 |

普通问答和不涉及协作的局部工作不需要完整流程。初始化只在用户请求时进行；这不是固定四阶段流水线。

## 本地构建与仓库分发

在本仓库根运行，Python 3.10+，只用标准库：

```sh
python scripts/team_plugin.py check plugins/dev-harness
python -m unittest discover -s tests/team_harness -v
python scripts/team_plugin.py package --output dist/dev-harness
python scripts/team_plugin.py package --format skills --output dist/repository-skills
```

输出目录须不存在，重建时换一个新目录。完整包包含四个 Skill 及全部材料；`repository-skills/.agents/skills/` 可由项目负责人按现有仓库流程纳入项目。它不是新的源码维护源，修改后应从本仓库重建。`provenance.json` 记录包版本、Git 起点、源码内容摘要与实际发布文件摘要；脏源码会明确标记，不能冒充发布提交。

本目录本身也是完整插件源码包。Codex/Claude 的 manifests 分开维护并验证，四个 Skill 正文共用。仓库 Skills 仅证明材料可移植，各宿主实际发现、策略和调用仍须验收。Codex 通过本仓库 `.agents/plugins/marketplace.json` 的 `dev-harness-team` 分发；安装命令和版本边界见根 README 与 [发布说明](RELEASE.md)。

## 项目接入

请 Agent “初始化本项目的 Dev Harness 协作约定”。它读取已有资料，复用现成入口，必要时生成 `.dev-harness/project.md` 并在现有 AGENTS.md/CLAUDE.md 加一条短引用。[模板](templates/project-map.md)列出所需信息；未知保持未知，后续按工作补全。

项目工具只登记能力和已有用法。GitLab、飞书、Multica、CodeGraph 等未安装时，明确缺口；普通启动不会安装工具或首次建索引。凭证留在各自环境。插件不实现锁；assignee、标签和本地文件都不能证明跨机器原子认领。

## 源码组织与迁移

`skills/` 是四个入口，`references/` 是共享规则唯一源码，`templates/` 是项目地图。入口使用相对路径。打包器把引用放到每个 Skill 内并改写路径，使单个目录也可移动。

仓库根目录仍是旧版 v4，不要把根目录与本包混装。团队版没有 hooks、agents、固定模型、流水线状态或后台调度。保留原安装，选定新包后再通过宿主管理切换，不同时运行两套默认工作流。
