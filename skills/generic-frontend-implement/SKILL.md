---
name: generic-frontend-implement
description: 通用前端实现 — 检测前端技术栈，按 plan 逐 Phase 实现组件/页面/路由变更，自动门禁验证。
---

# 通用前端实现

## 角色
你是前端实现专家。按计划精确实现 UI 组件、页面、路由和状态管理变更。

## 执行流程

### 第一步: 检测前端技术栈

```bash
# 检查 package.json 中的框架
cat package.json 2>/dev/null | python -c "
import sys, json
try:
    pkg = json.load(sys.stdin)
    deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
    if 'next' in deps: print('nextjs')
    elif 'nuxt' in deps: print('nuxt')
    elif 'react' in deps: print('react')
    elif 'vue' in deps: print('vue')
    elif 'angular' in deps or '@angular/core' in deps: print('angular')
    elif 'svelte' in deps: print('svelte')
    else: print('unknown')
except: print('unknown')
"
```

### 第二步: 读取 plan 并定位当前 Phase
完整阅读 `.claude/plans/` 下的计划文档，定位到当前 Phase。

### 第三步: 执行变更

按计划中的变更清单顺序实现:
1. **组件文件**: 创建/修改 React/Vue/Angular 组件
2. **样式文件**: 创建/修改 CSS/SCSS/Tailwind 样式
3. **路由配置**: 更新路由表（Next.js pages/app、Vue Router、Angular Router）
4. **状态管理**: 更新 Store/Context/Signal（根据项目使用的方案）
5. **类型定义**: 更新 TypeScript 类型/接口（如有）
6. **API 集成**: 创建/修改 API 调用函数

### 第四步: 运行门禁

```bash
# 根据检测到的技术栈运行
# Next.js: npm run build && npm run lint && npm test
# React:   npm run build && npm run lint && npm test
# Vue:     npm run build && npm run lint && npm test
# Angular: ng build && ng lint && ng test --watch=false
```

门禁项:
1. 构建通过（build 命令）
2. Lint 通过（lint 命令）
3. 测试通过（test 命令）

### 第五步: 更新状态并继续

```bash
python "$DH_HOME/scripts/harness.py" update implement IN_PROGRESS \
  --phase {N} --gate build=pass --gate test=pass
```

## 约束
- 遵循项目现有的组件命名规范和目录结构
- 使用项目已有的 UI 组件库（不引入新的 UI 框架）
- 样式遵循项目现有方案（CSS Modules / Tailwind / styled-components）
- 不擅自添加新依赖
- 发现计划有误时停下来报告，不自行决定
