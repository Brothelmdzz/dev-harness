# Svelte 实现指引

## 门禁命令
```bash
npm run build && npm run lint && npm test
```

## 变更清单
1. 组件: `src/lib/components/`
2. 页面: `src/routes/`（SvelteKit）
3. 布局: `+layout.svelte`
4. 数据加载: `+page.server.ts` / `+page.ts`
5. Store: `src/lib/stores/`

## 注意
- SvelteKit 文件路由，`+page.svelte` 是页面入口
- `$:` 响应式声明（Svelte 4）或 `$state`/`$derived`（Svelte 5）
- 服务端数据加载用 `load` 函数
