---
name: generic-frontend-implement
description: 通用前端实现 — 检测前端技术栈，按 plan 逐 Phase 实现组件/页面/路由变更，自动门禁验证。
---

# 通用前端实现

## 约束

- 遵循项目现有的组件命名规范和目录结构
- 使用项目已有的 UI 组件库（不引入新的 UI 框架）
- 样式遵循项目现有方案（CSS Modules / Tailwind / styled-components）
- 不擅自添加新依赖
- 门禁（build + lint + test）必须全部通过

## 框架特化

检测 `package.json` 中的框架后，读取本目录下对应文件：
- Next.js → 读取 framework-nextjs.md
- React → 读取 framework-react.md
- Vue/Nuxt → 读取 framework-vue.md
- Angular → 读取 framework-angular.md
- Svelte → 读取 framework-svelte.md

## 状态上报

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/dh-python.sh" "${CLAUDE_PLUGIN_ROOT}/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass
```
