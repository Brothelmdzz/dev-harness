# React 实现指引

## 门禁命令
```bash
npm run build && npm run lint && npm test
```

## 变更清单
1. 组件: `src/components/`
2. 页面: `src/pages/` 或 `src/views/`
3. 路由: `src/router/` 或 `src/App.tsx`
4. 状态: Redux / Zustand / Context
5. API: `src/api/` 或 `src/services/`

## 注意
- 函数组件 + hooks，不用 class 组件
- 状态提升优于 prop drilling，Context 优于全局 store（小范围共享）
- `useMemo`/`useCallback` 只在确有性能问题时使用
