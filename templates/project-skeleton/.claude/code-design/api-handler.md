# API Handler 标准模板（示例）

> 这是一份**示例文件**。请按你们的实际后端框架替换。

## 用途

实现一个新的后端接口时（如 `GET /api/orders/:id`、`POST /api/orders`），照这份模板的分层结构走。

## 完整代码示例（Node.js + Express + Prisma 示意）

```typescript
// ==================== src/feature/order/types/order.types.ts ====================
// 必抄：业务实体 + 接口契约分离
export interface IOrder {
  id: string
  userId: string
  amount: number
  createdAt: string
}

export interface IOrderCreateReq {
  userId: string
  amount: number
}

export interface IOrderCreateRes extends IOrder {}

// ==================== src/feature/order/services/orderApi.ts ====================
// 必抄：fetchXxxApi 命名 + Result 类型化
import { db } from '@/shared/db'
import type { IOrder, IOrderCreateReq } from '../types/order.types'

export async function fetchOrderByIdApi(id: string): Promise<IOrder | null> {
  return db.order.findUnique({ where: { id } })
}

export async function createOrderApi(req: IOrderCreateReq): Promise<IOrder> {
  return db.order.create({ data: req })
}

// ==================== src/feature/order/handlers/orderHandler.ts ====================
// 必抄：Handler 只负责 HTTP 协议层（参数解析、错误包装、状态码）
import type { Request, Response } from 'express'
import { fetchOrderByIdApi, createOrderApi } from '../services/orderApi'
import { z } from 'zod'

const CreateOrderSchema = z.object({
  userId: z.string().uuid(),
  amount: z.number().positive(),
})

export async function getOrderById(req: Request, res: Response) {
  const order = await fetchOrderByIdApi(req.params.id)
  if (!order) return res.status(404).json({ error: 'order not found' })
  return res.json(order)
}

export async function createOrder(req: Request, res: Response) {
  const parsed = CreateOrderSchema.safeParse(req.body)
  if (!parsed.success) {
    return res.status(400).json({ error: 'invalid input', details: parsed.error.issues })
  }
  const order = await createOrderApi(parsed.data)
  return res.status(201).json(order)
}

// ==================== src/feature/order/router.ts ====================
// 必抄：路由聚合 + 中间件组合
import { Router } from 'express'
import { requireAuth, requireRole } from '@/shared/middleware/auth'
import * as h from './handlers/orderHandler'

export const orderRouter = Router()
orderRouter.get('/orders/:id', requireAuth, h.getOrderById)
orderRouter.post('/orders', requireAuth, h.createOrder)
```

## 关键决策点

1. **types / services / handlers / router 四层分离**
   - 为什么：让单测可以只测 services 层（不需要 mock express）
   - 必抄

2. **接口请求/响应类型 `IXxxReq` / `IXxxRes`**
   - 为什么：和业务实体 `IOrder` 区分，前后端契约一目了然
   - 必抄

3. **Handler 用 zod schema 校验**
   - 为什么：把"参数检查"统一成结构化代码，模型不再用 `if (!req.body.x)` 散落到处
   - 必抄

4. **业务逻辑写在 services 里**
   - 为什么：跨 handler 复用 + 单测友好
   - 必抄

5. **数据库使用具体 ORM（Prisma / TypeORM / Drizzle 任选）**
   - 可变：换 ORM 时整体替换 services 层
   - 但分层结构不变

## 反模式

```typescript
// ❌ Handler 里直接写 SQL / ORM 调用 — 业务逻辑下沉到 service
app.get('/orders/:id', async (req, res) => {
  const order = await db.order.findUnique({ where: { id: req.params.id } })
  res.json(order)
})

// ❌ 没有 zod / 类型校验 — 输入不可信
app.post('/orders', async (req, res) => {
  const order = await db.order.create({ data: req.body })  // 任意字段都进库
  res.json(order)
})
```

## 衍生场景

- 接口需要事务 → 参考 `crud-page.md` 的批量写入示例
- 接口涉及多服务调用 → 单独抽 `services/orderOrchestrator.ts`
- 高并发场景 → 参考 `handbooks/perf-tuning.md`（按需新增）
