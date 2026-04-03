---
name: generic-docs
description: 通用文档更新 — 扫描代码变更自动更新 README 和 API 文档。
---

# 通用文档更新

## 触发条件
本次代码变更涉及公开 API（Controller/路由/handler/导出函数）时执行，否则跳过。

## 执行流程

1. **扫描变更**: `git diff --name-only master...HEAD` 找到改动文件
2. **识别 API 变更**: 检查是否有路由/接口/导出的变化
3. **更新文档**:
   - 如果项目有 `docs/` 目录 → 更新对应文档
   - 如果有 README.md 的 API 章节 → 更新
   - 如果有 OpenAPI/Swagger 文件 → 提示用户更新
4. **产出变更说明**: 列出更新了哪些文档

## 跳过条件
- 纯内部重构（无 API 变更）
- 只改了测试文件
- 只改了配置文件
