# 命名规范（约束层示例）

> 这是一份**示例文件**。请按你们的实际命名约定改写。
> 写法遵循 [`README.md`](README.md) 的反例免疫格式。

## 规则 1：函数名必须动词开头

**补偿的缺口**：模型默认会按英语习惯用名词命名函数（如 `userValidation()`），导致和数据/类型名混淆。

**❌ 反例**：
```typescript
function userValidation(user: User): boolean {}
function dataProcess(data: Data) {}
```

**✅ 正例**：
```typescript
function validateUser(user: User): boolean {}
function processData(data: Data) {}
```

**边界 / 例外**：
- React 组件名是 PascalCase 名词，不适用此规则
- 工具函数模块的"导出对象"可以用名词（如 `export const userUtils = { ... }`）

---

## 规则 2：API 调用函数必须 `fetchXxxApi` 前缀（示例）

**补偿的缺口**：模型容易把 API 调用混进业务逻辑里（如 `getUserList()` 既可能是本地缓存查询也可能是 API），命名歧义导致 review 时难以一眼分辨副作用。

**❌ 反例**：
```typescript
async function getUserList() {
  return await axios.get('/api/users')
}
```

**✅ 正例**：
```typescript
async function fetchUserListApi() {
  return await axios.get<IUserListRes>('/api/users')
}
```

**边界 / 例外**：
- 本地缓存查询用 `getCachedXxx`
- 同步纯计算用 `calculateXxx` / `deriveXxx`

---

## 规则 3：接口请求/响应类型必须 `I{Name}Req` / `I{Name}Res`（示例）

**补偿的缺口**：模型常把 request/response 类型混在业务实体类型里，导致前后端契约对齐困难。

**❌ 反例**：
```typescript
interface User { id: string; name: string }
interface UserCreate { name: string }
```

**✅ 正例**：
```typescript
interface IUser { id: string; name: string }              // 业务实体
interface IUserCreateReq { name: string }                  // 接口请求
interface IUserCreateRes { id: string; createdAt: string } // 接口响应
```

**边界 / 例外**：
- 已有项目存量类型保留原命名，仅新增类型遵守

---

## 这份文件应该多长

10-30 条规则即可，每条 5-10 行。超过 200 行就拆成 `code-naming-frontend.md` / `code-naming-backend.md`。

> 渐进披露原则：模型不会一次读完整本「百科全书」。
