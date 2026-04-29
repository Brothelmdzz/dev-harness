# TypeScript/Node 测试指引

## 测试命令
```bash
npm test
# 或 vitest/jest 直接调用
npx vitest run
npx jest
```

## 单测定位
```bash
npx jest --testPathPattern=auth
npx vitest run src/auth
```

## 覆盖率
```bash
npx vitest run --coverage
npx jest --coverage
```

## 常见问题
- ESM import 报错 → 检查 `jest.config` 的 `transform` 或 vitest 的 `deps.inline`
- React 组件测试 → 需要 `@testing-library/react` + jsdom 环境
- 超时 → `jest.setTimeout(10000)` 或 vitest `test.timeout`
