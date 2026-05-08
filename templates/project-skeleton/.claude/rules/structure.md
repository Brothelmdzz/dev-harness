# 目录结构规范（约束层示例）

> 这是一份**示例文件**。请按你们的实际分层改写。

## 规则 1：单职责分层（示例）

**补偿的缺口**：模型倾向把 service / hook / component / utils 全部塞进一个文件夹，导致模块边界模糊、互相导入循环依赖。

**❌ 反例**：
```
src/feature/user/
  ├── index.ts       (混了 UI、API、类型、常量)
  └── helpers.ts     (混了纯函数、API 调用、UI 工具)
```

**✅ 正例**（参考得物 *Spec Coding* 实战的分层）：
```
src/feature/user/
  ├── constants/      (常量、枚举、固定字符串)
  ├── types/          (TypeScript 类型/接口定义)
  ├── services/       (API 调用，命名 fetchXxxApi)
  ├── hooks/          (React hooks)
  ├── components/     (React 组件)
  ├── utils/          (纯函数工具)
  └── index.ts        (re-export 入口)
```

**边界 / 例外**：
- 单文件功能不强制拆 6 个目录（小功能 1-2 个文件即可）
- 共享层（如 `src/shared/`）有自己的分层规则

---

## 规则 2：禁止跨业务模块的横向 import

**补偿的缺口**：模型生成代码时容易直接 `import { something } from '../order/utils'` 跨业务模块拿东西，导致依赖网状化。

**❌ 反例**：
```typescript
// src/feature/user/components/UserCard.tsx
import { formatOrderAmount } from '../../order/utils/format'
```

**✅ 正例**：通过共享层中转
```typescript
// src/feature/user/components/UserCard.tsx
import { formatAmount } from '@/shared/utils/format'
```

**边界 / 例外**：
- 同根模块（如 `feature/order` 和 `feature/order-detail`）允许横向引用
- 通过明确的 facade 暴露的接口（如 `feature/order/api`）允许跨模块调

---

## 规则 3：测试文件与源码同目录（示例）

**补偿的缺口**：模型默认把测试放 `__tests__/` 或 `tests/` 下，但这种做法在大型仓库中难以一眼看出测试覆盖。

**❌ 反例**：
```
src/feature/user/services/userApi.ts
tests/feature/user/userApi.test.ts
```

**✅ 正例**：
```
src/feature/user/services/userApi.ts
src/feature/user/services/userApi.test.ts
```

**边界 / 例外**：
- E2E 测试可以独立 `e2e/` 目录
- 集成测试需要测试装置的可独立 `integration-tests/`

---

## 规则 4：每个新增目录必须有 README

**补偿的缺口**：模型不会主动给新目录写 README，导致下次 agent 进来又得猜目录用途。

**✅ 正例**：每个 `src/feature/xxx/` 顶层放一个 `README.md`，至少回答：
- 这个模块负责什么业务
- 入口文件是哪个
- 上游/下游依赖
- 已知坑（链接到 `pitfall-journal.jsonl` 相关条目）
