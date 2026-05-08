# 代码风格（约束层示例）

> 这是一份**示例文件**。请按你们的实际风格指南改写。

## 规则 1：错误处理必须显式区分"业务错误"和"系统错误"

**补偿的缺口**：模型默认习惯用 `try/catch` 一把抓，把网络错误、参数错误、业务逻辑错误混作一谈，导致前端无法做差异化提示。

**❌ 反例**：
```typescript
try {
  const result = await fetchOrderApi(id)
  return result
} catch (e) {
  message.error('Something went wrong')
}
```

**✅ 正例**：
```typescript
try {
  const result = await fetchOrderApi(id)
  if (!result.success) {
    return { ok: false, kind: 'business', code: result.code, message: result.message }
  }
  return { ok: true, data: result.data }
} catch (e) {
  if (axios.isAxiosError(e)) {
    return { ok: false, kind: 'network', message: '网络异常，请稍后重试' }
  }
  return { ok: false, kind: 'system', message: '系统错误' }
}
```

**边界 / 例外**：
- 全局错误边界（如 React ErrorBoundary）可以保留 catch-all
- 命令行工具内部脚本不强制（影响范围小）

---

## 规则 2：禁止 `any` / `unknown` 兜底

**补偿的缺口**：模型遇到类型推断困难时倾向标 `any` 让代码"先跑起来"，但这会让下游 review/test 失去类型保护。

**❌ 反例**：
```typescript
function process(data: any) { ... }
const result = JSON.parse(text) as any
```

**✅ 正例**：
```typescript
function process(data: IRawInput) { ... }
const result = JSON.parse(text) as IConfigSchema
// 或显式标注 unknown 并配合 type guard
const raw: unknown = JSON.parse(text)
if (isConfigSchema(raw)) { ... }
```

**边界 / 例外**：
- 第三方库 typing 缺失时可临时 `any`，但必须加 `// TODO(typing): xxx` 注释 + 创建 issue 跟踪

---

## 规则 3：组件 props ≤ 8 个（示例）

**补偿的缺口**：模型生成 React 组件时倾向把所有可配置项都开成 props，最后产出 17+ props 的"上帝组件"难以测试和复用。

**❌ 反例**：
```tsx
<ChatInterface
  messages={...} loading={...} input={...} onSend={...}
  showHeader={...} showAvatar={...} showTimestamp={...}
  theme={...} mode={...} placeholder={...}
  maxLength={...} onRetry={...} onCancel={...}
  ... // 17 个 props
/>
```

**✅ 正例**：拆成多个小组件 + 用 context 传递主题/状态
```tsx
<ChatProvider value={{ theme, mode }}>
  <ChatInterface
    messages={messages}
    onSend={onSend}
    placeholder={placeholder}
    maxLength={maxLength}
  />
</ChatProvider>
```

**边界 / 例外**：
- 表单组件因为字段多可以放宽到 12 个
- 库的根组件（如 antd Table）不适用此规则
