# Angular 实现指引

## 门禁命令
```bash
ng build && ng lint && ng test --watch=false
```

## 变更清单
1. 组件: `ng generate component`
2. 服务: `ng generate service`
3. 路由: `app-routing.module.ts` 或 standalone routes
4. 模块: `*.module.ts`（非 standalone）
5. 类型: `*.model.ts`

## 注意
- Standalone components（v17+）优于 NgModule
- 用 Angular CLI 生成文件保持一致性
- RxJS pipe 操作符优于嵌套 subscribe
- OnPush 变更检测优于默认策略
