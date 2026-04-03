---
name: generic-wiki
description: Wiki 知识库自动同步 — 在代码变更交付后将功能说明、接口文档、架构变更同步到团队 Wiki（Confluence/飞书）。Use when: dev pipeline 的 wiki 阶段，或用户说"同步wiki/更新wiki/wiki sync"。
---

# Wiki 知识库同步

## 角色
你是知识管理员。确保代码变更后团队 Wiki 同步更新，知识不散落在个人记忆中。

## 触发条件
- dev pipeline 的 wiki 阶段自动触发
- 用户手动请求同步

## 跳过条件
- 路线 C-lite（改动太小）
- 纯内部重构无外部行为变化
- 只改了测试/配置文件

---

## 第一步: 判断同步内容

根据本次变更类型确定要同步什么：

| 变更类型 | 同步内容 |
|----------|---------|
| 新功能/新接口 | 功能说明 + API 文档 + 数据库变更 |
| 接口变更 | 更新对应接口文档章节 |
| Bug 修复（影响行为） | 更新受影响功能的说明 |
| 架构变更 | 更新架构文档 + 模块关系 |
| 配置变更 | 更新配置说明 + 部署文档 |
| 纯内部重构 | **不同步** |

用 `git diff --name-only master...HEAD` 分析改动文件，判断变更类型。

## 第二步: 确定 Wiki 工具

按优先级尝试：

### 优先级 1: 项目 dev-config.yml 配置

读取 `.claude/dev-config.yml` 的 wiki 配置：
```yaml
wiki:
  type: confluence          # confluence 或 lark
  base_url: "http://your-wiki.example.com/confluence"
  space_key: YOUR_SPACE
```

### 优先级 2: Atlassian MCP（如已认证）

检查是否有 `mcp__claude_ai_Atlassian` 系列工具可用。如果已认证，直接用 MCP 工具操作 Confluence。

调用前先用 ToolSearch 检查:
```
ToolSearch("confluence atlassian page")
```
如果返回 create_page、update_page 等工具 → 使用 MCP。

### 优先级 3: ai-capability-hub REST API

项目 `your-project/tools/confluence/index.ts` 提供 REST API:
- 认证: Basic Auth（环境变量 CONFLUENCE_USERNAME / CONFLUENCE_PASSWORD）
- 操作: search / get / create / update

通过 Bash curl 调用（需要 ai-capability-hub 服务运行中）。

### 优先级 4: 飞书知识库

如果项目配置了 `wiki.type: lark`，使用:
- `/lark-wiki` — 定位知识空间和节点
- `/lark-doc` — 创建/更新文档内容

### 降级: 本地 Markdown

以上全不可用时，生成文件到 `docs/wiki-pending/`，提醒用户手动上传。

---

## 第三步: 执行同步

### Confluence 操作流程

```
1. 搜索: 在目标 space 中搜索是否已有对应页面
   action=search, space=YOUR_SPACE, query="功能名称"

2. 判断: 页面存在?
   YES → action=get, page_id=xxx  获取当前内容和版本号
         → action=update, page_id=xxx  追加/更新变更内容
   NO  → action=create, space=YOUR_SPACE, title=xxx, parent_id=xxx

3. 内容格式: Confluence Storage Format (XHTML)
   将 Markdown 变更说明转换为 XHTML
   保留原有内容，仅追加/更新变更部分
```

### 飞书操作流程

```
1. /lark-wiki 定位知识空间和目标节点
2. /lark-doc 获取或创建文档
3. /lark-doc 更新文档内容（追加模式）
```

---

## 第四步: 生成同步报告

保存到 `.claude/reports/wiki-sync-{date}.md`:

```markdown
# Wiki 同步报告 - {module} - {date}

## 同步方式
Atlassian MCP / ai-capability-hub / 飞书 / 降级(本地 Markdown)

## 同步操作
| 页面 | 操作 | 状态 | URL |
|------|------|------|-----|
| xxx功能说明 | 更新 | 成功 | http://... |

## 跳过原因（如有）
- xxx: 纯内部重构，无外部行为变化
```

---

## 铁律

1. **不删除 Wiki 页面** — 只创建和更新
2. **创建新顶层页面需人确认** — 防止污染 Wiki 结构
3. **保留原有内容** — 追加/更新，不覆盖全文
4. **Wiki 不可用不阻断提交** — 降级为本地 Markdown，提醒用户手动上传
