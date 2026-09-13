# 5.0.0-alpha.2 团队版预发布

## 产品范围

让进入项目的 Agent 发现并遵循项目共享约定，按需使用现有能力，更新受影响的共享资料，留下可接续的结果。每个项目初始化自己的入口，四个 Skill 按任务使用。

项目任务平台、Git、知识工具、CI及宿主分别保有原事实与执行能力。本包不管理Session生命周期，不实现任务分配器、互斥锁、图引擎或合并队列。

## 验证范围

包引用、可移植性、来源摘要和拒绝覆盖等8项确定性检查通过；Plugin及四个Skill格式校验通过。已进行Sol/medium和Luna/max的新上下文小样，覆盖初始化、重复初始化、接手、中途决定更新、职责边界、候选检查及交接。平台合成验收验证过Issue/MR及隔离目标合并；不包含业务部署。

精确标识与验证数量可以依据原始回执核对，语义解释仍需审阅：一个Sol样本仍推断了证据不支持的时间顺序。因此本版是有限验证的预发布，不保证所有模型和任务的遵循率。Cloud、其他宿主的完整行为、生产CI/部署、真实图工具连接未全面验证。

## 安装与回退

```sh
codex plugin marketplace add Brothelmdzz/dev-harness --ref v5.0.0-alpha.2
codex plugin add dev-harness@dev-harness-team
codex plugin list --marketplace dev-harness-team --json
```

使用支持这些命令的Codex版本。安装后用新任务确认四个入口已发现；已有项目先明确请求初始化，复用原规则。历史版和团队版是不同marketplace入口；安装前保留原配置，仅启用需要的一套。

回退可通过宿主禁用团队版；确需移除时使用 `codex plugin remove dev-harness@dev-harness-team`。保留已生成的项目资料与工作成果，插件移除不等于资料应该删除。Claude manifest已经静态校验，但本次安装验证以Codex为准。
