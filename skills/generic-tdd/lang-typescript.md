# TypeScript TDD 指引

## 测试命令
```bash
npx jest --testPathPattern=xxx
npx vitest run src/xxx
npm test  # 全量
```

## RED 阶段
在 `__tests__/` 或 `*.test.ts` 创建测试：
```typescript
it('should create user with valid input', () => {
  const user = createUser({ name: 'alice' });
  expect(user.name).toBe('alice');
});
```

## GREEN 阶段
在源码目录写最小实现让测试通过。

## 框架注意
- React 组件: 用 `@testing-library/react` + `render()` + `screen`
- API 测试: 用 `supertest` 或框架自带 test client
- Mock: 用 `jest.mock()` 或 `vi.mock()`, 不过度 mock
