# `docs/release-notes/` — 发布信息

> 每个版本的对外说明。

## 为什么需要这一层

「ALL In Code」哲学（设计哲学原则 4）——发布信息也是 Agent 工作所需上下文。

实际场景：
- Agent 生成需求文档时需要知道当前版本和已发布功能
- 客服 / 同事问"X 功能上线了吗"时直接 grep
- 故障回溯时按版本时间线对照

## 文件命名

```
docs/release-notes/
  ├── v1.2.0.md       ← 一个版本一个文件
  ├── v1.1.0.md
  └── README.md       ← 本文件，维护索引
```

## 写法（参考 Keep a Changelog）

```markdown
# v1.2.0 — 2026-05-08

## ✨ 新功能
- 订单批量操作（#PR-123）

## 🐛 修复
- 修复用户登录后头像不刷新 (#PR-130)

## 💥 破坏性变更
- 接口 `/api/orders` 删除 `deprecated_field` 字段

## 📝 内部
- 升级依赖 axios 1.6 → 1.7

## ⚠️ 已知问题
- IE 11 暂不支持（计划 v2.0 发布说明中提供降级方案）
```

## 维护原则

1. **每次发布同步更新** — 不允许"发了再补 release notes"
2. **破坏性变更必须显式标记** — 用 💥 emoji
3. **关联 PR / Issue / Commit** — 让人和 Agent 都能溯源

## 链接

- [Keep a Changelog 规范](https://keepachangelog.com/zh-CN/1.1.0/)
