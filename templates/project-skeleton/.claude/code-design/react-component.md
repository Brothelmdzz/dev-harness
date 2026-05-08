# React 组件标准模板（示例）

> 这是一份**示例文件**。请按你们的实际前端框架/UI 库改写。

## 用途

实现一个新的可复用 React 组件时，按这份模板的结构组织。

## 完整代码示例（React 18 + TypeScript + antd）

```tsx
// ==================== src/feature/order/components/OrderCard/index.tsx ====================
// 必抄：每个组件一个目录 + index.tsx
import { memo } from 'react'
import { Card, Tag, Button } from 'antd'
import type { IOrder } from '../../types/order.types'
import { formatAmount } from '@/shared/utils/format'
import styles from './OrderCard.module.css'

export interface IOrderCardProps {
  order: IOrder
  onCancel?: (id: string) => void
  // props ≤ 8 个；超过就拆子组件 / 用 context
}

function OrderCardImpl({ order, onCancel }: IOrderCardProps) {
  const handleCancel = () => onCancel?.(order.id)

  return (
    <Card className={styles.card} title={`订单 #${order.id.slice(0, 8)}`}>
      <div className={styles.row}>
        <span>金额</span>
        <span>{formatAmount(order.amount)}</span>
      </div>
      <div className={styles.row}>
        <span>状态</span>
        <Tag color={order.status === 'paid' ? 'green' : 'orange'}>
          {order.status}
        </Tag>
      </div>
      {onCancel && (
        <Button danger onClick={handleCancel}>取消订单</Button>
      )}
    </Card>
  )
}

export const OrderCard = memo(OrderCardImpl)

// ==================== src/feature/order/components/OrderCard/OrderCard.test.tsx ====================
// 必抄：测试与源码同目录
import { render, screen, fireEvent } from '@testing-library/react'
import { OrderCard } from './'

describe('OrderCard', () => {
  const fakeOrder = { id: 'abc-123', userId: 'u1', amount: 99, status: 'paid', createdAt: '...' }

  it('renders order info', () => {
    render(<OrderCard order={fakeOrder} />)
    expect(screen.getByText(/订单/)).toBeInTheDocument()
  })

  it('calls onCancel when cancel clicked', () => {
    const onCancel = jest.fn()
    render(<OrderCard order={fakeOrder} onCancel={onCancel} />)
    fireEvent.click(screen.getByText('取消订单'))
    expect(onCancel).toHaveBeenCalledWith('abc-123')
  })
})
```

## 关键决策点

1. **每个组件独立目录**
   - 为什么：组件 + 测试 + 样式 + 子组件可同居，不污染父级目录
   - 必抄

2. **`export interface IXxxProps` 显式导出 props 类型**
   - 为什么：父组件可以 `import type { IOrderCardProps }` 复用
   - 必抄

3. **Props ≤ 8 个**
   - 见 `rules/code-style.md` 规则 3
   - 必抄

4. **`memo` 包裹**
   - 为什么：React 默认 props 全比对；列表渲染时 memo 显著降低重渲染
   - 可变：性能不敏感的内部组件可以省略

5. **CSS Module / styled-components / Tailwind 任选**
   - 可变：选了之后整个项目统一

## 反模式

```tsx
// ❌ Props 太多
<OrderCard
  order={...}
  onCancel={...}
  showHeader={...} showFooter={...}
  variant="..." size="..." theme="..."
  loading={...} disabled={...}
  onClickHeader={...} onClickFooter={...}
/>

// ❌ 业务逻辑写在组件内（应该抽到 hook 或 service）
function OrderCard({ orderId }: { orderId: string }) {
  const [order, setOrder] = useState(null)
  useEffect(() => {
    fetch(`/api/orders/${orderId}`).then(r => r.json()).then(setOrder)
  }, [orderId])
  // ↑ 应该抽 useOrder hook
}

// ❌ 没有显式 Props 类型（用 any 或 inline）
function OrderCard(props: any) { ... }
```

## 衍生场景

- 组件需要表单 → 参考 `crud-page.md` 的表单子模板
- 组件需要拖拽 → 参考 `dnd-component.md`（按需新增）
- 组件是页面级 → 参考 `crud-page.md`
