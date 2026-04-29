# Vue/Nuxt 实现指引

## 门禁命令
```bash
# Vue
npm run build && npm run lint && npm test
# Nuxt
npx nuxi build && npm run lint && npx vitest run
```

## 变更清单
1. 组件: `src/components/` 或 `components/`
2. 页面: `src/views/` 或 `pages/`
3. 路由: `src/router/index.ts` 或 Nuxt 自动路由
4. 状态: Pinia store
5. Composables: `src/composables/`

## 注意
- Vue 3 Composition API + `<script setup>` 优先
- Nuxt 自动导入，不需手动 import composables/components
- Pinia 替代 Vuex
