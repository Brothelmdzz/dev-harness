# 注释规范（约束层示例）

> 这是一份**示例文件**。

## 核心原则

**默认不写注释**。只在 WHY 不显然时写。

参考 dev-harness 的 CLAUDE.md：
> "Default to writing no comments. Only add one when the WHY is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behavior that would surprise a reader."

## 规则 1：禁止解释 WHAT

**补偿的缺口**：模型倾向给每行代码配解释性注释，把已经清晰的代码再啰嗦一遍。

**❌ 反例**：
```typescript
// 增加 i 的值
i++

// 遍历用户列表
for (const user of users) {
  // 检查用户是否激活
  if (user.active) {
    // 添加到结果
    result.push(user)
  }
}
```

**✅ 正例**：直接删除所有这种注释。
```typescript
i++
for (const user of users) {
  if (user.active) {
    result.push(user)
  }
}
```

---

## 规则 2：注释只在 WHY 非显然时写

**补偿的缺口**：模型不会区分"代码已经清晰"和"代码隐藏了非显然的设计决策"。

**❌ 反例**（注释解释代码做了什么 — 已经显然）：
```typescript
// 这个函数计算用户的总订单金额
function calculateTotal(user: IUser): number { ... }
```

**✅ 正例**（注释解释为什么这样做 — 非显然）：
```typescript
// 这里强制走主库，因为读写分离 binlog 延迟可能让刚下单的用户看不到自己的订单
function fetchOrderListForUser(userId: string) {
  return primaryDb.query(...)
}
```

---

## 规则 3：禁止过期注释

**补偿的缺口**：模型修改代码后经常忘记同步更新注释，导致注释和代码不一致 — 比没注释更糟。

**❌ 反例**：
```typescript
// 返回 true 如果用户已注销
function isUserActive(user: IUser): boolean {
  return user.status === 'active'
}
```

**✅ 正例**：发现注释过期 = 立即删除或修正。
```typescript
function isUserActive(user: IUser): boolean {
  return user.status === 'active'
}
```

---

## 规则 4：禁止"任务流注释"

**补偿的缺口**：模型在迭代过程中会留下「这里之前是 X，后来改成 Y」的注释，这类信息属于 git history，不属于代码。

**❌ 反例**：
```typescript
// 之前用的是 axios，后来改成 fetch
// 因为线上事故 #1234 修复了这里
const response = await fetch(url)
```

**✅ 正例**：把变更原因写到 commit message / PR 描述，代码里不留。
```typescript
const response = await fetch(url)
```

---

## 边界

- 公共 API / SDK 必须有 docstring 或 JSDoc，但聚焦"如何调用"和"前置条件"
- 复杂算法（动态规划、状态机）可以用一行注释指向参考资料 / 论文 URL
- 临时绕过的 bug 必须 `// TODO(2026-05-08): xxx` 带日期 + issue 链接
