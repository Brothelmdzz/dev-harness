# Next.js 实现指引

## 门禁命令
```bash
npm run build && npm run lint && npm test
```

## 变更清单
1. 页面: `app/` 或 `pages/` 目录
2. 组件: `components/` 目录
3. API 路由: `app/api/` 或 `pages/api/`
4. 中间件: `middleware.ts`
5. 样式: CSS Modules / Tailwind

## 注意
- App Router vs Pages Router 不混用
- Server Component 默认，需要交互的用 `'use client'`
- 数据获取用 `fetch` + cache，不用 `getServerSideProps`（App Router）
