# 可选薄回执

已有任务/MR 足够接续就直接引用。普通同机接续核对原工作区；仅在跨环境需要结构化绑定时使用本模板，不逐轮填表。回执连接现有事实，不替代任务来源、候选制品或原始证据，也不提供锁和调度。

以下按冻结 v1 合同（实现候选 `668aeddd1bdb34d4d164a0073d32c5315dd2da97`）说明。所有仓库、任务、Session、来源、SHA 与证据均为合成值，只供输入合同演示，不能用于真实项目交接。真实项目回执留在私有验收环境。

## 来源与未知

由现有任务/分配来源取得 `task_id`、`revision`、负责 Session、state 和 ownership；从 Git 取得候选完整 base/head SHA，从决定来源取得有效版本。接收方按当前原始来源核对是否更新。context 是当前事实的一次快照，应独立核对来源后取得，不能通过复制旧 receipt 声称最新；校验器不保存或更新任务。

关键身份、任务版本或候选 SHA 未知时，保留文字交接与缺口，不用 `null`、假 SHA 或占位符生成有效回执。v1 只绑定提交候选；`base_sha`/`head_sha` 不能标识未提交差异，未提交工作仍按项目现有补丁/快照方式传递。`dependencies:[]` 和 `decisions:[]` 表示声明没有这些项，不能代替尚未调查；没有证据可用 `evidence:[]`，已有记录但无最终结果保留相应状态。

## 合成交接样例

保存为 `receipt.json`：

```json
{
  "schema_version": 1,
  "kind": "receipt",
  "repository": "example/project",
  "task_id": "task-a",
  "session_id": "session-a",
  "revision": "task-revision-1",
  "state": "handoff",
  "candidate": {
    "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "source": "git:example/project#candidate"
  },
  "ownership": {
    "source": "task:allocation-1",
    "paths": ["src/api/"],
    "shared_interfaces": []
  },
  "dependencies": [],
  "decisions": [
    {"id": "decision-a", "revision": "2", "source": "adr:decision-a"}
  ],
  "evidence": [
    {
      "candidate_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "command": "python -m unittest",
      "result": "unknown",
      "source": "artifact:synthetic-check",
      "environment": "synthetic"
    }
  ],
  "handoff": {
    "to_session": "session-b",
    "next_action": "核对当前决定与候选，取得原始测试最终结果"
  }
}
```

保存为 `context.json`：

```json
{
  "schema_version": 1,
  "kind": "context",
  "repository": "example/project",
  "source": "task:observed-current-snapshot",
  "tasks": [
    {
      "task_id": "task-a",
      "revision": "task-revision-1",
      "owner_session": "session-a",
      "state": "handoff",
      "candidate": {
        "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "source": "git:example/project#candidate"
      },
      "ownership": {
        "source": "task:allocation-1",
        "paths": ["src/api/"],
        "shared_interfaces": []
      },
      "dependencies": [],
      "decisions": [
        {"id": "decision-a", "revision": "2", "source": "adr:decision-a"}
      ]
    }
  ]
}
```

## 按需校验

需要 Python 3.10+ 及源码仓库中的 `scripts/team_receipt.py`、同目录 `scripts/team_receipt.schema.json`。这两个文件不包含在 plugin 或 repository-skills 安装包内；移动单个 Skill 只带走本模板，不代表 CLI 已安装。在已取得工具的源码根目录运行：

```sh
python scripts/team_receipt.py check receipt.json --context context.json
```

`--context` 必填；按需重复添加 `--peer peer-a.json`，所有传入 receipt 的任务都要有对应 context 记录。没有提供 peer 不证明没有其他并行 Session。不要为了校验另建任务库或每轮手填快照。

本合成样例预期 exit 0、`status:"consistent"`、`checked_receipts:1`、`receipts_without_evidence:0`、`evidence_results.unknown:1`，并始终有 `behavior_verification:"not_performed"`。未知证据仍是未知，快照一致不能报告为测试通过、业务验收或接收者实际接续。

| 退出码 | status | 含义 |
|---|---|---|
| 0 | `consistent` | 所提供快照的形状和一致性检查通过 |
| 1 | `conflict` | 输入形状有效，发现协作冲突 |
| 2 | `invalid_input` | 文件读取、JSON、字段或标识等输入错误 |

解析后的结果为 stdout JSON；普通命令行语法错误走 stderr、exit 2。工具只读、不联网、不运行证据命令；`passed` 也只是输入声明。`result` 完整枚举为 `passed|failed|pending|not_run|skipped|unavailable|unknown`，等待异步最终结果时用 `pending`。

对象禁止未知字段、`null`、重复 key 和非有限数字；`schema_version` 为整数 `1`。SHA 是 40 或 64 位完整小写十六进制值。身份和版本按原值区分大小写；source 只要求非空白文本，不认证或读取。`handoff` 仅在 state 为 `handoff` 时必填，其他状态禁止；`to_session` 必须不同于发出方。context task 没有 evidence 或 handoff 字段。

ownership 路径使用仓库相对字面路径：`src/api/` 表示目录范围，`src/api/client.py` 表示文件；不使用绝对路径、`.`/`..`、空路径段、反斜杠、冒号、glob 或控制字符。工具按字面路径区分大小写，不解析符号链接或别名。共享接口用项目已有标识；不同路径仍可能通过接口产生依赖。

校验器比较所给任务版本、state、归属、候选、写入范围、依赖声明、决定版本及证据候选绑定；对所给 active/handoff 回执检查重复任务、路径重叠与共享接口交集。它不验证 Git 对象存在、依赖已经集成、状态迁移合法、来源真实/最新或未提供的工作。取消/恢复从既有来源刷新事实；变更后只重查受影响证据，实际分配、冲突协调和接续由项目既有机制负责。
