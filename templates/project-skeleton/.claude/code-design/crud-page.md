# CRUD 页面整套模板（示例）

> 这是一份**示例文件**。最复杂的模板，整合了 api-handler + react-component + 表单 + 列表 + 弹窗。

## 用途

新需求是「[资源] 管理页（增删改查 + 列表 + 详情）」时——这是中后台最常见场景，照搬这套不用思考。

## 涉及的产物清单

```
src/feature/[resource]/
  ├── types/
  │   └── [resource].types.ts          ← I[Resource], I[Resource]CreateReq, ...
  ├── services/
  │   └── [resource]Api.ts             ← fetch[Resource]ListApi, create[Resource]Api, ...
  ├── hooks/
  │   ├── use[Resource]List.ts         ← 列表数据 + 分页 + 搜索
  │   └── use[Resource]Form.ts         ← 表单状态 + 提交
  ├── components/
  │   ├── [Resource]Table/             ← 列表表格
  │   ├── [Resource]FormDrawer/        ← 新增/编辑抽屉
  │   └── [Resource]DetailModal/       ← 详情弹窗
  └── pages/
      └── [Resource]ListPage.tsx       ← 页面入口

server/
  ├── feature/[resource]/
  │   ├── handlers/[resource]Handler.ts
  │   ├── services/[resource]Api.ts
  │   └── router.ts
```

## Hook 模板：use[Resource]List

```typescript
// src/feature/order/hooks/useOrderList.ts
import { useState, useEffect } from 'react'
import { fetchOrderListApi } from '../services/orderApi'
import type { IOrder } from '../types/order.types'

export interface IUseOrderListParams {
  pageSize?: number
  searchKey?: string
}

export function useOrderList(params: IUseOrderListParams = {}) {
  const [data, setData] = useState<IOrder[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const reload = async () => {
    setLoading(true)
    try {
      const res = await fetchOrderListApi({ page, pageSize: params.pageSize ?? 20, searchKey: params.searchKey })
      setData(res.list)
      setTotal(res.total)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { reload() }, [page, params.searchKey])

  return { data, loading, page, total, setPage, reload }
}
```

## 关键决策点

1. **每种类型操作一个 hook**
   - `use[Resource]List`：列表 + 分页 + 搜索
   - `use[Resource]Form`：表单创建/编辑
   - `use[Resource]Detail`：单条详情
   - 必抄：不要把"列表"和"表单"都塞一个 hook

2. **Drawer 用于编辑、Modal 用于详情**
   - 为什么：编辑场景需要表单空间，Drawer 比 Modal 宽
   - 必抄

3. **关闭抽屉时主动 form.resetFields() + 清空选中状态**
   - 为什么：得物 SDD 实战发现的隐性陷阱——AI 会自动复刻参考实现的隐性行为，但 SDD 文档没明说
   - 必抄
   - 引证：`docs/external-references-2026-05.md` 文章 2 的"SDD 陷阱"

4. **删除前必须二次确认 Modal**
   - 必抄：用 Popconfirm 或 Modal.confirm
   - 不要直接 `onClick={() => deleteOrder(id)}`

5. **列表分页参数对齐后端**
   - 后端 `{ page, pageSize, total }` ↔ 前端 `useOrderList`
   - 必抄

## 反模式

```typescript
// ❌ 列表数据放 useState，没有抽 hook
function OrderListPage() {
  const [orders, setOrders] = useState([])
  useEffect(() => { fetch('/api/orders').then(...) }, [])
  // ↑ 应该 useOrderList()
}

// ❌ 表单和列表共用一个组件状态
function OrderListPage() {
  const [editing, setEditing] = useState(null)
  const [orders, setOrders] = useState([])
  // ↑ 应该 useOrderList + useOrderForm 两个 hook
}

// ❌ 删除直接执行
<Button onClick={() => deleteOrder(id)}>删除</Button>
// ✅ 必须二次确认
<Popconfirm title="确认删除？" onConfirm={() => deleteOrder(id)}>
  <Button danger>删除</Button>
</Popconfirm>
```

## 衍生场景

- 资源有树形结构（如部门、分类）→ 用 antd Tree 替代 Table
- 资源有审批流 → 单独参考 `workflow-page.md`（按需新增）
- 资源是只读（不能编辑）→ 简化版只保留 Table + DetailModal
