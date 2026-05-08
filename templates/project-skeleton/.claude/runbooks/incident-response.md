# 故障响应通用剧本（示例）

> 这是一份**示例文件**。请按你们实际的应急流程改写。

## 触发条件

满足任一即启动本剧本：
- 监控告警 (P0/P1)
- 用户大规模反馈
- 核心业务指标异常下跌 ≥ 30%

## 角色

- **IC (Incident Commander)** — 指挥，决定决策
- **OS (On-call Specialist)** — 执行，跑命令
- **CL (Communications Lead)** — 对外沟通（用户公告、群通知）

小公司可能 1 个人扮多角色，但角色分工是关键。

## 流程

### Step 1（≤ 2 min）：识别 + 上报

- [ ] OS 在监控面板确认告警真实（排除误报）
- [ ] OS 在 #incident 频道开新 thread：`P0/P1 - [一句话描述] - [开始时间]`
- [ ] IC 接手，宣布"接手"

### Step 2（≤ 5 min）：止损评估

IC 决策树：

```
影响范围 = ?
├─ 全站 → 立即切流量到 DR / 启用降级开关
├─ 部分用户 → 限流或熔断
└─ 单接口 → 暂停该接口 + 进入根因排查
```

参考具体场景剧本：
- 数据库不可用 → `runbooks/db-down.md`（按需新增）
- 接口延迟 → `runbooks/high-latency.md`（按需新增）

### Step 3（持续）：根因排查

OS 优先看：
1. **最近变更** — `git log --since="2 hours ago"`
2. **监控关联指标** — error rate / latency / traffic 同时异常？
3. **依赖服务** — 上游 / 下游有异常？

每 10 分钟在 #incident thread 同步一次进展。

### Step 4：恢复

- [ ] OS 执行修复 / 回滚
- [ ] OS 验证恢复（监控指标回到基线）
- [ ] IC 宣布 "Recovered"

### Step 5（≤ 24h）：事后

- [ ] CL 起草 user-facing post-mortem
- [ ] OS 起草内部 post-mortem (RCA)
- [ ] 团队会议过 RCA → 把教训写进相关 runbook + `pitfall-journal.jsonl`

## 决策红线

- 严禁在 P0 期间引入"未经验证的修复" — 只用已知方案
- 严禁单人决策上线 hot fix — 必须 IC 同意
- 严禁忽略告警继续部署其他变更 — 一切其他变更冻结

## 沟通模板

### 内部 #incident 起手

```
P0 - 订单接口 500 错误率 80%
开始时间: 14:23
影响范围: 所有用户
当前状态: 排查中
IC: @alice  OS: @bob  CL: @charlie
```

### 用户公告（恢复后）

```
我们注意到 14:23-14:45 期间订单接口出现异常，已于 14:45 恢复。
原因: [一句话]
影响: [范围]
已采取的措施: [一句话]
```

## 链接

- [`pitfall-journal.jsonl`](../pitfall-journal.jsonl) — 历史事故归档
- [`handbooks/deployment.md`](../handbooks/deployment.md) — 回滚步骤详见此处
